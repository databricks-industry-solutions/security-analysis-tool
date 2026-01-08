# Databricks notebook source
# MAGIC %md
# MAGIC # Cluster Configuration Secret Scanning with TruffleHog
# MAGIC
# MAGIC This notebook scans Databricks cluster configurations (specifically `spark_env_vars`) for secrets using TruffleHog.
# MAGIC
# MAGIC ## Workflow:
# MAGIC 1. Get list of all clusters in workspace
# MAGIC 2. For each cluster, extract spark_env_vars configuration
# MAGIC 3. Serialize env vars to temp file
# MAGIC 4. Run TruffleHog dual-scan (built-in + custom detectors)
# MAGIC 5. Parse results and store in clusters_secret_scan_results table
# MAGIC
# MAGIC ## Based on:
# MAGIC - trufflehog_scan.py pattern
# MAGIC - Uses same TruffleHog binary and config
# MAGIC - Shares run_id with notebook scanning for correlation

# COMMAND ----------

# MAGIC %run ../install_sat_sdk

# COMMAND ----------

import time
start_time = time.time()

# COMMAND ----------

# MAGIC %run ../../Utils/common

# COMMAND ----------

test=False #local testing
if test:
    jsonstr = JSONLOCALTEST
else:
    jsonstr = dbutils.widgets.get('json_')

# COMMAND ----------

import json
if not jsonstr:
    print('cannot run notebook by itself')
    dbutils.notebook.exit('cannot run notebook by itself')
else:
    json_ = json.loads(jsonstr)

# COMMAND ----------


from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

import requests
from core import  parser as pars
from core.dbclient import SatDBClient

if cloud_type =='azure': # use client secret
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
  mastername =' ' # this will not be present when using SPs
  masterpwd = ' '  # we still need to send empty user/pwd.
  json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})
else: #lets populate master key for accounts api
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':'dapijedi', 'client_secret': client_secret})
  mastername = ' '
  masterpwd = ' '
  #mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
  #masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
  json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})

db_client = SatDBClient(json_)


# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Install Dependencies and Setup TruffleHog
# MAGIC
# MAGIC This cell installs required Python packages and downloads TruffleHog binary.

# COMMAND ----------

# MAGIC %sh
# MAGIC # Install required Python packages
# MAGIC pip install requests pyyaml
# MAGIC
# MAGIC # Check if TruffleHog is already installed (likely from notebook scanner)
# MAGIC if [ -f /tmp/trufflehog ]; then
# MAGIC     echo "TruffleHog already installed at /tmp/trufflehog"
# MAGIC     echo "Skipping installation (reusing from notebook scanner)"
# MAGIC else
# MAGIC     # Download and install TruffleHog binary to /tmp directory
# MAGIC     echo "Installing TruffleHog..."
# MAGIC     if curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /tmp; then
# MAGIC         if [ -f /tmp/trufflehog ]; then
# MAGIC             echo "Setup completed successfully!"
# MAGIC             echo "TruffleHog binary location: /tmp/trufflehog"
# MAGIC         else
# MAGIC             echo "ERROR: TruffleHog binary not found after installation!"
# MAGIC             echo "Please verify network access and try again."
# MAGIC             exit 1
# MAGIC         fi
# MAGIC     else
# MAGIC         echo "=========================================="
# MAGIC         echo "ERROR: Failed to download TruffleHog"
# MAGIC         echo "=========================================="
# MAGIC         echo ""
# MAGIC         echo "The TruffleHog security scanner could not be downloaded from:"
# MAGIC         echo "https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh"
# MAGIC         echo ""
# MAGIC         echo "Possible causes:"
# MAGIC         echo "  1. Network connectivity issues"
# MAGIC         echo "  2. Firewall or proxy blocking external downloads"
# MAGIC         echo "  3. GitHub.com access is restricted in your environment"
# MAGIC         echo ""
# MAGIC         echo "ACTION REQUIRED:"
# MAGIC         echo "Please contact your IT/Security team to allowlist access to:"
# MAGIC         echo "  - raw.githubusercontent.com"
# MAGIC         echo "  - github.com/trufflesecurity"
# MAGIC         echo ""
# MAGIC         echo "Alternatively, you may need to configure a proxy or use an"
# MAGIC         echo "internal mirror of the TruffleHog installation package."
# MAGIC         echo "=========================================="
# MAGIC         exit 1
# MAGIC     fi
# MAGIC fi
# MAGIC
# MAGIC echo "✅ TruffleHog setup verified!"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Configuration and Authentication
# MAGIC
# MAGIC This cell sets up configuration constants and extracts Databricks authentication context.

