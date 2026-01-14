# Databricks notebook source
# MAGIC %md
# MAGIC # Permissions Analysis Tool Configuration
# MAGIC
# MAGIC **Purpose**: Centralized configuration for all Permissions Analysis Tool notebooks.
# MAGIC
# MAGIC Run this notebook first, or set these values in each analysis notebook.
# MAGIC
# MAGIC **Configuration Options**:
# MAGIC 1. **Run this notebook** to set workspace-wide widgets
# MAGIC 2. **Copy the config cell** to your notebook
# MAGIC 3. **Import from library** (if Permissions Analysis Tool is installed as package)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Service Principal Setup (Required for Multi-Workspace Collection)
# MAGIC
# MAGIC To collect data from **all workspaces** in your account, you need a Service Principal with:
# MAGIC 1. **Account Admin** role at the account level
# MAGIC 2. **Workspace Admin** access on each workspace you want to analyze
# MAGIC
# MAGIC ### Step 1: Create a Service Principal
# MAGIC 1. Go to **Account Console** > **User Management** > **Service Principals**
# MAGIC 2. Click **Add Service Principal** and create a new one (e.g., "brickhound-collector")
# MAGIC 3. Note the **Application ID** (Client ID)
# MAGIC
# MAGIC ### Step 2: Generate OAuth Secret
# MAGIC 1. Select the Service Principal
# MAGIC 2. Go to **OAuth secrets** tab > **Generate Secret**
# MAGIC 3. Copy and save the **Secret** (you won't see it again!)
# MAGIC
# MAGIC ### Step 3: Assign Account Admin Role
# MAGIC 1. Go to **Account Console** > **User Management** > **Service Principals**
# MAGIC 2. Click on your SP > **Roles** tab > Add **Account Admin**
# MAGIC
# MAGIC ### Step 4: Add SP to Target Workspaces
# MAGIC For each workspace you want to analyze:
# MAGIC 1. Go to that workspace's **Admin Console** > **Users**
# MAGIC 2. Add the Service Principal
# MAGIC 3. Grant **Admin** permissions
# MAGIC
# MAGIC ### Step 5: Configure Credentials
# MAGIC
# MAGIC BrickHound is integrated into SAT and uses SAT's credential system.
# MAGIC
# MAGIC **If SAT is already installed:**
# MAGIC - No additional configuration needed
# MAGIC - BrickHound automatically uses credentials from `sat_scope` secret scope
# MAGIC - Required secrets (already configured by SAT):
# MAGIC   - `account-console-id` (Account UUID)
# MAGIC   - `client-id` (Service Principal Application ID)
# MAGIC   - `client-secret` (Service Principal OAuth Secret)
# MAGIC   - `analysis_schema_name` (Unity Catalog schema: `catalog.schema`)
# MAGIC
# MAGIC **If SAT is not installed:**
# MAGIC - Run the SAT installer: `./install.sh` in the SAT project root
# MAGIC - This will create `sat_scope` and configure all required credentials

# COMMAND ----------

# MAGIC %md
# MAGIC ## Quick Configuration (Copy This Cell to Any Notebook)

# COMMAND ----------

# DBTITLE 1,BrickHound Configuration (SAT Integration)
# ==============================================================================
# BRICKHOUND CONFIGURATION (SAT Integration)
# ==============================================================================
# Configuration is automatically read from SAT's sat_scope

# Secrets scope name (uses SAT's secret scope)
SECRETS_SCOPE = "sat_scope"

# Read catalog and schema from SAT configuration
analysis_schema = dbutils.secrets.get(scope="sat_scope", key="analysis_schema_name")
CATALOG = analysis_schema.split('.')[0]
SCHEMA = analysis_schema.split('.')[1]

# Table names (namespaced with brickhound_ prefix to avoid conflicts with SAT tables)
VERTICES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_vertices"
EDGES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_edges"
COLLECTION_METADATA_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_collection_metadata"

print("=" * 60)
print("BrickHound Configuration (SAT Integration)")
print("=" * 60)
print(f"Catalog:        {CATALOG}")
print(f"Schema:         {SCHEMA}")
print(f"Secrets Scope:  {SECRETS_SCOPE}")
print(f"Vertices:       {VERTICES_TABLE}")
print(f"Edges:          {EDGES_TABLE}")
print(f"Metadata:       {COLLECTION_METADATA_TABLE}")
print("=" * 60)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Configuration

# COMMAND ----------

# DBTITLE 1,Check if catalog exists
try:
    existing_catalogs = spark.sql("SHOW CATALOGS").collect()
    catalog_names = [row.catalog for row in existing_catalogs]
    
    if CATALOG in catalog_names:
        print(f"✓ Catalog '{CATALOG}' exists")
    else:
        print(f"✗ Catalog '{CATALOG}' does not exist")
        print(f"\nAvailable catalogs:")
        for cat in catalog_names:
            print(f"  - {cat}")
        print(f"\nUpdate CATALOG variable above to use one of these.")
except Exception as e:
    print(f"Error checking catalogs: {e}")

# COMMAND ----------

# DBTITLE 1,Check if graph tables exist
try:
    # Try to access vertices table
    v_count = spark.table(VERTICES_TABLE).count()
    e_count = spark.table(EDGES_TABLE).count()
    
    print(f"✓ Graph tables exist!")
    print(f"  Vertices: {v_count:,}")
    print(f"  Edges:    {e_count:,}")
    print(f"\nGraph data is ready for analysis.")
except Exception as e:
    print(f"✗ Graph tables not found: {e}")
    print(f"\nRun '/notebooks/permission_analysis_data_collection.py' to create the graph data.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Using Configuration in Other Notebooks
# MAGIC
# MAGIC ### Option 1: Copy the Config Cell
# MAGIC Copy the "Permissions Analysis Tool Configuration" cell above to the top of any analysis notebook.
# MAGIC
# MAGIC ### Option 2: Use %run Magic
# MAGIC ```python
# MAGIC %run ./00_config
# MAGIC # Now CATALOG, SCHEMA, VERTICES_TABLE, EDGES_TABLE are available
# MAGIC ```
# MAGIC
# MAGIC ### Option 3: Import from Library
# MAGIC ```python
# MAGIC from brickhound.utils.config import GraphConfig
# MAGIC
# MAGIC config = GraphConfig(catalog="main", schema="brickhound")
# MAGIC VERTICES_TABLE = config.vertices_path
# MAGIC EDGES_TABLE = config.edges_path
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## Advanced: Environment Variables
# MAGIC
# MAGIC Set these as cluster environment variables for automatic configuration:
# MAGIC
# MAGIC ```bash
# MAGIC BRICKHOUND_CATALOG=main
# MAGIC BRICKHOUND_SCHEMA=brickhound
# MAGIC ```
# MAGIC
# MAGIC Then in notebooks:
# MAGIC ```python
# MAGIC from brickhound.utils.config import GraphConfig
# MAGIC config = GraphConfig.from_env()
# MAGIC ```
# MAGIC
