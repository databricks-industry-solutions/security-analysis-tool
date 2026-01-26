# Databricks notebook source
# MAGIC %md
# MAGIC # Permissions Analysis Tool - Comprehensive Data Collection
# MAGIC
# MAGIC This notebook collects **all Databricks objects and permissions** across **ALL workspaces** in your account
# MAGIC into a Unity Catalog schema as a graph structure for security analysis.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC ### For Multi-Workspace Collection (Recommended)
# MAGIC Set up a Service Principal with Account Admin access. See **00_config** for detailed instructions.
# MAGIC
# MAGIC **Required Secrets** (in scope "brickhound"):
# MAGIC - `account-id` - Your Databricks Account UUID
# MAGIC - `sp-client-id` - Service Principal Application ID
# MAGIC - `sp-client-secret` - Service Principal OAuth Secret
# MAGIC
# MAGIC ### For Single Workspace Collection
# MAGIC If no SP credentials are configured, collection will only run on the current workspace using the notebook user's permissions.
# MAGIC
# MAGIC ## What Gets Collected
# MAGIC
# MAGIC ### Account-Level (requires SP with Account Admin)
# MAGIC * **Workspaces** - All workspaces in the account
# MAGIC * **Account Users, Groups, Service Principals** - With group memberships
# MAGIC * **Metastores** - Unity Catalog metastores and assignments
# MAGIC * **Workspace Assignments** - Who has access to which workspaces
# MAGIC
# MAGIC ### Workspace-Level (collected from ALL workspaces with SP, or current workspace only)
# MAGIC
# MAGIC #### Identity & Access
# MAGIC * Users, Groups, Service Principals
# MAGIC * Group memberships
# MAGIC
# MAGIC #### Compute
# MAGIC * Clusters, Instance Pools, Cluster Policies
# MAGIC * Global Init Scripts
# MAGIC
# MAGIC #### AI/ML
# MAGIC * Serving Endpoints, Vector Search Endpoints/Indexes
# MAGIC * Registered Models (Unity Catalog), MLflow Experiments
# MAGIC
# MAGIC #### Analytics/BI
# MAGIC * Dashboards (Lakeview), SQL Queries, Alerts
# MAGIC
# MAGIC #### Development
# MAGIC * Notebooks, Repos
# MAGIC
# MAGIC #### Orchestration
# MAGIC * Jobs, Pipelines (Delta Live Tables)
# MAGIC
# MAGIC #### Data & Analytics
# MAGIC * SQL Warehouses
# MAGIC * Catalogs, Schemas, Tables, Views, Volumes, Functions
# MAGIC * External Locations, Storage Credentials, Connections
# MAGIC
# MAGIC #### Security
# MAGIC * Secret Scopes, Secrets, Tokens, IP Access Lists
# MAGIC
# MAGIC #### Apps
# MAGIC * Databricks Apps
# MAGIC
# MAGIC ## Output
# MAGIC
# MAGIC Graph data saved to Delta Lake:
# MAGIC * `{CATALOG}.{SCHEMA}.vertices` - All resources and principals
# MAGIC * `{CATALOG}.{SCHEMA}.edges` - All relationships and permissions
# MAGIC * `{CATALOG}.{SCHEMA}.collection_metadata` - Collection timestamp and stats
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **Run cells in order from top to bottom.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Install Required Libraries

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# MAGIC %pip install databricks-sdk>=0.18.0 networkx tqdm python-dotenv --quiet

# COMMAND ----------

# DBTITLE 1,Restart Python (Required After Install)
dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Load Configuration

# COMMAND ----------

# MAGIC %run ./brickhound/00_config

# COMMAND ----------

# DBTITLE 1,Load Configuration
print("="*80)
print("Permissions Analysis Tool Configuration")
print("="*80)
print(f"Catalog:        {CATALOG}")
print(f"Schema:         {SCHEMA}")
print(f"Vertices:       {VERTICES_TABLE}")
print(f"Edges:          {EDGES_TABLE}")
print("="*80)

# COMMAND ----------

# DBTITLE 1,Verify catalog and schema setup
# Verify catalog exists and we have access
print("\n" + "="*80)
print("Verifying Catalog Access")
print("="*80)

try:
    existing_catalogs = spark.sql("SHOW CATALOGS").collect()
    catalog_names = [row.catalog for row in existing_catalogs]

    # Strip backticks for comparison (SAT uses backticks to handle special chars)
    catalog_name_clean = CATALOG.strip('`').strip()
    schema_name_clean = SCHEMA.strip('`').strip()

    if catalog_name_clean in catalog_names:
        print(f"\n Catalog '{catalog_name_clean}' exists")
    else:
        print(f"\n Catalog '{catalog_name_clean}' does not exist")
        print(f"\nAvailable catalogs: {', '.join(catalog_names)}")
        print(f"\n Update CATALOG in 00_config.py or create the catalog")
        raise Exception(f"Catalog {catalog_name_clean} not found")

    # Create schema if needed (use original CATALOG/SCHEMA with backticks for SQL)
    spark.sql(f"USE CATALOG {CATALOG}")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    print(f" Schema '{schema_name_clean}' ready")

    # Check existing tables
    tables = spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").collect()
    print(f" Found {len(tables)} existing tables in {CATALOG}.{SCHEMA}")

    if tables:
        print(f"\n Existing tables will be overwritten during save")

except Exception as e:
    print(f"\n Error: {e}")
    raise