# COMMAND ----------

# Import required libraries
import os
import json
import subprocess
import time
import hashlib
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

# Configure logging
logger = loggr  # Use existing logger from common setup

# Use db_client for direct API calls (already initialized in common setup)
# Extract workspace context
workspace_id = json_["workspace_id"]
base_url = json_["url"]

# Get run_id from parent orchestrator (shared with notebook scan)
run_id = json_.get("run_id")
if not run_id:
    logger.warning("No run_id provided by orchestrator, will generate fallback")

logger.info(f"Successfully extracted Databricks context. Base URL: {base_url}")
logger.info(f"Workspace ID: {workspace_id}")
logger.info(f"Run ID: {run_id}")

print(f"✅ Authentication setup completed!")
print(f"📊 Workspace ID: {workspace_id}")
print(f"🆔 Run ID: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Configuration Setup
# MAGIC
# MAGIC Load TruffleHog configuration and set up temp directories.

# COMMAND ----------

# Configuration constants
class Config:
    """Configuration class for cluster secret scanning"""

    # File paths
    TRUFFLEHOG_BINARY = "/tmp/trufflehog"
    TRUFFLEHOG_CONFIG = "/tmp/trufflehog_config.yaml"  # Shared with notebook scanner
    TEMP_CLUSTERS_DIR = "/tmp/clusters"
    RESULTS_LOG_FILE = "/tmp/cluster_secrets_scan_results.json"

    # API settings
    API_SLEEP_SECONDS = 10  # Rate limiting between cluster API calls

    # Scanning settings
    CONFIG_FIELD = "spark_env_vars"  # Which cluster config field to scan

# Create temporary directories if they don't exist
os.makedirs(Config.TEMP_CLUSTERS_DIR, exist_ok=True)
logger.info(f"Temporary directory created: {Config.TEMP_CLUSTERS_DIR}")

# Verify TruffleHog binary exists (should be installed in Step 1)
if not os.path.exists(Config.TRUFFLEHOG_BINARY):
    error_msg = f"""
    ==========================================
    ERROR: TruffleHog binary not found!
    ==========================================

    Expected location: {Config.TRUFFLEHOG_BINARY}

    The TruffleHog binary should have been installed in Step 1.
    Please ensure the installation step completed successfully.
    ==========================================
    """
    logger.error(error_msg)
    raise FileNotFoundError(error_msg)

logger.info(f"✓ TruffleHog binary verified at: {Config.TRUFFLEHOG_BINARY}")

print("✅ Configuration loaded and directories setup successfully!")
print(f"📁 Temp directory: {Config.TEMP_CLUSTERS_DIR}")
print(f"🔧 Config field to scan: {Config.CONFIG_FIELD}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Utility Functions
# MAGIC
# MAGIC Define helper functions for cluster discovery, serialization, and scanning.

# COMMAND ----------

def get_all_clusters() -> List[Dict[str, Any]]:
    """
    Get list of all clusters in the workspace (including terminated).
    Uses direct API call to /clusters/list endpoint.

    Returns:
        List[Dict]: List of cluster objects with cluster_id, cluster_name, state
    """
    try:
        logger.info("Fetching list of all clusters via direct API call...")
        # Direct API call to clusters/list endpoint
        response = db_client.get('/clusters/list', json_params={}, version='2.1')
        clusters = response.get('clusters', [])
        logger.info(f"Found {len(clusters)} clusters in workspace")
        return clusters
    except Exception as e:
        logger.error(f"Failed to get cluster list: {str(e)}")
        raise


def get_cluster_config(cluster_id: str) -> Optional[Dict[str, Any]]:
    """
    Get full cluster configuration including spark_env_vars.
    Uses direct API call to /clusters/get endpoint.

    Args:
        cluster_id: Cluster ID

    Returns:
        Dict: Full cluster configuration dict or None if error
    """
    try:
        # Direct API call to clusters/get endpoint
        json_params = {'cluster_id': cluster_id}
        response = db_client.get('/clusters/get', json_params=json_params, version='2.1')

        # The response has format: {'satelements': <data>, 'http_status_code': 200}
        # Extract the actual cluster config from 'satelements' key
        if isinstance(response, dict) and 'satelements' in response:
            satelements = response['satelements']

            # satelements can be either a list or dict depending on the endpoint
            if isinstance(satelements, list):
                # For single-item endpoints like /clusters/get, it's a list with one element
                if len(satelements) > 0:
                    return satelements[0]  # Return first (and only) item
                else:
                    logger.warning(f"Empty satelements list for cluster {cluster_id}")
                    return None
            elif isinstance(satelements, dict):
                # Already a dict, return as-is
                return satelements
            else:
                logger.warning(f"Unexpected satelements type: {type(satelements)}")
                return None
        else:
            # Response doesn't have satelements wrapper, return as-is
            return response
    except Exception as e:
        logger.error(f"Failed to get cluster config for {cluster_id}: {str(e)}")
        return None


def extract_spark_env_vars(cluster_config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Extract spark_env_vars from cluster configuration.

    Args:
        cluster_config: Full cluster configuration dict

    Returns:
        Dict: spark_env_vars as key-value pairs, or None if not present
    """
    if not cluster_config:
        return None

    # Debug: Log available keys in cluster config
    available_keys = list(cluster_config.keys())
    logger.debug(f"Cluster config keys available: {available_keys}")

    spark_env_vars = cluster_config.get('spark_env_vars', {})

    if not spark_env_vars or len(spark_env_vars) == 0:
        logger.debug(f"No spark_env_vars found. Checking alternative field names...")

        # Check alternative field names
        alternatives = ['spark_env_variables', 'environment_variables', 'env_vars']
        for alt_key in alternatives:
            if alt_key in cluster_config:
                spark_env_vars = cluster_config.get(alt_key, {})
                if spark_env_vars:
                    logger.info(f"Found environment variables under key: '{alt_key}'")
                    return spark_env_vars

        logger.debug(f"No environment variables found in any checked fields")
        return None

    return spark_env_vars


def serialize_env_vars_to_file(cluster_id: str, cluster_name: str, env_vars: Dict[str, str]) -> str:
    """
    Serialize environment variables to a temp file in KEY=VALUE format.

    Args:
        cluster_id: Cluster ID
        cluster_name: Cluster name
        env_vars: Dictionary of environment variables

    Returns:
        str: Path to the created temp file
    """
    file_path = os.path.join(Config.TEMP_CLUSTERS_DIR, f"cluster_config_{cluster_id}.txt")

    try:
        with open(file_path, 'w') as f:
            # Write header comments
            f.write(f"# Cluster: {cluster_name}\n")
            f.write(f"# Cluster ID: {cluster_id}\n")
            f.write(f"# Config Field: {Config.CONFIG_FIELD}\n")
            f.write(f"# Scan Time: {datetime.now(timezone.utc).isoformat()}\n")
            f.write("#" + "="*50 + "\n\n")

            # Write env vars in KEY=VALUE format
            for key, value in env_vars.items():
                # Escape newlines and quotes in values
                if value:
                    escaped_value = str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')
                    f.write(f'{key}="{escaped_value}"\n')
                else:
                    f.write(f'{key}=""\n')

        logger.info(f"Serialized {len(env_vars)} env vars to {file_path}")
        return file_path

    except Exception as e:
        logger.error(f"Failed to serialize env vars to file: {str(e)}")
        raise


def hash_secret(secret: str) -> str:
    """
    Generate SHA-256 hash of a secret (never store raw secrets).

    Args:
        secret: The secret string to hash

    Returns:
        str: SHA-256 hash in hexadecimal format
    """
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


print("✅ Utility functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: TruffleHog Scanning Functions
# MAGIC
# MAGIC Functions to run TruffleHog scans and process results.

# COMMAND ----------

def scan_cluster_config_for_secrets(file_path: str) -> tuple:
    """
    Run TruffleHog dual-scan (built-in + custom detectors) on cluster config file.

    Args:
        file_path: Path to temp file containing cluster config

    Returns:
        tuple: (built_in_results, custom_results) as lists of dicts
    """
    built_in_results = []
    custom_results = []

    try:
        # Scan 1: Built-in detectors (excluding DatabricksToken)
        logger.info(f"Running built-in detectors scan on {file_path}")
        built_in_cmd = [
            Config.TRUFFLEHOG_BINARY,
            "filesystem",
            file_path,
            "--exclude-detectors=DatabricksToken",
            "--no-update",
            "-j"
        ]

        logger.info(f"Built-in scan command: {' '.join(built_in_cmd)}")

        built_in_process = subprocess.run(
            built_in_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        logger.info(f"Built-in scan exit code: {built_in_process.returncode}")

        if built_in_process.stdout:
            built_in_results = [
                json.loads(line)
                for line in built_in_process.stdout.strip().split('\n')
                if line.strip()
            ]
            logger.info(f"Built-in detectors scan completed with {len(built_in_results)} output lines")
        else:
            logger.info("Built-in detectors scan completed with no secrets found")

        # Scan 2: Custom detectors (Databricks-specific)
        logger.info(f"Running custom detectors scan on {file_path}")
        custom_cmd = [
            Config.TRUFFLEHOG_BINARY,
            "filesystem",
            file_path,
            "--no-update",
            "--config",
            Config.TRUFFLEHOG_CONFIG,
            "-j"
        ]

        custom_process = subprocess.run(
            custom_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        logger.info(f"Custom scan exit code: {custom_process.returncode}")

        if custom_process.stdout:
            custom_results = [
                json.loads(line)
                for line in custom_process.stdout.strip().split('\n')
                if line.strip()
            ]
            logger.info(f"Custom detectors scan completed with {len(custom_results)} output lines")
        else:
            logger.info("Custom detectors scan completed with no secrets found")

        return (built_in_results, custom_results)

    except subprocess.TimeoutExpired:
        logger.error(f"TruffleHog scan timed out for {file_path}")
        return ([], [])
    except Exception as e:
        logger.error(f"Failed to scan cluster config for secrets: {str(e)}")
        return ([], [])


def extract_config_key_from_finding(file_content_lines: List[str], raw_secret: str) -> Optional[str]:
    """
    Determine which environment variable key contains the detected secret.

    Args:
        file_content_lines: Lines from the cluster config file
        raw_secret: The raw secret that was detected

    Returns:
        str: Environment variable key name, or None if not found
    """
    try:
        for line in file_content_lines:
            # Skip comments
            if line.strip().startswith('#'):
                continue

            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes from value
                value = value.strip().strip('"').strip("'")

                # Check if this value contains the secret
                if raw_secret in value:
                    return key.strip()

        return None

    except Exception as e:
        logger.warning(f"Failed to extract config key: {str(e)}")
        return None


def process_trufflehog_output(built_in_results: List[Dict], custom_results: List[Dict],
                               cluster_id: str, cluster_name: str, file_path: str) -> List[Dict]:
    """
    Process TruffleHog scan results and extract secret metadata.

    Args:
        built_in_results: Results from built-in detectors scan
        custom_results: Results from custom detectors scan
        cluster_id: Cluster ID
        cluster_name: Cluster name
        file_path: Path to scanned file

    Returns:
        List[Dict]: List of processed secret findings
    """
    secrets_found = []

    # Read file content for key extraction
    try:
        with open(file_path, 'r') as f:
            file_content_lines = f.readlines()
    except:
        file_content_lines = []

    # Combine all results
    all_results = built_in_results + custom_results

    for result in all_results:
        try:
            detector_name = result.get('DetectorName', 'Unknown')
            raw_secret = result.get('Raw', '')
            verified = result.get('Verified', False)
            source_file = result.get('SourceMetadata', {}).get('Data', {}).get('Filesystem', {}).get('file', file_path)

            if raw_secret:
                # Hash the secret (never store plaintext)
                secret_hash = hash_secret(raw_secret)

                # Extract which config key contains this secret
                config_key = extract_config_key_from_finding(file_content_lines, raw_secret)

                secret_metadata = {
                    "DetectorName": detector_name,
                    "Raw_SHA": secret_hash,
                    "SourceFile": source_file,
                    "Verified": verified,
                    "ConfigKey": config_key or "Unknown"
                }

                secrets_found.append(secret_metadata)
                logger.info(f"Secret detected - Type: {detector_name}, Key: {config_key}, SHA: {secret_hash[:16]}...")

        except Exception as e:
            logger.warning(f"Failed to parse TruffleHog output line: {result}. Error: {str(e)}")
            continue

    if secrets_found:
        logger.info(f"Found {len(secrets_found)} potential secrets in cluster: {cluster_name}")
    else:
        logger.info(f"No secrets found in cluster: {cluster_name}")

    return secrets_found


print("✅ Scanning functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Database Storage Functions
# MAGIC
# MAGIC Functions for storing cluster secret scan results in the database.

# COMMAND ----------

def insert_cluster_secret_scan_results(workspace_id: str, cluster_metadata: Dict[str, Any], run_id: int) -> None:
    """
    Insert cluster secret scan results into the clusters_secret_scan_results table.
    Only inserts records when secrets are actually found to avoid database bloat.

    Args:
        workspace_id (str): Workspace ID being scanned
        cluster_metadata (Dict[str, Any]): Cluster metadata with secret details
        run_id (int): SAT run ID for tracking
    """
    import time

    # Extract metadata FIRST so variables are always defined (even if exception occurs)
    cluster_id = cluster_metadata.get("cluster_id", "Unknown")
    cluster_name = cluster_metadata.get("cluster_name", "Unknown")
    config_field = cluster_metadata.get("config_field", Config.CONFIG_FIELD)
    secrets_found = cluster_metadata.get("secrets_found", 0)

    try:
        # Create the table if it doesn't exist
        from common import create_clusters_secret_scan_results_table
        create_clusters_secret_scan_results_table()

        logger.debug(f"Inserting cluster secret scan results for workspace_id: {workspace_id}")
        logger.debug(f"Cluster metadata: {json.dumps(cluster_metadata, indent=2)}")

        scan_time = time.time()

        if secrets_found > 0:
            # Only insert records when secrets are found
            secret_details = cluster_metadata.get("secret_details", [])

            for secret in secret_details:
                detector_name = secret.get("DetectorName", "Unknown")
                secret_sha256 = secret.get("Raw_SHA", "")
                source_file = secret.get("SourceFile", "")
                verified = secret.get("Verified", False)
                config_key = secret.get("ConfigKey", "Unknown")

                # Insert individual secret record
                sql = f"""
                INSERT INTO {json_["analysis_schema_name"]}.clusters_secret_scan_results
                (workspace_id, cluster_id, cluster_name, config_field, config_key, detector_name,
                 secret_sha256, source_file, verified, secrets_found, run_id, scan_time)
                VALUES ('{workspace_id}', '{cluster_id}', '{cluster_name}', '{config_field}',
                        '{config_key}', '{detector_name}', '{secret_sha256}', '{source_file}',
                        {verified}, {secrets_found}, {run_id}, cast({scan_time} as timestamp))
                """

                spark.sql(sql)
                logger.debug(f"Inserted secret scan result for cluster {cluster_id}, detector: {detector_name}")
        else:
            # Don't insert anything for clean clusters to avoid database bloat
            logger.debug(f"No secrets found in cluster {cluster_id}, skipping database insert")

    except Exception as e:
        logger.error(f"Failed to insert cluster secret scan results for cluster {cluster_id}: {str(e)}")
        # Don't raise exception to avoid stopping the scan process


def insert_no_secrets_tracking_row(workspace_id: str, run_id: int) -> None:
    """
    Insert a single tracking row for a scan run where no secrets were found.
    Ensures only one row per run_id exists.
    """
    try:
        # Ensure table exists
        from common import create_clusters_secret_scan_results_table
        create_clusters_secret_scan_results_table()

        logger.info(f"Inserting no-secrets tracking row for workspace_id: {workspace_id}, run_id: {run_id}")

        # Check if a row already exists for this run_id
        existing = spark.sql(f"""
            SELECT COUNT(*) as cnt
            FROM {json_["analysis_schema_name"]}.clusters_secret_scan_results
            WHERE run_id = {run_id}
        """).collect()[0]["cnt"]

        if existing > 0:
            logger.info(f"No-secrets row already exists for run_id {run_id}, skipping insert")
            return

        # Insert placeholder row
        spark.sql(f"""
            INSERT INTO {json_["analysis_schema_name"]}.clusters_secret_scan_results
            (workspace_id, cluster_id, cluster_name, config_field, config_key, detector_name,
             secret_sha256, source_file, verified, secrets_found, run_id, scan_time)
            VALUES ('{workspace_id}', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0, {run_id}, current_timestamp())
        """)
        logger.info(f"No-secrets tracking row inserted successfully for run_id: {run_id}")

    except Exception as e:
        logger.error(f"Failed to insert no-secrets tracking row: {str(e)}")
        # Do not raise to avoid stopping workflow


print("✅ Database storage functions defined successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7: Main Scanning Workflow
# MAGIC
# MAGIC Orchestrate the entire cluster secret scanning process.

# COMMAND ----------

def main_cluster_scanning_workflow():
    """
    Main workflow for scanning cluster configurations for secrets.

    Returns:
        Dict: Summary statistics of the scan
    """
    print("🔍 Starting Cluster Configuration Secret Scanning Workflow")
    print("=" * 60)

    # Get current run_id (passed from orchestrator or use fallback)
    current_run_id = run_id if run_id else int(time.time())
    logger.info(f"Cluster scan starting for workspace: {workspace_id}, run_id: {current_run_id}")

    # Summary statistics
    total_clusters = 0
    clusters_scanned = 0
    clusters_with_secrets = 0
    total_secrets_found = 0

    # Debug info to survive notebook.exit()
    debug_info = {
        "sample_cluster_configs": [],
        "test_cluster_found": False,
        "test_cluster_name": None,
        "test_cluster_has_spark_env_vars": None,
        "clusters_with_spark_env_vars_field": 0
    }

    try:
        # Get all clusters
        clusters = get_all_clusters()
        total_clusters = len(clusters)

        logger.info(f"📊 Found {total_clusters} clusters to scan")

        # Scan each cluster
        for idx, cluster in enumerate(clusters, 1):
            cluster_id = cluster.get('cluster_id')
            cluster_name = cluster.get('cluster_name', 'Unknown')

            # Special logging for test cluster
            is_test_cluster = 'Arun' in cluster_name or 'Personal' in cluster_name
            if is_test_cluster:
                logger.info(f"🎯 FOUND TEST CLUSTER: {cluster_name} ({cluster_id})")
                print(f"\n🎯 FOUND TEST CLUSTER: {cluster_name}")

            logger.info(f"🔍 [{idx}/{total_clusters}] Processing cluster: {cluster_name} ({cluster_id})")

            try:
                # Get full cluster configuration
                cluster_config = get_cluster_config(cluster_id)

                if not cluster_config:
                    logger.warning(f"Failed to get config for cluster {cluster_id}, skipping")
                    print(f"  ⚠️  Failed to get config for {cluster_name}")
                    continue

                # Debug: Log cluster config structure for debugging
                if idx <= 3:  # Show first 3 clusters for debugging
                    config_keys = list(cluster_config.keys())
                    logger.info(f"Sample cluster config keys for debugging: {config_keys}")
                    print(f"  🔍 Debug: Cluster #{idx} config keys: {config_keys}")
                    debug_info["sample_cluster_configs"].append({
                        "cluster_name": cluster_name,
                        "cluster_id": cluster_id,
                        "config_keys": config_keys
                    })

                # Check if spark_env_vars field exists
                has_spark_env_vars = 'spark_env_vars' in cluster_config
                spark_env_vars_value = cluster_config.get('spark_env_vars', None)

                # Track clusters with spark_env_vars field
                if has_spark_env_vars:
                    debug_info["clusters_with_spark_env_vars_field"] += 1

                # Special debugging for test cluster
                if is_test_cluster:
                    debug_info["test_cluster_found"] = True
                    debug_info["test_cluster_name"] = cluster_name
                    debug_info["test_cluster_has_spark_env_vars"] = has_spark_env_vars
                    debug_info["test_cluster_spark_env_vars_value"] = str(spark_env_vars_value)[:200]  # First 200 chars
                    debug_info["test_cluster_config_keys"] = list(cluster_config.keys())

                    print(f"  🔍 TEST CLUSTER DEBUG:")
                    print(f"     - Has spark_env_vars field: {has_spark_env_vars}")
                    print(f"     - spark_env_vars value: {spark_env_vars_value}")
                    print(f"     - spark_env_vars type: {type(spark_env_vars_value).__name__}")
                    if spark_env_vars_value:
                        print(f"     - spark_env_vars keys: {list(spark_env_vars_value.keys()) if isinstance(spark_env_vars_value, dict) else 'N/A'}")

                if has_spark_env_vars:
                    logger.info(f"Cluster {cluster_name} has spark_env_vars field: {spark_env_vars_value}")
                    print(f"  ✅ {cluster_name}: Has spark_env_vars field (value type: {type(spark_env_vars_value).__name__})")
                else:
                    logger.info(f"Cluster {cluster_name} does NOT have spark_env_vars field")
                    print(f"  ⏭️  {cluster_name}: No spark_env_vars field in config")

                # Extract spark_env_vars
                env_vars = extract_spark_env_vars(cluster_config)

                if not env_vars:
                    logger.info(f"No environment variables extracted from cluster {cluster_name}")
                    print(f"  ⏭️  {cluster_name}: No environment variables extracted, skipping")
                    continue

                print(f"  ✅ {cluster_name}: Found {len(env_vars)} environment variables to scan")

                # Serialize to temp file
                file_path = serialize_env_vars_to_file(cluster_id, cluster_name, env_vars)

                # Run TruffleHog dual-scan
                built_in_results, custom_results = scan_cluster_config_for_secrets(file_path)

                # Process results
                secrets_found = process_trufflehog_output(
                    built_in_results, custom_results, cluster_id, cluster_name, file_path
                )

                clusters_scanned += 1

                if secrets_found:
                    clusters_with_secrets += 1
                    total_secrets_found += len(secrets_found)

                    # Store in database
                    cluster_metadata = {
                        "cluster_id": cluster_id,
                        "cluster_name": cluster_name,
                        "config_field": Config.CONFIG_FIELD,
                        "secrets_found": len(secrets_found),
                        "secret_details": secrets_found
                    }

                    insert_cluster_secret_scan_results(workspace_id, cluster_metadata, current_run_id)

                    print(f"🚨 SECRETS DETECTED in {cluster_name}: {len(secrets_found)} secrets found")

                # Clean up temp file
                try:
                    os.remove(file_path)
                except:
                    pass

                # Rate limiting
                if idx < total_clusters:
                    time.sleep(Config.API_SLEEP_SECONDS)

            except Exception as e:
                logger.error(f"Error scanning cluster {cluster_id}: {str(e)}")
                continue

        # Insert tracking row if no secrets found anywhere
        if total_secrets_found == 0:
            insert_no_secrets_tracking_row(workspace_id, current_run_id)

        # Print summary
        print("\n🎉 Cluster Secret Scanning Completed!")
        print("=" * 60)
        print(f"📊 Total clusters: {total_clusters}")
        print(f"🔍 Clusters scanned: {clusters_scanned}")
        print(f"🚨 Clusters with secrets: {clusters_with_secrets}")
        print(f"🔑 Total secrets detected: {total_secrets_found}")

        if clusters_with_secrets > 0:
            print(f"⚠️  Security Alert: {clusters_with_secrets} cluster(s) contain potential secrets!")
            print("   Please review the detailed results in the dashboard and take appropriate action.")

        return {
            "total_clusters": total_clusters,
            "clusters_scanned": clusters_scanned,
            "clusters_with_secrets": clusters_with_secrets,
            "total_secrets_found": total_secrets_found,
            "run_id": current_run_id,
            "debug_info": debug_info
        }

    except Exception as e:
        logger.error(f"Fatal error in cluster scanning workflow: {str(e)}")
        raise


# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 8: Execute Workflow
# MAGIC
# MAGIC Run the main scanning workflow and display results.

# COMMAND ----------

# Execute the main workflow
results = main_cluster_scanning_workflow()

# Display summary as output
dbutils.notebook.exit(json.dumps(results))