print("\n" + "="*80 + "\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Configure Collection

# COMMAND ----------

# DBTITLE 1,Collection Configuration
from datetime import datetime

print("="*80)
print("Collection Configuration")
print("="*80)

# ============================================================================
# COLLECTION CONFIGURATION - Modify these settings as needed
# ============================================================================

COLLECTION_CONFIG = {
    # Scope settings
    'collect_account_level': True,  # Set to True when account admin SP is configured
    'collect_workspace_level': True,
    'collect_unity_catalog': True,
    'collect_permissions': True,  # CRITICAL - Must be True for permission analysis!

    # What to collect (set to False to skip)
    'collect_users': True,
    'collect_groups': True,
    'collect_service_principals': True,
    'collect_clusters': True,
    'collect_instance_pools': True,
    'collect_cluster_policies': True,
    'collect_global_init_scripts': True,
    'collect_serving_endpoints': True,
    'collect_vector_search_endpoints': True,
    'collect_vector_search_indexes': True,
    'collect_registered_models': True,
    'collect_experiments': True,
    'collect_dashboards': True,
    'collect_queries': True,
    'collect_alerts': True,
    'collect_notebooks': True,
    'collect_repos': True,
    'collect_jobs': True,
    'collect_pipelines': True,
    'collect_warehouses': True,
    'collect_metastores': True,
    'collect_external_locations': True,
    'collect_storage_credentials': True,
    'collect_connections': True,
    'collect_secret_scopes': True,
    'collect_tokens': True,
    'collect_ip_access_lists': True,
    'collect_apps': True,

    # Performance settings for Unity Catalog (adjust for large environments)
    'max_catalogs': None,  # None = no limit
    'max_schemas_per_catalog': None,
    'max_tables_per_schema': None,

    # Data retention settings
    # -1 = keep forever, 0 or 1 = keep only latest run, N = delete runs older than N days
    'retention_days': 30,

    # Output
    'output_catalog': CATALOG,
    'output_schema': SCHEMA,
}

print("\n Collection Scope:")
print(f"  Account Level: {'' if COLLECTION_CONFIG['collect_account_level'] else ' (requires account admin SP)'}")
print(f"  Workspace Level: {'' if COLLECTION_CONFIG['collect_workspace_level'] else ''}")
print(f"  Unity Catalog: {'' if COLLECTION_CONFIG['collect_unity_catalog'] else ''}")
print(f"  Permissions: {'' if COLLECTION_CONFIG['collect_permissions'] else ''}")

print(f"\n Output:")
print(f"  {COLLECTION_CONFIG['output_catalog']}.{COLLECTION_CONFIG['output_schema']}.vertices")
print(f"  {COLLECTION_CONFIG['output_catalog']}.{COLLECTION_CONFIG['output_schema']}.edges")

print("\n" + "="*80 + "\n")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Initialize Collector

# COMMAND ----------

# DBTITLE 1,Initialize Permissions Analysis Tool Collector and Load Credentials
import sys
import os
from databricks.sdk import WorkspaceClient, AccountClient, useragent

# Configure User-Agent for all API calls (aligns with dbclient.py)
useragent.with_product("databricks-sat", "0.1.0")

# Add the brickhound package to path (if running from notebooks folder)
repo_root = os.path.dirname(os.path.dirname(os.getcwd()))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# =============================================================================
# Helper Functions for Cloud Detection and Domain Extraction
# =============================================================================
# Note: These functions align with the reference implementation in dbclient.py
# and support government clouds (e.g., .com.br for Brazil, .mil for US military)

import re

def get_domain_from_url(url):
    """
    Extract domain suffix from Databricks URL to support government clouds.

    This function aligns with the reference implementation in dbclient.py and
    supports various domain suffixes including government clouds.

    Examples:
        https://adb-123.cloud.databricks.com → com
        https://adb-456.cloud.databricks.com.br → com.br
        https://workspace.azuredatabricks.net → net
        https://workspace.gcp.databricks.com → com

    Args:
        url (str): Databricks workspace URL

    Returns:
        str: Domain suffix (e.g., 'com', 'com.br', 'net')
    """
    regex = r"https://.*databricks\.(.*?)/?$"
    match = re.match(regex, url)
    if match:
        return match.group(1)

    # Fallback to '.com' or '.net' if extraction fails
    if 'azure' in url.lower():
        return 'net'
    return 'com'


def parse_cloud_type(workspace_url):
    """
    Determine cloud provider from workspace URL using explicit pattern matching.

    This function aligns with the reference implementation in dbclient.py for
    consistent cloud detection across the codebase.

    Args:
        workspace_url (str): Databricks workspace URL

    Returns:
        str: Cloud provider ('azure', 'aws', or 'gcp')
    """
    if 'azuredatabricks.net' in workspace_url:
        return 'azure'
    if 'gcp.databricks' in workspace_url:
        return 'gcp'
    if 'cloud.databricks' in workspace_url:
        return 'aws'

    # Fallback to AWS as default
    return 'aws'


print("="*80)
print("Initializing Permissions Analysis Tool Collector")
print("="*80)

# ============================================================================
# LOAD SERVICE PRINCIPAL CREDENTIALS (for multi-workspace collection)
# ============================================================================
# These credentials enable collection from ALL workspaces in your account.
# Without these, only the current workspace will be collected.

SP_CREDENTIALS = {
    'account_id': None,
    'client_id': None,
    'client_secret': None,
    'account_host': None
}
MULTI_WORKSPACE_MODE = False

# Determine account host based on current workspace URL
# Note: Domain extraction supports government clouds (e.g., .com.br for Brazil)
# This aligns with the reference implementation in dbclient.py
workspace_url = spark.conf.get("spark.databricks.workspaceUrl", "")
domain = get_domain_from_url(workspace_url)
cloud_type = parse_cloud_type(workspace_url)

if cloud_type == 'azure':
    SP_CREDENTIALS['account_host'] = f"https://accounts.azuredatabricks.{domain}"
elif cloud_type == 'gcp':
    SP_CREDENTIALS['account_host'] = f"https://accounts.gcp.databricks.{domain}"
else:  # aws
    SP_CREDENTIALS['account_host'] = f"https://accounts.cloud.databricks.{domain}"

# Store cloud type for later use
SP_CREDENTIALS['cloud_type'] = cloud_type

print(f"\n1. Loading Service Principal Credentials...")

# Get the secrets scope name (default: "sat_scope" for SAT integration)
secrets_scope = SECRETS_SCOPE if 'SECRETS_SCOPE' in dir() else "sat_scope"

try:
    # Updated for SAT integration: using SAT secret key names
    SP_CREDENTIALS['account_id'] = dbutils.secrets.get(scope=secrets_scope, key="account-console-id")
    SP_CREDENTIALS['client_id'] = dbutils.secrets.get(scope=secrets_scope, key="client-id")
    SP_CREDENTIALS['client_secret'] = dbutils.secrets.get(scope=secrets_scope, key="client-secret")

    if SP_CREDENTIALS['account_id'] and SP_CREDENTIALS['client_id'] and SP_CREDENTIALS['client_secret']:
        print(f"   ✓ Loaded credentials from secrets scope '{secrets_scope}'")
        print(f"   Account ID: {SP_CREDENTIALS['account_id'][:8]}...")
        print(f"   Client ID: {SP_CREDENTIALS['client_id'][:8]}...")
        print(f"   Account Host: {SP_CREDENTIALS['account_host']}")
        MULTI_WORKSPACE_MODE = True
    else:
        print(f"   ⚠ Some credentials missing in scope '{secrets_scope}'")
        MULTI_WORKSPACE_MODE = False
except Exception as e:
    print(f"   ⚠ Could not load SP credentials: {e}")
    print(f"   → Will collect from CURRENT WORKSPACE ONLY")
    print(f"   → Set up secrets in scope '{secrets_scope}' for multi-workspace collection")
    MULTI_WORKSPACE_MODE = False

# ============================================================================
# INITIALIZE CLIENTS
# ============================================================================
print(f"\n2. Initializing API Clients...")

account_client = None
workspaces_to_collect = []

# Track workspace collection status for metadata
WORKSPACE_COLLECTION_STATUS = {}  # {workspace_id: {'name': str, 'status': 'success'|'failed'|'skipped', 'error': str|None}}

# Initialize AccountClient if we have SP credentials
if MULTI_WORKSPACE_MODE:
    print(f"\n   Testing connection to Accounts Console...")
    print(f"   Host: {SP_CREDENTIALS['account_host']}")
    print(f"   Account ID: {SP_CREDENTIALS['account_id']}")

    # First, do a direct HTTP test to get raw error messages (SDK swallows details)
    import requests
    http_test_error = None
    try:
        # Try to get OAuth token first - this will reveal IP ACL issues
        token_url = f"{SP_CREDENTIALS['account_host']}/oidc/accounts/{SP_CREDENTIALS['account_id']}/v1/token"
        token_response = requests.post(
            token_url,
            data={
                'grant_type': 'client_credentials',
                'client_id': SP_CREDENTIALS['client_id'],
                'client_secret': SP_CREDENTIALS['client_secret'],
                'scope': 'all-apis'
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        if not token_response.ok:
            http_test_error = f"HTTP {token_response.status_code}: {token_response.text}"
    except requests.exceptions.RequestException as req_err:
        http_test_error = f"HTTP Request Error: {str(req_err)}"

    try:
        account_client = AccountClient(
            host=SP_CREDENTIALS['account_host'],
            account_id=SP_CREDENTIALS['account_id'],
            client_id=SP_CREDENTIALS['client_id'],
            client_secret=SP_CREDENTIALS['client_secret'],
            auth_type="oauth-m2m"
        )

        # Test connection and get list of workspaces
        workspaces_list = list(account_client.workspaces.list())
        workspaces_to_collect = [ws for ws in workspaces_list if ws.workspace_status and ws.workspace_status.value == 'RUNNING']

        print(f"   ✓ AccountClient initialized successfully")
        print(f"   ✓ Found {len(workspaces_to_collect)} active workspaces")
        for ws in workspaces_to_collect:
            print(f"      - {ws.workspace_name} (ID: {ws.workspace_id})")
            # Initialize status tracking
            WORKSPACE_COLLECTION_STATUS[str(ws.workspace_id)] = {
                'name': ws.workspace_name,
                'status': 'pending',
                'error': None
            }

    except Exception as e:
        # Try to extract detailed error message from various exception attributes
        error_msg = str(e)

        # Check for nested error details in SDK exceptions
        if hasattr(e, 'message'):
            error_msg = e.message
        if hasattr(e, 'error_code'):
            error_msg = f"{e.error_code}: {error_msg}"
        if hasattr(e, '__cause__') and e.__cause__:
            error_msg = f"{error_msg} (Caused by: {str(e.__cause__)})"
        if hasattr(e, 'args') and e.args:
            # Sometimes the real error is in args
            for arg in e.args:
                if isinstance(arg, str) and len(arg) > len(error_msg):
                    error_msg = arg

        # Also check repr for more details
        error_repr = repr(e)

        print(f"\n" + "="*80)
        print("❌ ACCOUNTS CONSOLE CONNECTION FAILED")
        print("="*80)

        # If we have the HTTP test error, show that (it has the real details)
        if http_test_error:
            print(f"\n   Error: {http_test_error}")
        else:
            print(f"\n   Error: {error_msg}")
            if "unknown: unknown" in error_msg.lower() or error_msg == str(e):
                print(f"   Details: {error_repr}")

        print(f"\n   This typically means:")

        # Check HTTP error, error_msg, and error_repr for known patterns
        full_error = f"{http_test_error or ''} {error_msg} {error_repr}".lower()
        if "blocked by databricks ip acl" in full_error or "ip access list" in full_error:
            print("   • Your Accounts Console has IP Access Lists enabled")
            print("   • Serverless compute IPs are NOT in your allow list")
            print("")
            print("   🔧 TO FIX THIS:")
            print("")
            print("   Option 1: Add Serverless IPs to Account IP Allow List")
            print("   • Contact your Databricks account team to get the serverless")
            print("     NAT gateway IPs for your region")
            print("   • Add those IPs to your Account Console IP Access List")
            print("")
            print("   Option 2: Run on Classic Compute (Recommended)")
            print("   • Run this notebook on a classic cluster (not serverless)")
            print("   • Classic clusters use your VPC's NAT gateway with known IPs")
            print("   • Add your VPC NAT gateway IPs to the Account IP Allow List")
            print("")
            print("   📚 Documentation:")
            print("   • https://docs.databricks.com/aws/en/security/network/front-end/ip-access-list-account")
        elif "401" in full_error or "unauthorized" in full_error:
            print("   • The Service Principal credentials are invalid")
            print("   • Check sp-client-id and sp-client-secret in your secrets scope")
        elif "403" in full_error or "forbidden" in full_error:
            print("   • The Service Principal does NOT have Account Admin role")
            print("   • Go to Account Console → User Management → Service Principals")
            print("   • Add the 'Account Admin' role to your Service Principal")
        elif "404" in full_error or "not found" in full_error:
            print("   • The Account ID may be incorrect")
            print("   • Verify account-id in your secrets scope")
        elif "connection" in full_error or "timeout" in full_error:
            print("   • Network connectivity issue to the Accounts Console")
            print("   • Check firewall rules and network configuration")
        else:
            print("   • Unknown error - see details above")

        print(f"\n   Required secrets in scope '{secrets_scope}':")
        print("   • account-id: Your Databricks Account UUID")
        print("   • sp-client-id: Service Principal Application ID")
        print("   • sp-client-secret: Service Principal OAuth Secret")
        print(f"\n" + "="*80)
        print("⛔ EXITING: Cannot proceed without Accounts Console access")
        print("   Please fix the configuration and re-run this notebook.")
        print("="*80 + "\n")
        raise Exception(f"Accounts Console connection failed: {error_msg}")

# Initialize WorkspaceClient for current workspace (fallback or for local testing)
try:
    w = WorkspaceClient()
    current_user = w.current_user.me()
    current_workspace_url = spark.conf.get("spark.databricks.workspaceUrl", "unknown")
    current_workspace_id = spark.conf.get("spark.databricks.clusterUsageTags.clusterOwnerOrgId", "unknown")
    print(f"\n   ✓ WorkspaceClient initialized for current workspace")
    print(f"   Authenticated as: {current_user.user_name}")
    print(f"   Current workspace: {current_workspace_url}")
except Exception as e:
    print(f"\n   ✗ Failed to initialize WorkspaceClient: {e}")
    raise

# ============================================================================
# TEST WORKSPACE CONNECTIVITY (Pre-flight check)
# ============================================================================
if MULTI_WORKSPACE_MODE and workspaces_to_collect:
    print(f"\n3. Testing connectivity to all workspaces...")
    print("-"*60)

    reachable_workspaces = []
    unreachable_workspaces = []

    for ws in workspaces_to_collect:
        ws_name = ws.workspace_name
        ws_id = str(ws.workspace_id)

        # Build workspace URL
        if ws.azure_workspace_info:
            ws_host = f"https://{ws.deployment_name}.azuredatabricks.net"
        elif hasattr(ws, 'gcp_managed_network_config') and ws.gcp_managed_network_config:
            ws_host = f"https://{ws.workspace_id}.gcp.databricks.com"
        else:
            ws_host = f"https://{ws.deployment_name}.cloud.databricks.com"

        try:
            # Test connection by creating client and making a simple API call
            test_client = WorkspaceClient(
                host=ws_host,
                client_id=SP_CREDENTIALS['client_id'],
                client_secret=SP_CREDENTIALS['client_secret'],
                auth_type="oauth-m2m"
            )
            # Simple API call to verify connectivity
            test_client.current_user.me()

            print(f"   ✓ {ws_name} - reachable")
            reachable_workspaces.append(ws)
            WORKSPACE_COLLECTION_STATUS[ws_id]['status'] = 'pending'  # Ready for collection

        except Exception as e:
            error_msg = str(e)
            print(f"   ✗ {ws_name} - UNREACHABLE")
            if "401" in error_msg or "Unauthorized" in error_msg:
                print(f"      Error: Service Principal not authorized (not added to workspace?)")
            elif "403" in error_msg or "Forbidden" in error_msg:
                print(f"      Error: Access denied (SP needs workspace access)")
            else:
                print(f"      Error: {error_msg[:100]}...")

            unreachable_workspaces.append((ws, error_msg))
            WORKSPACE_COLLECTION_STATUS[ws_id]['status'] = 'failed'
            WORKSPACE_COLLECTION_STATUS[ws_id]['error'] = error_msg[:500]

    print("-"*60)
    print(f"   Reachable: {len(reachable_workspaces)}/{len(workspaces_to_collect)} workspaces")

    if unreachable_workspaces:
        print(f"\n   ⚠ WARNING: {len(unreachable_workspaces)} workspace(s) are unreachable:")
        for ws, err in unreachable_workspaces:
            print(f"      • {ws.workspace_name}")
        print(f"\n   These workspaces will be SKIPPED during collection.")
        print(f"   To fix: Add the Service Principal to each workspace's identity federation.")

    # Update workspaces_to_collect to only include reachable ones
    workspaces_to_collect = reachable_workspaces

# ============================================================================
# COLLECTION MODE SUMMARY
# ============================================================================
print("\n" + "="*80)
if MULTI_WORKSPACE_MODE:
    print("🌐 MULTI-WORKSPACE MODE ENABLED")
    print(f"   Will collect from {len(workspaces_to_collect)} workspaces:")
    for ws in workspaces_to_collect:
        print(f"   • {ws.workspace_name}")
    print("\n   Account-level data will also be collected.")
else:
    print("📍 SINGLE WORKSPACE MODE")
    print(f"   Collecting from current workspace only: {current_workspace_url}")
    print("\n   ⚠ To collect from all workspaces:")
    print(f"   1. Set up a Service Principal with Account Admin role")
    print(f"   2. Add secrets to scope '{secrets_scope}':")
    print(f"      - account-id, sp-client-id, sp-client-secret")
    print(f"   3. Re-run this notebook")
print("="*80 + "\n")

# Try to import from installed package, otherwise use direct imports
try:
    from brickhound.collector.core import DatabricksCollector
    from brickhound.utils.config import DatabricksConfig, CollectorConfig
    from brickhound.graph.schema import NodeType, EdgeType
    print("Using installed Permissions Analysis Tool package")
except ImportError:
    print("Permissions Analysis Tool package not installed, using notebook implementation")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Run Data Collection
# MAGIC
# MAGIC This step collects all configured object types. In **multi-workspace mode**, it iterates over
# MAGIC all workspaces and collects data from each one. In **single workspace mode**, it only collects
# MAGIC from the current workspace.

# COMMAND ----------

# DBTITLE 1,Define Collection Helper Functions
import json
import uuid
from datetime import datetime, timedelta
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, BooleanType, TimestampType
from tqdm import tqdm

# Generate unique run_id for this collection (timestamp-based for readability + UUID for uniqueness)
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
print(f"\n🔖 Collection Run ID: {RUN_ID}")

# Helper function to safely get attribute
def safe_get(obj, attr, default=None):
    """Safely get attribute from object or dict"""
    if hasattr(obj, attr):
        val = getattr(obj, attr)
        # Handle enum values
        if hasattr(val, 'value'):
            return val.value
        return val
    elif isinstance(obj, dict):
        return obj.get(attr, default)
    return default

def safe_json(obj):
    """Safely convert object to JSON string"""
    try:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return json.dumps(obj)
        return json.dumps(obj.__dict__ if hasattr(obj, '__dict__') else str(obj))
    except:
        return None

def get_workspace_client(workspace):
    """
    Create a WorkspaceClient for a specific workspace using SP credentials.

    Args:
        workspace: Workspace object from AccountClient.workspaces.list()

    Returns:
        WorkspaceClient configured for the specified workspace
    """
    if not MULTI_WORKSPACE_MODE:
        return w  # Return current workspace client

    # Build the workspace URL
    ws_host = f"https://{workspace.deployment_name}.cloud.databricks.com"

    # For Azure workspaces
    if workspace.azure_workspace_info:
        ws_host = f"https://{workspace.deployment_name}.azuredatabricks.net"
    # For GCP workspaces
    elif hasattr(workspace, 'gcp_managed_network_config'):
        ws_host = f"https://{workspace.workspace_id}.gcp.databricks.com"

    try:
        ws_client = WorkspaceClient(
            host=ws_host,
            client_id=SP_CREDENTIALS['client_id'],
            client_secret=SP_CREDENTIALS['client_secret'],
            auth_type="oauth-m2m"
        )
        return ws_client
    except Exception as e:
        print(f"   ⚠ Failed to create client for {workspace.workspace_name}: {e}")
        return None

print("Collection helper functions defined.")

# COMMAND ----------

# DBTITLE 1,Run Collection Using Permissions Analysis Tool Module
print("="*80)
print("Running Data Collection")
print("="*80)
print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Initialize data structures
all_vertices = []
all_edges = []

# Note: In MULTI_WORKSPACE_MODE, additional workspaces will be collected in Step 9 (Account-Level Collection)
if MULTI_WORKSPACE_MODE:
    print(f"\n🌐 Multi-workspace mode enabled")
    print(f"   Step 5-6: Collect from CURRENT workspace")
    print(f"   Step 9: Collect from ALL {len(workspaces_to_collect)} workspaces + account-level data")
else:
    print(f"\n📍 Single workspace mode: Collecting from current workspace only")

# ============================================================================
# IDENTITY COLLECTION
# ============================================================================

# Collect Users
if COLLECTION_CONFIG['collect_users']:
    print("\n1. Collecting Users...")
    try:
        users = list(w.users.list())
        for user in tqdm(users, desc="Users"):
            all_vertices.append({
                'id': str(user.id),
                'node_type': 'User',
                'name': safe_get(user, 'user_name'),
                'display_name': safe_get(user, 'display_name'),
                'email': user.emails[0].value if user.emails else None,
                'owner': None,
                'active': safe_get(user, 'active', True),
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': safe_json({'external_id': safe_get(user, 'external_id')})
            })
        print(f"    Collected {len(users)} users")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Groups
if COLLECTION_CONFIG['collect_groups']:
    print("\n2. Collecting Groups...")
    try:
        groups = list(w.groups.list())
        for group in tqdm(groups, desc="Groups"):
            all_vertices.append({
                'id': str(group.id),
                'node_type': 'Group',
                'name': safe_get(group, 'display_name'),
                'display_name': safe_get(group, 'display_name'),
                'email': None,
                'owner': None,
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': safe_json({'external_id': safe_get(group, 'external_id')})
            })

            # Collect memberships
            if hasattr(group, 'members') and group.members:
                for member in group.members:
                    all_edges.append({
                        'src': str(member.value),
                        'dst': str(group.id),
                        'relationship': 'MemberOf',
                        'permission_level': None,
                        'inherited': False,
                        'properties': None,
                        'created_at': datetime.now()
                    })
        print(f"    Collected {len(groups)} groups")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Service Principals
if COLLECTION_CONFIG['collect_service_principals']:
    print("\n3. Collecting Service Principals...")
    try:
        sps = list(w.service_principals.list())
        for sp in tqdm(sps, desc="Service Principals"):
            all_vertices.append({
                'id': str(sp.id),
                'node_type': 'ServicePrincipal',
                'name': safe_get(sp, 'application_id') or safe_get(sp, 'display_name'),
                'display_name': safe_get(sp, 'display_name'),
                'email': None,
                'application_id': safe_get(sp, 'application_id'),
                'owner': None,
                'active': safe_get(sp, 'active', True),
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': safe_json({'application_id': safe_get(sp, 'application_id')})
            })
        print(f"    Collected {len(sps)} service principals")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# COMPUTE COLLECTION
# ============================================================================

# Collect Clusters (only in single-workspace mode; multi-workspace mode collects in Step 9)
if COLLECTION_CONFIG['collect_clusters'] and not MULTI_WORKSPACE_MODE:
    print("\n4. Collecting Clusters...")
    try:
        clusters = list(w.clusters.list())
        for cluster in tqdm(clusters, desc="Clusters"):
            cluster_id = safe_get(cluster, 'cluster_id')
            all_vertices.append({
                'id': cluster_id,
                'node_type': 'Cluster',
                'name': safe_get(cluster, 'cluster_name'),
                'display_name': safe_get(cluster, 'cluster_name'),
                'email': None,
                'owner': safe_get(cluster, 'creator_user_name'),
                'active': safe_get(cluster, 'state') == 'RUNNING',
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({'spark_version': safe_get(cluster, 'spark_version')}),
                'metadata': safe_json({'state': safe_get(cluster, 'state')})
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("clusters", cluster_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = None
                            if acl.user_name:
                                principal = acl.user_name
                            elif acl.group_name:
                                principal = acl.group_name
                            elif acl.service_principal_name:
                                principal = acl.service_principal_name

                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': cluster_id,
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(clusters)} clusters")
    except Exception as e:
        print(f"    Error: {e}")
elif COLLECTION_CONFIG['collect_clusters'] and MULTI_WORKSPACE_MODE:
    print("\n4. Clusters: Skipped (collected per-workspace in Step 9)")

# Collect Instance Pools
if COLLECTION_CONFIG['collect_instance_pools']:
    print("\n5. Collecting Instance Pools...")
    try:
        pools = list(w.instance_pools.list())
        for pool in tqdm(pools, desc="Instance Pools"):
            pool_id = safe_get(pool, 'instance_pool_id')
            all_vertices.append({
                'id': pool_id,
                'node_type': 'InstancePool',
                'name': safe_get(pool, 'instance_pool_name'),
                'display_name': safe_get(pool, 'instance_pool_name'),
                'email': None,
                'owner': None,
                'active': safe_get(pool, 'state') == 'ACTIVE',
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({'node_type_id': safe_get(pool, 'node_type_id')}),
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("instance-pools", pool_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': pool_id,
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(pools)} instance pools")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Cluster Policies
if COLLECTION_CONFIG['collect_cluster_policies']:
    print("\n6. Collecting Cluster Policies...")
    try:
        policies = list(w.cluster_policies.list())
        for policy in tqdm(policies, desc="Cluster Policies"):
            policy_id = safe_get(policy, 'policy_id')
            all_vertices.append({
                'id': policy_id,
                'node_type': 'ClusterPolicy',
                'name': safe_get(policy, 'name'),
                'display_name': safe_get(policy, 'name'),
                'email': None,
                'owner': safe_get(policy, 'creator_user_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("cluster-policies", policy_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': policy_id,
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(policies)} cluster policies")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# AI/ML COLLECTION
# ============================================================================

# Collect Serving Endpoints
if COLLECTION_CONFIG['collect_serving_endpoints']:
    print("\n7. Collecting Serving Endpoints...")
    try:
        endpoints = list(w.serving_endpoints.list())
        for ep in tqdm(endpoints, desc="Serving Endpoints"):
            ep_name = safe_get(ep, 'name')
            all_vertices.append({
                'id': f"serving_endpoint:{ep_name}",
                'node_type': 'ServingEndpoint',
                'name': ep_name,
                'display_name': ep_name,
                'email': None,
                'owner': safe_get(ep, 'creator'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("serving-endpoints", ep_name)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': f"serving_endpoint:{ep_name}",
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(endpoints)} serving endpoints")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Vector Search Endpoints
if COLLECTION_CONFIG['collect_vector_search_endpoints']:
    print("\n8. Collecting Vector Search Endpoints...")
    try:
        vs_endpoints = list(w.vector_search_endpoints.list_endpoints())
        for ep in tqdm(vs_endpoints, desc="Vector Search Endpoints"):
            ep_name = safe_get(ep, 'name')
            all_vertices.append({
                'id': f"vs_endpoint:{ep_name}",
                'node_type': 'VectorSearchEndpoint',
                'name': ep_name,
                'display_name': ep_name,
                'email': None,
                'owner': safe_get(ep, 'creator'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })
        print(f"    Collected {len(vs_endpoints)} vector search endpoints")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Experiments
if COLLECTION_CONFIG['collect_experiments']:
    print("\n9. Collecting MLflow Experiments...")
    try:
        experiments = list(w.experiments.list_experiments())
        for exp in tqdm(experiments, desc="Experiments"):
            exp_id = safe_get(exp, 'experiment_id')
            all_vertices.append({
                'id': f"experiment:{exp_id}",
                'node_type': 'Experiment',
                'name': safe_get(exp, 'name'),
                'display_name': safe_get(exp, 'name'),
                'email': None,
                'owner': None,
                'active': safe_get(exp, 'lifecycle_stage') == 'active',
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("experiments", exp_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': f"experiment:{exp_id}",
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(experiments)} experiments")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# ANALYTICS/BI COLLECTION
# ============================================================================

# Collect Dashboards
if COLLECTION_CONFIG['collect_dashboards']:
    print("\n10. Collecting Dashboards...")
    try:
        dashboards = list(w.lakeview.list())
        for dash in tqdm(dashboards, desc="Dashboards"):
            dash_id = safe_get(dash, 'dashboard_id')
            all_vertices.append({
                'id': f"dashboard:{dash_id}",
                'node_type': 'Dashboard',
                'name': safe_get(dash, 'display_name'),
                'display_name': safe_get(dash, 'display_name'),
                'email': None,
                'owner': safe_get(dash, 'creator_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({'warehouse_id': safe_get(dash, 'warehouse_id')}),
                'metadata': None
            })
        print(f"    Collected {len(dashboards)} dashboards")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Queries
if COLLECTION_CONFIG['collect_queries']:
    print("\n11. Collecting SQL Queries...")
    try:
        queries = list(w.queries.list())
        for query in tqdm(queries, desc="Queries"):
            query_id = safe_get(query, 'id')
            all_vertices.append({
                'id': f"query:{query_id}",
                'node_type': 'Query',
                'name': safe_get(query, 'name') or safe_get(query, 'display_name'),
                'display_name': safe_get(query, 'name') or safe_get(query, 'display_name'),
                'email': None,
                'owner': safe_get(query, 'owner_user_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })
        print(f"    Collected {len(queries)} queries")
    except Exception as e:
        print(f"    Error: {e}")

# Collect Alerts
if COLLECTION_CONFIG['collect_alerts']:
    print("\n12. Collecting Alerts...")
    try:
        alerts = list(w.alerts.list())
        for alert in tqdm(alerts, desc="Alerts"):
            alert_id = safe_get(alert, 'id')
            all_vertices.append({
                'id': f"alert:{alert_id}",
                'node_type': 'Alert',
                'name': safe_get(alert, 'name') or safe_get(alert, 'display_name'),
                'display_name': safe_get(alert, 'name') or safe_get(alert, 'display_name'),
                'email': None,
                'owner': safe_get(alert, 'owner_user_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })
        print(f"    Collected {len(alerts)} alerts")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# ORCHESTRATION COLLECTION
# ============================================================================

# Collect Jobs (only in single-workspace mode; multi-workspace mode collects in Step 9)
if COLLECTION_CONFIG['collect_jobs'] and not MULTI_WORKSPACE_MODE:
    print("\n13. Collecting Jobs...")
    try:
        jobs = list(w.jobs.list())
        for job in tqdm(jobs, desc="Jobs"):
            job_id = str(safe_get(job, 'job_id'))
            job_name = safe_get(job.settings, 'name') if job.settings else f"Job {job_id}"
            all_vertices.append({
                'id': job_id,
                'node_type': 'Job',
                'name': job_name,
                'display_name': job_name,
                'email': None,
                'owner': safe_get(job, 'creator_user_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("jobs", job_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': job_id,
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(jobs)} jobs")
    except Exception as e:
        print(f"    Error: {e}")
elif COLLECTION_CONFIG['collect_jobs'] and MULTI_WORKSPACE_MODE:
    print("\n13. Jobs: Skipped (collected per-workspace in Step 9)")

# Collect Pipelines
if COLLECTION_CONFIG['collect_pipelines']:
    print("\n14. Collecting Pipelines (DLT)...")
    try:
        pipelines = list(w.pipelines.list_pipelines())
        for pipeline in tqdm(pipelines, desc="Pipelines"):
            pipeline_id = safe_get(pipeline, 'pipeline_id')
            all_vertices.append({
                'id': f"pipeline:{pipeline_id}",
                'node_type': 'Pipeline',
                'name': safe_get(pipeline, 'name'),
                'display_name': safe_get(pipeline, 'name'),
                'email': None,
                'owner': safe_get(pipeline, 'creator_user_name'),
                'active': safe_get(pipeline, 'state') in ['RUNNING', 'IDLE'],
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': None,
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("pipelines", pipeline_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': f"pipeline:{pipeline_id}",
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(pipelines)} pipelines")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# SQL WAREHOUSES
# ============================================================================

# Collect SQL Warehouses (only in single-workspace mode; multi-workspace mode collects in Step 9)
if COLLECTION_CONFIG['collect_warehouses'] and not MULTI_WORKSPACE_MODE:
    print("\n15. Collecting SQL Warehouses...")
    try:
        warehouses = list(w.warehouses.list())
        for wh in tqdm(warehouses, desc="Warehouses"):
            wh_id = safe_get(wh, 'id')
            all_vertices.append({
                'id': wh_id,
                'node_type': 'Warehouse',
                'name': safe_get(wh, 'name'),
                'display_name': safe_get(wh, 'name'),
                'email': None,
                'owner': None,
                'active': safe_get(wh, 'state') == 'RUNNING',
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({
                    'warehouse_type': safe_get(wh, 'warehouse_type'),
                    'cluster_size': safe_get(wh, 'cluster_size')
                }),
                'metadata': None
            })

            # Collect permissions
            if COLLECTION_CONFIG['collect_permissions']:
                try:
                    perms = w.permissions.get("sql/warehouses", wh_id)
                    if perms and perms.access_control_list:
                        for acl in perms.access_control_list:
                            principal = acl.user_name or acl.group_name or acl.service_principal_name
                            if principal and acl.all_permissions:
                                for perm in acl.all_permissions:
                                    all_edges.append({
                                        'src': principal,
                                        'dst': wh_id,
                                        'relationship': safe_get(perm, 'permission_level'),
                                        'permission_level': safe_get(perm, 'permission_level'),
                                        'inherited': safe_get(perm, 'inherited', False),
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                except:
                    pass
        print(f"    Collected {len(warehouses)} warehouses")
    except Exception as e:
        print(f"    Error: {e}")
elif COLLECTION_CONFIG['collect_warehouses'] and MULTI_WORKSPACE_MODE:
    print("\n15. SQL Warehouses: Skipped (collected per-workspace in Step 9)")

# ============================================================================
# SECURITY COLLECTION
# ============================================================================

# Collect Secret Scopes (only in single-workspace mode; multi-workspace mode collects in Step 9)
if COLLECTION_CONFIG['collect_secret_scopes'] and not MULTI_WORKSPACE_MODE:
    print("\n16. Collecting Secret Scopes...")
    try:
        scopes = list(w.secrets.list_scopes())
        for scope in tqdm(scopes, desc="Secret Scopes"):
            scope_name = safe_get(scope, 'name')
            all_vertices.append({
                'id': f"secret_scope:{scope_name}",
                'node_type': 'SecretScope',
                'name': scope_name,
                'display_name': scope_name,
                'email': None,
                'owner': None,
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({'backend_type': safe_get(scope, 'backend_type')}),
                'metadata': None
            })

            # Collect secrets in scope
            try:
                secrets = list(w.secrets.list_secrets(scope=scope_name))
                for secret in secrets:
                    secret_key = safe_get(secret, 'key')
                    all_vertices.append({
                        'id': f"secret:{scope_name}/{secret_key}",
                        'node_type': 'Secret',
                        'name': secret_key,
                        'display_name': secret_key,
                        'email': None,
                        'owner': None,
                        'active': True,
                        'created_at': None,
                        'updated_at': None,
                        'comment': None,
                        'properties': safe_json({'scope': scope_name}),
                        'metadata': None
                    })

                    # Add Contains edge
                    all_edges.append({
                        'src': f"secret_scope:{scope_name}",
                        'dst': f"secret:{scope_name}/{secret_key}",
                        'relationship': 'Contains',
                        'permission_level': None,
                        'inherited': False,
                        'properties': None,
                        'created_at': datetime.now()
                    })
            except:
                pass

            # Collect ACLs
            try:
                acls = list(w.secrets.list_acls(scope=scope_name))
                for acl in acls:
                    principal = safe_get(acl, 'principal')
                    permission = safe_get(acl, 'permission')
                    if principal and permission:
                        perm_map = {'MANAGE': 'CanManageSecret', 'WRITE': 'CanWriteSecret', 'READ': 'CanReadSecret'}
                        all_edges.append({
                            'src': principal,
                            'dst': f"secret_scope:{scope_name}",
                            'relationship': perm_map.get(permission, 'CanReadSecret'),
                            'permission_level': permission,
                            'inherited': False,
                            'properties': None,
                            'created_at': datetime.now()
                        })
            except:
                pass
        print(f"    Collected {len(scopes)} secret scopes")
    except Exception as e:
        print(f"    Error: {e}")
elif COLLECTION_CONFIG['collect_secret_scopes'] and MULTI_WORKSPACE_MODE:
    print("\n16. Secret Scopes: Skipped (collected per-workspace in Step 9)")

# Collect Tokens
if COLLECTION_CONFIG['collect_tokens']:
    print("\n17. Collecting Tokens...")
    try:
        tokens = list(w.tokens.list())
        for token in tqdm(tokens, desc="Tokens"):
            token_id = safe_get(token, 'token_id')
            all_vertices.append({
                'id': f"token:{token_id}",
                'node_type': 'Token',
                'name': safe_get(token, 'comment') or f"token-{token_id}",
                'display_name': safe_get(token, 'comment') or f"token-{token_id}",
                'email': None,
                'owner': safe_get(token, 'created_by_username'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': safe_get(token, 'comment'),
                'properties': None,
                'metadata': None
            })

            # Add owner edge
            owner = safe_get(token, 'created_by_username')
            if owner:
                all_edges.append({
                    'src': owner,
                    'dst': f"token:{token_id}",
                    'relationship': 'Owns',
                    'permission_level': None,
                    'inherited': False,
                    'properties': None,
                    'created_at': datetime.now()
                })
        print(f"    Collected {len(tokens)} tokens")
    except Exception as e:
        print(f"    Error: {e}")

# ============================================================================
# APPS COLLECTION
# ============================================================================

if COLLECTION_CONFIG['collect_apps']:
    print("\n18. Collecting Databricks Apps...")
    try:
        apps = list(w.apps.list())
        for app in tqdm(apps, desc="Apps"):
            app_name = safe_get(app, 'name')
            all_vertices.append({
                'id': f"app:{app_name}",
                'node_type': 'App',
                'name': app_name,
                'display_name': app_name,
                'email': None,
                'owner': safe_get(app, 'creator_name'),
                'active': True,
                'created_at': None,
                'updated_at': None,
                'comment': None,
                'properties': safe_json({'url': safe_get(app, 'url')}),
                'metadata': None
            })
        print(f"    Collected {len(apps)} apps")
    except Exception as e:
        print(f"    Error: {e}")

print(f"\n Collection Phase 1 Complete!")
print(f"   Vertices: {len(all_vertices)}")
print(f"   Edges: {len(all_edges)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Collect Unity Catalog Objects & Grants

# COMMAND ----------

# DBTITLE 1,Collect Unity Catalog with SHOW GRANTS
print("="*80)
print("Collecting Unity Catalog Objects & Grants")
print("="*80)

if COLLECTION_CONFIG['collect_unity_catalog']:

    # Get catalogs
    catalogs = list(w.catalogs.list())

    # Filter system catalogs
    catalogs = [c for c in catalogs if c.name not in ['system', '__databricks_internal']]

    # Apply limit if configured
    if COLLECTION_CONFIG['max_catalogs']:
        catalogs = catalogs[:COLLECTION_CONFIG['max_catalogs']]

    print(f"\nFound {len(catalogs)} catalogs (excluding system)")

    grant_count = 0

    for cat in tqdm(catalogs, desc="Catalogs"):
        cat_name = cat.name

        # Add catalog vertex
        all_vertices.append({
            'id': cat_name,
            'node_type': 'Catalog',
            'name': cat_name,
            'display_name': cat_name,
            'email': None,
            'owner': safe_get(cat, 'owner'),
            'active': True,
            'created_at': datetime.fromtimestamp(cat.created_at / 1000) if cat.created_at else None,
            'updated_at': datetime.fromtimestamp(cat.updated_at / 1000) if cat.updated_at else None,
            'comment': safe_get(cat, 'comment'),
            'properties': safe_json(cat.properties) if cat.properties else None,
            'metadata': safe_json({'metastore_id': safe_get(cat, 'metastore_id')})
        })

        # Collect catalog grants using SHOW GRANTS
        if COLLECTION_CONFIG['collect_permissions']:
            try:
                grants_df = spark.sql(f"SHOW GRANTS ON CATALOG `{cat_name}`")
                for grant in grants_df.collect():
                    principal = grant.Principal if hasattr(grant, 'Principal') else grant.principal
                    action_type = grant.ActionType if hasattr(grant, 'ActionType') else grant.action_type

                    all_edges.append({
                        'src': principal,
                        'dst': cat_name,
                        'relationship': action_type,
                        'permission_level': action_type,
                        'inherited': False,
                        'properties': None,
                        'created_at': datetime.now()
                    })
                    grant_count += 1
            except:
                pass

        # Collect schemas
        try:
            schemas = list(w.schemas.list(catalog_name=cat_name))

            if COLLECTION_CONFIG['max_schemas_per_catalog']:
                schemas = schemas[:COLLECTION_CONFIG['max_schemas_per_catalog']]

            for schema in schemas:
                schema_id = f"{cat_name}.{schema.name}"

                # Add schema vertex
                all_vertices.append({
                    'id': schema_id,
                    'node_type': 'Schema',
                    'name': schema_id,
                    'display_name': schema.name,
                    'email': None,
                    'owner': safe_get(schema, 'owner'),
                    'active': True,
                    'created_at': datetime.fromtimestamp(schema.created_at / 1000) if schema.created_at else None,
                    'updated_at': datetime.fromtimestamp(schema.updated_at / 1000) if schema.updated_at else None,
                    'comment': safe_get(schema, 'comment'),
                    'properties': safe_json(schema.properties) if schema.properties else None,
                    'metadata': safe_json({'catalog_name': cat_name})
                })

                # Add Contains edge: Catalog -> Schema
                all_edges.append({
                    'src': cat_name,
                    'dst': schema_id,
                    'relationship': 'Contains',
                    'permission_level': None,
                    'inherited': False,
                    'properties': None,
                    'created_at': datetime.now()
                })

                # Collect schema grants
                if COLLECTION_CONFIG['collect_permissions']:
                    try:
                        grants_df = spark.sql(f"SHOW GRANTS ON SCHEMA `{cat_name}`.`{schema.name}`")
                        for grant in grants_df.collect():
                            principal = grant.Principal if hasattr(grant, 'Principal') else grant.principal
                            action_type = grant.ActionType if hasattr(grant, 'ActionType') else grant.action_type

                            all_edges.append({
                                'src': principal,
                                'dst': schema_id,
                                'relationship': action_type,
                                'permission_level': action_type,
                                'inherited': False,
                                'properties': None,
                                'created_at': datetime.now()
                            })
                            grant_count += 1
                    except:
                        pass

                # Collect tables
                try:
                    tables = list(w.tables.list(catalog_name=cat_name, schema_name=schema.name))

                    if COLLECTION_CONFIG['max_tables_per_schema']:
                        tables = tables[:COLLECTION_CONFIG['max_tables_per_schema']]

                    for table in tables:
                        table_id = f"{cat_name}.{schema.name}.{table.name}"
                        table_type = safe_get(table, 'table_type')
                        node_type = 'View' if table_type and 'VIEW' in str(table_type).upper() else 'Table'

                        # Add table vertex
                        all_vertices.append({
                            'id': table_id,
                            'node_type': node_type,
                            'name': table_id,
                            'display_name': table.name,
                            'email': None,
                            'owner': safe_get(table, 'owner'),
                            'active': True,
                            'created_at': datetime.fromtimestamp(table.created_at / 1000) if table.created_at else None,
                            'updated_at': datetime.fromtimestamp(table.updated_at / 1000) if table.updated_at else None,
                            'comment': safe_get(table, 'comment'),
                            'properties': safe_json(table.properties) if table.properties else None,
                            'metadata': safe_json({
                                'table_type': str(table_type),
                                'data_source_format': safe_get(table, 'data_source_format')
                            })
                        })

                        # Add Contains edge: Schema -> Table
                        all_edges.append({
                            'src': schema_id,
                            'dst': table_id,
                            'relationship': 'Contains',
                            'permission_level': None,
                            'inherited': False,
                            'properties': None,
                            'created_at': datetime.now()
                        })

                        # Collect table grants
                        if COLLECTION_CONFIG['collect_permissions']:
                            try:
                                grants_df = spark.sql(f"SHOW GRANTS ON TABLE `{cat_name}`.`{schema.name}`.`{table.name}`")
                                for grant in grants_df.collect():
                                    principal = grant.Principal if hasattr(grant, 'Principal') else grant.principal
                                    action_type = grant.ActionType if hasattr(grant, 'ActionType') else grant.action_type

                                    all_edges.append({
                                        'src': principal,
                                        'dst': table_id,
                                        'relationship': action_type,
                                        'permission_level': action_type,
                                        'inherited': False,
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                                    grant_count += 1
                            except:
                                pass
                except:
                    pass
        except:
            pass

    print(f"\n Unity Catalog collection complete!")
    print(f"   Total grants collected: {grant_count}")
else:
    print("\n Unity Catalog collection disabled")

print(f"\n Total Vertices: {len(all_vertices)}")
print(f" Total Edges: {len(all_edges)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7: Save to Delta Lake

# COMMAND ----------

# DBTITLE 1,Prepare and Save DataFrames
print("="*80)
print("Saving to Delta Lake")
print("="*80)

# Define schemas (run_id added for point-in-time snapshots)
vertices_schema = StructType([
    StructField("run_id", StringType(), False),  # Collection run identifier
    StructField("id", StringType(), False),
    StructField("node_type", StringType(), False),
    StructField("name", StringType(), True),
    StructField("display_name", StringType(), True),
    StructField("owner", StringType(), True),
    StructField("email", StringType(), True),
    StructField("application_id", StringType(), True),  # For service principals
    StructField("active", BooleanType(), True),
    StructField("created_at", TimestampType(), True),
    StructField("updated_at", TimestampType(), True),
    StructField("comment", StringType(), True),
    StructField("properties", StringType(), True),
    StructField("metadata", StringType(), True),
])

edges_schema = StructType([
    StructField("run_id", StringType(), False),  # Collection run identifier
    StructField("src", StringType(), False),
    StructField("dst", StringType(), False),
    StructField("relationship", StringType(), False),
    StructField("permission_level", StringType(), True),
    StructField("inherited", BooleanType(), True),
    StructField("properties", StringType(), True),
    StructField("created_at", TimestampType(), True),
])

# Add run_id to all vertices and edges
print(f"\n Adding run_id '{RUN_ID}' to all records...")
for v in all_vertices:
    v['run_id'] = RUN_ID
for e in all_edges:
    e['run_id'] = RUN_ID

# Create DataFrames
print("\n Creating DataFrames...")
vertices_df = spark.createDataFrame(all_vertices, schema=vertices_schema)
edges_df = spark.createDataFrame(all_edges, schema=edges_schema)

print(f"   Vertices: {vertices_df.count():,}")
print(f"   Edges: {edges_df.count():,}")

# Save vertices (append mode for point-in-time snapshots)
print(f"\n Saving vertices to {VERTICES_TABLE}...")
vertices_df.write \
    .format("delta") \
    .mode("append") \
    .saveAsTable(VERTICES_TABLE)
print(f"    Vertices saved!")

# Save edges (append mode for point-in-time snapshots)
print(f"\n Saving edges to {EDGES_TABLE}...")
edges_df.write \
    .format("delta") \
    .mode("append") \
    .saveAsTable(EDGES_TABLE)
print(f"    Edges saved!")

# Save collection metadata (timestamp and statistics)
print(f"\n Saving collection metadata to {COLLECTION_METADATA_TABLE}...")
collection_time = datetime.now()

# Build workspace collection summary
workspaces_collected = []
workspaces_failed = []
if MULTI_WORKSPACE_MODE:
    for ws_id, ws_info in WORKSPACE_COLLECTION_STATUS.items():
        if ws_info.get('status') == 'success':
            workspaces_collected.append(ws_info['name'])
        elif ws_info.get('status') == 'failed':
            workspaces_failed.append(ws_info['name'])
else:
    workspaces_collected = [current_workspace_url]

metadata = [{
    'run_id': RUN_ID,
    'collection_timestamp': collection_time,
    'vertices_count': str(vertices_df.count()),
    'edges_count': str(edges_df.count()),
    'collected_by': current_user.user_name if current_user else 'unknown',
    'collection_config': json.dumps({k: v for k, v in COLLECTION_CONFIG.items() if not k.startswith('output')}),
    'workspaces_collected': json.dumps(workspaces_collected),
    'workspaces_failed': json.dumps(workspaces_failed),
    'workspace_status': json.dumps(WORKSPACE_COLLECTION_STATUS) if MULTI_WORKSPACE_MODE else None,
    'collection_mode': 'multi-workspace' if MULTI_WORKSPACE_MODE else 'single-workspace'
}]

metadata_schema = StructType([
    StructField("run_id", StringType(), False),
    StructField("collection_timestamp", TimestampType(), False),
    StructField("vertices_count", StringType(), True),
    StructField("edges_count", StringType(), True),
    StructField("collected_by", StringType(), True),
    StructField("collection_config", StringType(), True),
    StructField("workspaces_collected", StringType(), True),
    StructField("workspaces_failed", StringType(), True),
    StructField("workspace_status", StringType(), True),
    StructField("collection_mode", StringType(), True),
])
metadata_df = spark.createDataFrame(metadata, schema=metadata_schema)
metadata_df.write \
    .format("delta") \
    .mode("append") \
    .saveAsTable(COLLECTION_METADATA_TABLE)
print(f"    Metadata saved!")
print(f"    Collection timestamp: {collection_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"    Workspaces collected: {len(workspaces_collected)}")
if workspaces_failed:
    print(f"    ⚠ Workspaces failed: {len(workspaces_failed)} - {', '.join(workspaces_failed)}")

# ============================================================================
# DATA RETENTION - Cleanup old runs based on retention_days setting
# ============================================================================
retention_days = COLLECTION_CONFIG.get('retention_days', 30)
print(f"\n🗑️ Applying data retention policy (retention_days={retention_days})...")

if retention_days == -1:
    print("   Retention: Keep forever - no cleanup")
elif retention_days in (0, 1):
    # Keep only the latest run (current one)
    print("   Retention: Keep only latest run - deleting all previous runs...")
    try:
        spark.sql(f"DELETE FROM {VERTICES_TABLE} WHERE run_id != '{RUN_ID}'")
        spark.sql(f"DELETE FROM {EDGES_TABLE} WHERE run_id != '{RUN_ID}'")
        spark.sql(f"DELETE FROM {COLLECTION_METADATA_TABLE} WHERE run_id != '{RUN_ID}'")
        print("   ✓ Previous runs deleted")
    except Exception as e:
        print(f"   ⚠ Cleanup error: {e}")
else:
    # Delete runs older than N days
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    print(f"   Retention: Delete runs older than {retention_days} days (before {cutoff_date.strftime('%Y-%m-%d')})...")
    try:
        # Get run_ids to delete from metadata table
        old_runs_df = spark.sql(f"""
            SELECT run_id FROM {COLLECTION_METADATA_TABLE}
            WHERE collection_timestamp < '{cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}'
        """)
        old_run_ids = [row.run_id for row in old_runs_df.collect()]

        if old_run_ids:
            run_ids_str = "', '".join(old_run_ids)
            spark.sql(f"DELETE FROM {VERTICES_TABLE} WHERE run_id IN ('{run_ids_str}')")
            spark.sql(f"DELETE FROM {EDGES_TABLE} WHERE run_id IN ('{run_ids_str}')")
            spark.sql(f"DELETE FROM {COLLECTION_METADATA_TABLE} WHERE run_id IN ('{run_ids_str}')")
            print(f"   ✓ Deleted {len(old_run_ids)} old run(s)")
        else:
            print("   ✓ No old runs to delete")
    except Exception as e:
        print(f"   ⚠ Cleanup error: {e}")

print(f"\n SUCCESS! Graph data saved to {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8: Verify Collection

# COMMAND ----------

# DBTITLE 1,Verify Saved Data
print("="*80)
print("Verification")
print("="*80)

# Load saved tables
vertices_saved = spark.table(VERTICES_TABLE)
edges_saved = spark.table(EDGES_TABLE)

print(f"\n Saved Data:")
print(f"  Vertices: {vertices_saved.count():,}")
print(f"  Edges: {edges_saved.count():,}")

# Verify vertices by type
print(f"\n Vertices by type:")
display(vertices_saved.groupBy("node_type").count().orderBy(F.desc("count")))

# Verify edges by relationship
print(f"\n Edges by relationship:")
display(edges_saved.groupBy("relationship").count().orderBy(F.desc("count")))

# Critical check: permission grants
permission_grants = edges_saved.filter(F.col("permission_level").isNotNull())
grant_count = permission_grants.count()

print(f"\n Permission Grants: {grant_count:,}")

if grant_count == 0:
    print("\n CRITICAL: No permission grants saved!")
    print("   Permission analysis will NOT work.")
else:
    print(f"\n SUCCESS! {grant_count} permission grants saved")
    print("\n Permission types:")
    display(permission_grants.groupBy("permission_level").count().orderBy(F.desc("count")))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Collection Scope Reference
# MAGIC
# MAGIC The following object types are now collected:
# MAGIC
# MAGIC | Category | Objects |
# MAGIC |----------|---------|
# MAGIC | **Identity** | Users, Groups, Service Principals |
# MAGIC | **Compute** | Clusters, Instance Pools, Cluster Policies, Global Init Scripts |
# MAGIC | **AI/ML** | Serving Endpoints, Vector Search Endpoints/Indexes, Registered Models, Experiments |
# MAGIC | **Analytics/BI** | Dashboards, SQL Queries, Alerts |
# MAGIC | **Development** | Notebooks, Repos |
# MAGIC | **Orchestration** | Jobs, Pipelines (DLT) |
# MAGIC | **Data & Analytics** | SQL Warehouses, Metastores, Catalogs, Schemas, Tables, Views, Volumes, Functions, External Locations, Storage Credentials, Connections |
# MAGIC | **Security** | Secret Scopes, Secrets, Tokens, IP Access Lists |
# MAGIC | **Apps** | Databricks Apps |
# MAGIC | **Account-Level** | Workspaces, Account Users/Groups/SPs, Workspace Assignments |
# MAGIC
# MAGIC Run the analysis notebooks (02-06) to analyze this data!

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Step 9: Account-Level & Multi-Workspace Collection
# MAGIC
# MAGIC This step collects:
# MAGIC - **Account-level objects**: Workspaces, Account Users/Groups/SPs, Metastores, Workspace Assignments
# MAGIC - **Multi-workspace data**: Users, Groups, Jobs from ALL workspaces using SP credentials
# MAGIC
# MAGIC **Requirements:**
# MAGIC - Service Principal with **Account Admin** role
# MAGIC - SP added as **Admin** to each workspace you want to collect from
# MAGIC - Secrets configured in scope "brickhound" (see 00_config for detailed setup)
# MAGIC
# MAGIC **Note:** If SP credentials were loaded in Step 4, this step will:
# MAGIC 1. Collect account-level objects
# MAGIC 2. Iterate over ALL workspaces and collect Users, Groups, Jobs from each

# COMMAND ----------

# DBTITLE 1,Account-Level & Multi-Workspace Collection
if COLLECTION_CONFIG.get('collect_account_level', False):
    import traceback

    print("="*80)
    print("Account-Level & Multi-Workspace Collection")
    print("="*80)

    # Use credentials loaded in Step 4 (or try to load them now if not available)
    if MULTI_WORKSPACE_MODE and SP_CREDENTIALS.get('account_id'):
        ACCOUNT_ID = SP_CREDENTIALS['account_id']
        SP_CLIENT_ID = SP_CREDENTIALS['client_id']
        SP_CLIENT_SECRET = SP_CREDENTIALS['client_secret']
        print("✓ Using credentials loaded in Step 4")
    else:
        # Try to load credentials from secrets (using SAT secret key names)
        try:
            ACCOUNT_ID = dbutils.secrets.get(scope=secrets_scope, key="account-console-id")
            SP_CLIENT_ID = dbutils.secrets.get(scope=secrets_scope, key="client-id")
            SP_CLIENT_SECRET = dbutils.secrets.get(scope=secrets_scope, key="client-secret")
            print(f"✓ Loaded credentials from secrets scope '{secrets_scope}'")
        except:
            ACCOUNT_ID = ""
            SP_CLIENT_ID = ""
            SP_CLIENT_SECRET = ""
            print("⚠ No credentials available")

    if ACCOUNT_ID and SP_CLIENT_ID and SP_CLIENT_SECRET:
        try:
            # Reuse account host determined during initialization (Step 4)
            # If not available (credentials loaded directly here), compute it using helper functions
            if SP_CREDENTIALS.get('account_host'):
                account_host = SP_CREDENTIALS['account_host']
            else:
                # Fallback: compute account host using domain-aware logic
                workspace_url = spark.conf.get("spark.databricks.workspaceUrl", "")
                domain = get_domain_from_url(workspace_url)
                cloud_type = parse_cloud_type(workspace_url)

                if cloud_type == 'azure':
                    account_host = f"https://accounts.azuredatabricks.{domain}"
                elif cloud_type == 'gcp':
                    account_host = f"https://accounts.gcp.databricks.{domain}"
                else:  # aws
                    account_host = f"https://accounts.cloud.databricks.{domain}"

            print(f"\n📡 Connecting to {account_host}")
            print(f"   Account ID: {ACCOUNT_ID}")
            print(f"   Client ID: {SP_CLIENT_ID[:8]}...")

            # Initialize Account Client with explicit OAuth M2M auth type
            account = AccountClient(
                host=account_host,
                account_id=ACCOUNT_ID,
                client_id=SP_CLIENT_ID,
                client_secret=SP_CLIENT_SECRET,
                auth_type="oauth-m2m"
            )

            # Test connection
            print(f"\n🔍 Testing connection by listing workspaces...")
            workspaces = list(account.workspaces.list())
            print(f"✓ Connected! Found {len(workspaces)} workspaces")

            # ================================================================
            # Collect Workspaces
            # ================================================================
            print("\n📦 Collecting Workspaces...")
            for ws in tqdm(workspaces, desc="Workspaces"):
                ws_id = str(ws.workspace_id)
                all_vertices.append({
                    'id': f"workspace:{ws_id}",
                    'node_type': 'Workspace',
                    'name': ws.workspace_name,
                    'display_name': ws.workspace_name,
                    'email': None,
                    'owner': None,
                    'active': ws.workspace_status.value == 'RUNNING' if hasattr(ws.workspace_status, 'value') else True,
                    'created_at': None,
                    'updated_at': None,
                    'comment': None,
                    'properties': safe_json({
                        'deployment_name': ws.deployment_name,
                        'cloud': ws.cloud,
                        'region': ws.aws_region if hasattr(ws, 'aws_region') else ws.location if hasattr(ws, 'location') else None
                    }),
                    'metadata': safe_json({'workspace_id': ws_id})
                })
            print(f"   ✓ Collected {len(workspaces)} workspaces")

            # ================================================================
            # Collect Account Users (with full details including roles)
            # ================================================================
            print("\n👥 Collecting Account Users...")
            account_admin_count = 0
            try:
                # First get list of all users
                account_users_list = list(account.users.list())
                account_users = []

                # Fetch full details for each user including roles
                for user in tqdm(account_users_list, desc="Fetching User Details"):
                    try:
                        full_user = account.users.get(user.id)
                        account_users.append(full_user)
                    except Exception as e:
                        print(f"   ⚠ Error getting details for user {user.id}: {e}")
                        account_users.append(user)  # Fall back to basic info

                for user in tqdm(account_users, desc="Account Users"):
                    user_id = f"account_user:{user.id}"

                    # Extract roles for metadata
                    user_roles = []
                    if hasattr(user, 'roles') and user.roles:
                        user_roles = [r.value for r in user.roles if hasattr(r, 'value')]

                    all_vertices.append({
                        'id': user_id,
                        'node_type': 'AccountUser',
                        'name': user.user_name,
                        'display_name': user.display_name,
                        'email': user.emails[0].value if user.emails else None,
                        'owner': None,
                        'active': user.active if hasattr(user, 'active') else True,
                        'created_at': None,
                        'updated_at': None,
                        'comment': None,
                        'properties': None,
                        'metadata': safe_json({
                            'external_id': user.external_id if hasattr(user, 'external_id') else None,
                            'roles': user_roles
                        })
                    })

                    # Check for account_admin role and create AccountAdmin edge
                    if 'account_admin' in user_roles:
                        all_edges.append({
                            'src': user_id,
                            'dst': f"account:{ACCOUNT_ID}",
                            'relationship': 'AccountAdmin',
                            'permission_level': None,
                            'inherited': False,
                            'created_at': None,
                            'properties': None
                        })
                        account_admin_count += 1
                        print(f"   👑 Found Account Admin: {user.user_name}")

                print(f"   ✓ Collected {len(account_users)} account users")
                if account_admin_count > 0:
                    print(f"   👑 Found {account_admin_count} Account Admins")
            except Exception as e:
                print(f"   ⚠ Error collecting account users: {e}")

            # ================================================================
            # Collect Account Groups (with full member details)
            # ================================================================
            print("\n👥 Collecting Account Groups...")
            try:
                # First get list of all groups (groups.list() doesn't return members)
                account_groups_list = list(account.groups.list())
                account_groups = []

                # Fetch full details for each group including members
                for group in tqdm(account_groups_list, desc="Fetching Group Details"):
                    try:
                        full_group = account.groups.get(group.id)
                        account_groups.append(full_group)
                    except Exception as e:
                        print(f"   ⚠ Error getting details for group {group.id}: {e}")
                        account_groups.append(group)  # Fall back to basic info

                for group in tqdm(account_groups, desc="Account Groups"):
                    group_id = f"account_group:{group.id}"
                    group_name = group.display_name
                    all_vertices.append({
                        'id': group_id,
                        'node_type': 'AccountGroup',
                        'name': group_name,
                        'display_name': group_name,
                        'email': None,
                        'owner': None,
                        'active': True,
                        'created_at': None,
                        'updated_at': None,
                        'comment': None,
                        'properties': None,
                        'metadata': None
                    })

                    # Collect memberships (now available from groups.get())
                    if hasattr(group, 'members') and group.members:
                        for member in group.members:
                            member_type = member.type if hasattr(member, 'type') else None
                            ref = member.ref if hasattr(member, 'ref') else ''

                            # Determine member type and prefix
                            # Use consistent prefixes: account_user, account_group, account_sp
                            if member_type == 'User' or 'Users' in str(ref):
                                member_prefix = 'account_user'
                            elif member_type == 'Group' or 'Groups' in str(ref):
                                member_prefix = 'account_group'
                            elif member_type == 'ServicePrincipal' or 'ServicePrincipals' in str(ref):
                                member_prefix = 'account_sp'
                            else:
                                member_prefix = 'account_user'  # Default

                            prefixed_member_id = f"{member_prefix}:{member.value}"

                            # MemberOf edge with prefixed IDs (member -> group by ID)
                            all_edges.append({
                                'src': prefixed_member_id,
                                'dst': group_id,
                                'relationship': 'MemberOf',
                                'permission_level': None,
                                'inherited': False,
                                'properties': None,
                                'created_at': datetime.now()
                            })

                            # Also add MemberOf edge using group name as dst for query flexibility
                            all_edges.append({
                                'src': prefixed_member_id,
                                'dst': group_name,
                                'relationship': 'MemberOf',
                                'permission_level': None,
                                'inherited': False,
                                'properties': None,
                                'created_at': datetime.now()
                            })
                print(f"   ✓ Collected {len(account_groups)} account groups")
            except Exception as e:
                print(f"   ⚠ Error collecting account groups: {e}")

            # ================================================================
            # Collect Account Service Principals (with full details including roles)
            # ================================================================
            print("\n🤖 Collecting Account Service Principals...")
            sp_admin_count = 0
            try:
                # First get list of all service principals
                account_sps_list = list(account.service_principals.list())
                account_sps = []

                # Fetch full details for each SP including roles
                for sp in tqdm(account_sps_list, desc="Fetching SP Details"):
                    try:
                        full_sp = account.service_principals.get(sp.id)
                        account_sps.append(full_sp)
                    except Exception as e:
                        print(f"   ⚠ Error getting details for SP {sp.id}: {e}")
                        account_sps.append(sp)  # Fall back to basic info

                for sp in tqdm(account_sps, desc="Account SPs"):
                    sp_id = f"account_sp:{sp.id}"

                    # Extract roles for metadata
                    sp_roles = []
                    if hasattr(sp, 'roles') and sp.roles:
                        sp_roles = [r.value for r in sp.roles if hasattr(r, 'value')]

                    all_vertices.append({
                        'id': sp_id,
                        'node_type': 'AccountServicePrincipal',
                        'name': sp.display_name or sp.application_id,
                        'display_name': sp.display_name,
                        'email': None,
                        'application_id': sp.application_id,
                        'owner': None,
                        'active': sp.active if hasattr(sp, 'active') else True,
                        'created_at': None,
                        'updated_at': None,
                        'comment': None,
                        'properties': None,
                        'metadata': safe_json({
                            'application_id': sp.application_id,
                            'roles': sp_roles
                        })
                    })

                    # Check for account_admin role and create AccountAdmin edge
                    if 'account_admin' in sp_roles:
                        all_edges.append({
                            'src': sp_id,
                            'dst': f"account:{ACCOUNT_ID}",
                            'relationship': 'AccountAdmin',
                            'permission_level': None,
                            'inherited': False,
                            'created_at': None,
                            'properties': None
                        })
                        sp_admin_count += 1
                        print(f"   👑 Found Account Admin SP: {sp.display_name}")

                print(f"   ✓ Collected {len(account_sps)} account service principals")
                if sp_admin_count > 0:
                    print(f"   👑 Found {sp_admin_count} Account Admin Service Principals")
            except Exception as e:
                print(f"   ⚠ Error collecting account service principals: {e}")

            # ================================================================
            # Collect Workspace Assignments
            # ================================================================
            print("\n🔗 Collecting Workspace Assignments...")
            assignment_count = 0
            for ws in tqdm(workspaces, desc="Workspace Assignments"):
                try:
                    assignments = list(account.workspace_assignment.list(workspace_id=ws.workspace_id))
                    for assignment in assignments:
                        principal_id = assignment.principal.principal_id

                        # Determine source node based on which name field is populated
                        # The API returns group_name, user_name, or service_principal_name
                        # to indicate the principal type (no principal_type field exists)
                        if hasattr(assignment.principal, 'group_name') and assignment.principal.group_name:
                            src = f"account_group:{principal_id}"
                        elif hasattr(assignment.principal, 'service_principal_name') and assignment.principal.service_principal_name:
                            src = f"account_sp:{principal_id}"
                        else:
                            # Default to user (user_name is populated)
                            src = f"account_user:{principal_id}"

                        all_edges.append({
                            'src': src,
                            'dst': f"workspace:{ws.workspace_id}",
                            'relationship': 'WorkspaceAccess',
                            'permission_level': 'WORKSPACE_ACCESS',
                            'inherited': False,
                            'properties': None,
                            'created_at': datetime.now()
                        })
                        assignment_count += 1
                except Exception as e:
                    pass  # Some workspaces may not allow listing assignments
            print(f"   ✓ Collected {assignment_count} workspace assignments")

            # ================================================================
            # Collect Metastores
            # ================================================================
            print("\n🗄️ Collecting Metastores...")
            try:
                metastores = list(account.metastores.list())
                for ms in tqdm(metastores, desc="Metastores"):
                    ms_id = ms.metastore_id
                    all_vertices.append({
                        'id': f"metastore:{ms_id}",
                        'node_type': 'Metastore',
                        'name': ms.name,
                        'display_name': ms.name,
                        'email': None,
                        'owner': ms.owner if hasattr(ms, 'owner') else None,
                        'active': True,
                        'created_at': datetime.fromtimestamp(ms.created_at / 1000) if ms.created_at else None,
                        'updated_at': datetime.fromtimestamp(ms.updated_at / 1000) if ms.updated_at else None,
                        'comment': None,
                        'properties': safe_json({
                            'region': ms.region if hasattr(ms, 'region') else None,
                            'cloud': ms.cloud if hasattr(ms, 'cloud') else None
                        }),
                        'metadata': safe_json({'metastore_id': ms_id})
                    })
                print(f"   ✓ Collected {len(metastores)} metastores")

                # Collect metastore assignments
                print("\n🔗 Collecting Metastore Assignments...")
                ms_assignment_count = 0
                for ws in workspaces:
                    try:
                        ms_assignment = account.metastore_assignments.get(workspace_id=ws.workspace_id)
                        if ms_assignment and ms_assignment.metastore_id:
                            all_edges.append({
                                'src': f"workspace:{ws.workspace_id}",
                                'dst': f"metastore:{ms_assignment.metastore_id}",
                                'relationship': 'UsesMetastore',
                                'permission_level': None,
                                'inherited': False,
                                'properties': None,
                                'created_at': datetime.now()
                            })
                            ms_assignment_count += 1
                    except:
                        pass
                print(f"   ✓ Collected {ms_assignment_count} metastore assignments")
            except Exception as e:
                print(f"   ⚠ Error collecting metastores: {e}")

            # ================================================================
            # Collect Workspace-Level Data from ALL Workspaces
            # ================================================================
            print("\n" + "="*60)
            print("🌐 COLLECTING WORKSPACE-LEVEL DATA FROM ALL WORKSPACES")
            print("="*60)
            print(f"   This will collect Users, Groups, Jobs, Notebooks from {len(workspaces)} workspaces")

            # Skip the current workspace since we already collected from it
            current_ws_url = spark.conf.get("spark.databricks.workspaceUrl", "").lower()

            for ws_idx, ws in enumerate(workspaces):
                ws_name = ws.workspace_name
                ws_id = str(ws.workspace_id)  # Convert to string for consistent dict keys

                # Build workspace URL
                if ws.azure_workspace_info:
                    ws_host = f"https://{ws.deployment_name}.azuredatabricks.net"
                elif hasattr(ws, 'gcp_managed_network_config') and ws.gcp_managed_network_config:
                    ws_host = f"https://{ws.workspace_id}.gcp.databricks.com"
                else:
                    ws_host = f"https://{ws.deployment_name}.cloud.databricks.com"

                # Check if this is the current workspace
                is_current_workspace = ws_host.lower().replace("https://", "") in current_ws_url or current_ws_url in ws_host.lower()

                print(f"\n   [{ws_idx+1}/{len(workspaces)}] {ws_name}{' (current workspace)' if is_current_workspace else ''}")
                print(f"      URL: {ws_host}")

                # Initialize status tracking if not already present
                if ws_id not in WORKSPACE_COLLECTION_STATUS:
                    WORKSPACE_COLLECTION_STATUS[ws_id] = {'name': ws_name, 'status': 'pending', 'error': None}

                try:
                    # Create WorkspaceClient for this workspace using SP credentials
                    ws_client = WorkspaceClient(
                        host=ws_host,
                        client_id=SP_CREDENTIALS['client_id'],
                        client_secret=SP_CREDENTIALS['client_secret'],
                        auth_type="oauth-m2m"
                    )

                    # Collect Users from this workspace
                    print(f"      Collecting Users...")
                    try:
                        ws_users = list(ws_client.users.list())
                        for user in ws_users:
                            all_vertices.append({
                                'id': f"ws_{ws_id}_user:{user.id}",
                                'node_type': 'User',
                                'name': safe_get(user, 'user_name'),
                                'display_name': safe_get(user, 'display_name'),
                                'email': user.emails[0].value if user.emails else None,
                                'owner': None,
                                'active': safe_get(user, 'active', True),
                                'created_at': None,
                                'updated_at': None,
                                'comment': None,
                                'properties': safe_json({'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                'metadata': None
                            })
                        print(f"      ✓ {len(ws_users)} users")
                    except Exception as e:
                        print(f"      ⚠ Users: {e}")

                    # Collect Groups from this workspace
                    print(f"      Collecting Groups...")
                    try:
                        ws_groups = list(ws_client.groups.list())
                        for group in ws_groups:
                            group_id = f"ws_{ws_id}_group:{group.id}"
                            all_vertices.append({
                                'id': group_id,
                                'node_type': 'Group',
                                'name': safe_get(group, 'display_name'),
                                'display_name': safe_get(group, 'display_name'),
                                'email': None,
                                'owner': None,
                                'active': True,
                                'created_at': None,
                                'updated_at': None,
                                'comment': None,
                                'properties': safe_json({'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                'metadata': None
                            })
                            # Collect group memberships
                            if hasattr(group, 'members') and group.members:
                                for member in group.members:
                                    all_edges.append({
                                        'src': f"ws_{ws_id}_user:{member.value}" if 'User' in str(member.type) else f"ws_{ws_id}_group:{member.value}",
                                        'dst': group_id,
                                        'relationship': 'MemberOf',
                                        'permission_level': None,
                                        'inherited': False,
                                        'properties': None,
                                        'created_at': datetime.now()
                                    })
                        print(f"      ✓ {len(ws_groups)} groups")
                    except Exception as e:
                        print(f"      ⚠ Groups: {e}")

                    # Collect Jobs from this workspace (important for escalation paths)
                    print(f"      Collecting Jobs...")
                    try:
                        ws_jobs = list(ws_client.jobs.list())
                        for job in ws_jobs:
                            job_id = f"ws_{ws_id}_job:{job.job_id}"
                            job_settings = job.settings if hasattr(job, 'settings') else None
                            job_owner = safe_get(job_settings, 'run_as') if job_settings else None
                            if not job_owner:
                                job_owner = safe_get(job, 'creator_user_name')
                            all_vertices.append({
                                'id': job_id,
                                'node_type': 'Job',
                                'name': job_settings.name if job_settings else str(job.job_id),
                                'display_name': job_settings.name if job_settings else str(job.job_id),
                                'email': None,
                                'owner': str(job_owner) if job_owner else None,
                                'active': True,
                                'created_at': datetime.fromtimestamp(job.created_time / 1000) if job.created_time else None,
                                'updated_at': None,
                                'comment': None,
                                'properties': safe_json({'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                'metadata': None
                            })
                        print(f"      ✓ {len(list(ws_jobs))} jobs")
                    except Exception as e:
                        print(f"      ⚠ Jobs: {e}")

                    # Collect Secret Scopes from this workspace
                    if COLLECTION_CONFIG.get('collect_secret_scopes', True):
                        print(f"      Collecting Secret Scopes...")
                        try:
                            ws_scopes = list(ws_client.secrets.list_scopes())
                            scope_count = 0
                            for scope in ws_scopes:
                                scope_name = safe_get(scope, 'name')
                                scope_id = f"ws_{ws_id}_secret_scope:{scope_name}"
                                all_vertices.append({
                                    'id': scope_id,
                                    'node_type': 'SecretScope',
                                    'name': scope_name,
                                    'display_name': scope_name,
                                    'email': None,
                                    'owner': None,
                                    'active': True,
                                    'created_at': None,
                                    'updated_at': None,
                                    'comment': None,
                                    'properties': safe_json({'backend_type': safe_get(scope, 'backend_type'), 'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                    'metadata': None
                                })
                                scope_count += 1

                                # Collect secrets in scope
                                try:
                                    ws_secrets = list(ws_client.secrets.list_secrets(scope=scope_name))
                                    for secret in ws_secrets:
                                        secret_key = safe_get(secret, 'key')
                                        secret_id = f"ws_{ws_id}_secret:{scope_name}/{secret_key}"
                                        all_vertices.append({
                                            'id': secret_id,
                                            'node_type': 'Secret',
                                            'name': secret_key,
                                            'display_name': secret_key,
                                            'email': None,
                                            'owner': None,
                                            'active': True,
                                            'created_at': None,
                                            'updated_at': None,
                                            'comment': None,
                                            'properties': safe_json({'scope': scope_name, 'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                            'metadata': None
                                        })
                                        # Add Contains edge
                                        all_edges.append({
                                            'src': scope_id,
                                            'dst': secret_id,
                                            'relationship': 'Contains',
                                            'permission_level': None,
                                            'inherited': False,
                                            'properties': None,
                                            'created_at': datetime.now()
                                        })
                                except:
                                    pass

                                # Collect ACLs for the scope
                                try:
                                    ws_acls = list(ws_client.secrets.list_acls(scope=scope_name))
                                    for acl in ws_acls:
                                        principal = safe_get(acl, 'principal')
                                        permission = safe_get(acl, 'permission')
                                        if principal and permission:
                                            perm_map = {'MANAGE': 'CanManageSecret', 'WRITE': 'CanWriteSecret', 'READ': 'CanReadSecret'}
                                            all_edges.append({
                                                'src': principal,
                                                'dst': scope_id,
                                                'relationship': perm_map.get(permission, 'CanReadSecret'),
                                                'permission_level': permission,
                                                'inherited': False,
                                                'properties': safe_json({'workspace_id': str(ws_id)}),
                                                'created_at': datetime.now()
                                            })
                                except:
                                    pass
                            print(f"      ✓ {scope_count} secret scopes")
                        except Exception as e:
                            print(f"      ⚠ Secret Scopes: {e}")

                    # Collect Clusters from this workspace
                    if COLLECTION_CONFIG.get('collect_clusters', True):
                        print(f"      Collecting Clusters...")
                        try:
                            ws_clusters = list(ws_client.clusters.list())
                            for cluster in ws_clusters:
                                cluster_id = safe_get(cluster, 'cluster_id')
                                all_vertices.append({
                                    'id': f"ws_{ws_id}_cluster:{cluster_id}",
                                    'node_type': 'Cluster',
                                    'name': safe_get(cluster, 'cluster_name'),
                                    'display_name': safe_get(cluster, 'cluster_name'),
                                    'email': None,
                                    'owner': safe_get(cluster, 'creator_user_name'),
                                    'active': safe_get(cluster, 'state') == 'RUNNING',
                                    'created_at': None,
                                    'updated_at': None,
                                    'comment': None,
                                    'properties': safe_json({'spark_version': safe_get(cluster, 'spark_version'), 'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                    'metadata': safe_json({'state': safe_get(cluster, 'state')})
                                })
                            print(f"      ✓ {len(ws_clusters)} clusters")
                        except Exception as e:
                            print(f"      ⚠ Clusters: {e}")

                    # Collect SQL Warehouses from this workspace
                    if COLLECTION_CONFIG.get('collect_warehouses', True):
                        print(f"      Collecting SQL Warehouses...")
                        try:
                            ws_warehouses = list(ws_client.warehouses.list())
                            for wh in ws_warehouses:
                                wh_id = safe_get(wh, 'id')
                                all_vertices.append({
                                    'id': f"ws_{ws_id}_warehouse:{wh_id}",
                                    'node_type': 'SQLWarehouse',
                                    'name': safe_get(wh, 'name'),
                                    'display_name': safe_get(wh, 'name'),
                                    'email': None,
                                    'owner': safe_get(wh, 'creator_name'),
                                    'active': safe_get(wh, 'state') == 'RUNNING',
                                    'created_at': None,
                                    'updated_at': None,
                                    'comment': None,
                                    'properties': safe_json({'warehouse_type': safe_get(wh, 'warehouse_type'), 'workspace_id': str(ws_id), 'workspace_name': ws_name}),
                                    'metadata': safe_json({'state': safe_get(wh, 'state')})
                                })
                            print(f"      ✓ {len(ws_warehouses)} warehouses")
                        except Exception as e:
                            print(f"      ⚠ SQL Warehouses: {e}")

                    # Mark this workspace as successfully collected
                    WORKSPACE_COLLECTION_STATUS[ws_id]['status'] = 'success'

                except Exception as e:
                    print(f"      ✗ Failed to connect: {e}")
                    WORKSPACE_COLLECTION_STATUS[ws_id]['status'] = 'failed'
                    WORKSPACE_COLLECTION_STATUS[ws_id]['error'] = str(e)[:500]
                    continue

            print(f"\n   ✓ Multi-workspace collection complete")

            print(f"\n✅ Account-level collection complete!")
            print(f"   Total vertices now: {len(all_vertices)}")
            print(f"   Total edges now: {len(all_edges)}")

        except Exception as e:
            print(f"\n❌ Failed to connect to account: {e}")
            print(f"   Error type: {type(e).__name__}")
            print(f"\n📋 Full traceback:")
            traceback.print_exc()
            print("\n💡 Troubleshooting tips:")
            print("   1. Verify ACCOUNT_ID format (should be a UUID)")
            print("   2. Ensure SP has 'Account Admin' role at account level")
            print("   3. Check if client_id and client_secret are correct")
            print("   4. Verify the account host URL is correct for your cloud")
    else:
        print("\n⚠ Account credentials not configured")
        print("   Set up secrets or hardcode credentials above")
        print("   Required: ACCOUNT_ID, SP_CLIENT_ID, SP_CLIENT_SECRET")
else:
    print("\nAccount-level collection is disabled.")
    print("Set 'collect_account_level': True in COLLECTION_CONFIG to enable.")

# COMMAND ----------

# DBTITLE 1,Re-save if account-level data was collected
if COLLECTION_CONFIG.get('collect_account_level', False):
    print("="*80)
    print("Re-saving with Account-Level Data")
    print("="*80)

    # Add run_id to any new records (account-level data) that don't have it yet
    print(f"\n Adding run_id '{RUN_ID}' to account-level records...")
    for v in all_vertices:
        if 'run_id' not in v or v.get('run_id') is None:
            v['run_id'] = RUN_ID
    for e in all_edges:
        if 'run_id' not in e or e.get('run_id') is None:
            e['run_id'] = RUN_ID

    # Delete the first save for this run_id (we'll re-save everything)
    print(f"\n Removing partial save for run_id '{RUN_ID}'...")
    try:
        spark.sql(f"DELETE FROM {VERTICES_TABLE} WHERE run_id = '{RUN_ID}'")
        spark.sql(f"DELETE FROM {EDGES_TABLE} WHERE run_id = '{RUN_ID}'")
        spark.sql(f"DELETE FROM {COLLECTION_METADATA_TABLE} WHERE run_id = '{RUN_ID}'")
    except Exception as e:
        print(f"   ⚠ Note: {e}")

    # Recreate DataFrames with all data
    vertices_df = spark.createDataFrame(all_vertices, schema=vertices_schema)
    edges_df = spark.createDataFrame(all_edges, schema=edges_schema)

    print(f"\n📊 Final counts:")
    print(f"   Vertices: {vertices_df.count():,}")
    print(f"   Edges: {edges_df.count():,}")

    # Save vertices (append mode)
    print(f"\n💾 Saving vertices to {VERTICES_TABLE}...")
    vertices_df.write \
        .format("delta") \
        .mode("append") \
        .saveAsTable(VERTICES_TABLE)
    print(f"   ✓ Vertices saved!")

    # Save edges (append mode)
    print(f"\n💾 Saving edges to {EDGES_TABLE}...")
    edges_df.write \
        .format("delta") \
        .mode("append") \
        .saveAsTable(EDGES_TABLE)
    print(f"   ✓ Edges saved!")

    # Update collection metadata with final counts and workspace status
    print(f"\n💾 Updating collection metadata...")
    final_collection_time = datetime.now()

    # Build final workspace collection summary
    final_workspaces_collected = []
    final_workspaces_failed = []
    if MULTI_WORKSPACE_MODE:
        for ws_id, ws_info in WORKSPACE_COLLECTION_STATUS.items():
            if ws_info.get('status') == 'success':
                final_workspaces_collected.append(ws_info['name'])
            elif ws_info.get('status') == 'failed':
                final_workspaces_failed.append(ws_info['name'])
    else:
        final_workspaces_collected = [current_workspace_url]

    final_metadata = [{
        'run_id': RUN_ID,
        'collection_timestamp': final_collection_time,
        'vertices_count': str(vertices_df.count()),
        'edges_count': str(edges_df.count()),
        'collected_by': current_user.user_name if current_user else 'unknown',
        'collection_config': json.dumps({k: v for k, v in COLLECTION_CONFIG.items() if not k.startswith('output')}),
        'workspaces_collected': json.dumps(final_workspaces_collected),
        'workspaces_failed': json.dumps(final_workspaces_failed),
        'workspace_status': json.dumps(WORKSPACE_COLLECTION_STATUS) if MULTI_WORKSPACE_MODE else None,
        'collection_mode': 'multi-workspace' if MULTI_WORKSPACE_MODE else 'single-workspace'
    }]
    final_metadata_df = spark.createDataFrame(final_metadata, schema=metadata_schema)
    final_metadata_df.write \
        .format("delta") \
        .mode("append") \
        .saveAsTable(COLLECTION_METADATA_TABLE)
    print(f"   ✓ Metadata updated!")
    print(f"   Workspaces collected: {len(final_workspaces_collected)}")
    if final_workspaces_failed:
        print(f"   ⚠ Workspaces failed: {len(final_workspaces_failed)} - {', '.join(final_workspaces_failed)}")

    # Re-apply retention policy
    retention_days = COLLECTION_CONFIG.get('retention_days', 30)
    print(f"\n🗑️ Re-applying data retention policy (retention_days={retention_days})...")
    if retention_days == -1:
        print("   Retention: Keep forever - no cleanup")
    elif retention_days in (0, 1):
        print("   Retention: Keep only latest run - deleting all previous runs...")
        try:
            spark.sql(f"DELETE FROM {VERTICES_TABLE} WHERE run_id != '{RUN_ID}'")
            spark.sql(f"DELETE FROM {EDGES_TABLE} WHERE run_id != '{RUN_ID}'")
            spark.sql(f"DELETE FROM {COLLECTION_METADATA_TABLE} WHERE run_id != '{RUN_ID}'")
            print("   ✓ Previous runs deleted")
        except Exception as e:
            print(f"   ⚠ Cleanup error: {e}")
    else:
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        print(f"   Retention: Delete runs older than {retention_days} days...")
        try:
            old_runs_df = spark.sql(f"""
                SELECT run_id FROM {COLLECTION_METADATA_TABLE}
                WHERE collection_timestamp < '{cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}'
            """)
            old_run_ids = [row.run_id for row in old_runs_df.collect()]
            if old_run_ids:
                run_ids_str = "', '".join(old_run_ids)
                spark.sql(f"DELETE FROM {VERTICES_TABLE} WHERE run_id IN ('{run_ids_str}')")
                spark.sql(f"DELETE FROM {EDGES_TABLE} WHERE run_id IN ('{run_ids_str}')")
                spark.sql(f"DELETE FROM {COLLECTION_METADATA_TABLE} WHERE run_id IN ('{run_ids_str}')")
                print(f"   ✓ Deleted {len(old_run_ids)} old run(s)")
            else:
                print("   ✓ No old runs to delete")
        except Exception as e:
            print(f"   ⚠ Cleanup error: {e}")

    print(f"\n✅ SUCCESS! Graph data with account-level info saved to {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Collection Summary

# COMMAND ----------

# DBTITLE 1,Final Collection Summary
print("="*80)
print("📊 COLLECTION SUMMARY")
print("="*80)

print(f"\n📅 Collection Run ID: {RUN_ID}")
print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"   Collected by: {current_user.user_name if current_user else 'unknown'}")

print(f"\n📈 Data Statistics:")
print(f"   Total Vertices: {len(all_vertices):,}")
print(f"   Total Edges: {len(all_edges):,}")

print(f"\n🌐 Workspace Coverage:")
if MULTI_WORKSPACE_MODE:
    collected = [ws_info['name'] for ws_id, ws_info in WORKSPACE_COLLECTION_STATUS.items() if ws_info.get('status') == 'success']
    failed = [ws_info['name'] for ws_id, ws_info in WORKSPACE_COLLECTION_STATUS.items() if ws_info.get('status') == 'failed']
    print(f"   Mode: Multi-Workspace")
    print(f"   Successfully Collected: {len(collected)}")
    for ws_name in collected:
        print(f"      ✓ {ws_name}")
    if failed:
        print(f"\n   ⚠ Failed to Collect: {len(failed)}")
        for ws_name in failed:
            print(f"      ✗ {ws_name}")
        print(f"\n   Note: Failed workspaces are NOT included in this analysis.")
        print(f"   To include them, add the Service Principal to those workspaces.")
else:
    print(f"   Mode: Single Workspace")
    print(f"   Workspace: {current_workspace_url}")

print(f"\n📦 Output Location:")
print(f"   {VERTICES_TABLE}")
print(f"   {EDGES_TABLE}")
print(f"   {COLLECTION_METADATA_TABLE}")

print("\n" + "="*80)
print("✅ Collection complete! Run the analysis notebooks to explore the data.")
print("="*80)
