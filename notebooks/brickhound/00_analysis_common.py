# Databricks notebook source
# MAGIC %md
# MAGIC # Common Analysis Setup
# MAGIC *Shared initialization for security analysis notebooks*
# MAGIC
# MAGIC This notebook contains common setup logic used by all analysis notebooks:
# MAGIC - Dependency installation
# MAGIC - Configuration loading
# MAGIC - SecurityAnalyzer initialization
# MAGIC - Data snapshot selection
# MAGIC - Graph data loading
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC Run `/notebooks/permission_analysis_data_collection.py` first to populate the graph data.
# MAGIC
# MAGIC ## Usage
# MAGIC
# MAGIC Include this notebook in your analysis notebook:
# MAGIC ```python
# MAGIC %run ./00_analysis_common
# MAGIC ```

# COMMAND ----------

# DBTITLE 1,Install Dependencies
import os

print("="*60)
print("BRICKHOUND SDK INSTALLATION")
print("="*60)
print(f"Current working directory: {os.getcwd()}")

# Verify SDK path exists before installing
sdk_path = os.path.abspath("../../src/brickhound")
print(f"SDK installation path: {sdk_path}")
print(f"SDK path exists: {os.path.exists(sdk_path)}")

# MAGIC %pip install networkx --quiet

if os.path.exists(sdk_path):
    print(f"\nInstalling brickhound SDK from: {sdk_path}")
    # MAGIC %pip install -e ../../src/brickhound
    print("✓ SDK installation command executed")
else:
    print(f"\n⚠️  WARNING: SDK path not found at {sdk_path}")
    print(f"   SDK will not be available - notebooks will use fallback functions")

print("="*60)

# COMMAND ----------

# DBTITLE 1,Restart Python (required after pip install)
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Load Configuration
# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Imports and Initialize Analyzer
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import sys
import os

# Add brickhound to path for local development (fallback if pip install didn't work)
sys.path.insert(0, os.path.dirname(os.getcwd()))

# Import the SecurityAnalyzer class
print("\n" + "="*60)
print("SDK LOADING VERIFICATION")
print("="*60)

try:
    from brickhound.graph.analyzer import SecurityAnalyzer, PRIVILEGED_ROLES

    # Verify the import actually worked
    print("✓ SecurityAnalyzer imported successfully")
    print(f"  Module location: {SecurityAnalyzer.__module__}")
    print(f"  SecurityAnalyzer class: {SecurityAnalyzer}")

    USE_ANALYZER = True
    print("\n✓ SDK LOADED - Using SecurityAnalyzer (full-featured analysis)")

except ImportError as e:
    print("✗ SDK import failed - Using fallback functions (simplified analysis)")
    print(f"  Error: {e}")
    print(f"  Current sys.path (first 3): {sys.path[:3]}")
    print("\nTo fix:")
    print("  1. Verify SDK path exists: ../../src/brickhound")
    print("  2. Re-run the 'Install Dependencies' cell above")
    print("  3. Ensure Python restart completed (run all cells in order)")

    SecurityAnalyzer = None
    USE_ANALYZER = False

print("="*60 + "\n")

def format_principal_name(display_name, email, name, principal_id=None):
    """Format principal name with identifier in parentheses like 'Arun Pamulapati (arun.pamulapati@databricks.com)'"""
    display = display_name or name or email or principal_id or 'Unknown'
    identifier = email or name or principal_id
    if identifier and display.lower() != identifier.lower():
        return f"{display} ({identifier})"
    return display

# COMMAND ----------

# DBTITLE 1,Select Data Snapshot
# Get available collection runs
available_runs_df = spark.sql(f"""
    SELECT run_id, collection_timestamp, vertices_count, edges_count, collected_by
    FROM {COLLECTION_METADATA_TABLE}
    ORDER BY collection_timestamp DESC
    LIMIT 20
""")
available_runs = available_runs_df.collect()

if not available_runs:
    raise Exception("No collection runs found. Run /notebooks/permission_analysis_data_collection.py first to collect data.")

# Build dropdown options
run_options = []
run_id_map = {}
for run in available_runs:
    ts = run['collection_timestamp'].strftime('%Y-%m-%d %H:%M') if run['collection_timestamp'] else 'Unknown'
    vertices_count = run['vertices_count'] or 0
    label = f"{ts} ({vertices_count} vertices)"
    run_options.append(label)
    run_id_map[label] = run['run_id']

# Create widget for run selection
dbutils.widgets.dropdown("run_id_selection", run_options[0], run_options, "Data Snapshot")

# Get selected run
selected_label = dbutils.widgets.get("run_id_selection")
SELECTED_RUN_ID = run_id_map.get(selected_label, available_runs[0]['run_id'])

print(f"Selected: {selected_label}")
print(f"Run ID: {SELECTED_RUN_ID}")

# COMMAND ----------

# DBTITLE 1,Load Graph Data
print(f"Loading graph data...")

# Load vertices and edges for selected run
vertices = spark.table(VERTICES_TABLE).filter(F.col("run_id") == SELECTED_RUN_ID)
edges = spark.table(EDGES_TABLE).filter(F.col("run_id") == SELECTED_RUN_ID)

v_count = vertices.count()
e_count = edges.count()

print(f"Vertices: {v_count:,}")
print(f"Edges: {e_count:,}")

# Cache for performance
vertices.cache()
edges.cache()

# Initialize the SecurityAnalyzer if available
if SecurityAnalyzer:
    analyzer = SecurityAnalyzer(spark, VERTICES_TABLE, EDGES_TABLE, SELECTED_RUN_ID)
    print(f"✓ SecurityAnalyzer initialized (using shared logic with app)")
else:
    analyzer = None
    print(f"⚠ Using fallback notebook-local functions")

# COMMAND ----------

# DBTITLE 1,⚠️ VERIFY SDK STATUS (Check This!)
print("="*60)
print("BRICKHOUND SDK STATUS")
print("="*60)

if analyzer is not None:
    print("\n✓ SDK ACTIVE: Using SecurityAnalyzer from brickhound package")
    print("\n  Available features:")
    print("  • Full group expansion (nested groups)")
    print("  • Parent resource inheritance")
    print("  • Complete permission resolution")
    print("  • Detailed source tracking (DIRECT, GROUP, OWNERSHIP, PARENT)")
    print("\n  All analysis notebooks will use full-featured SDK methods.")
else:
    print("\n⚠️  FALLBACK MODE: Using simplified notebook functions")
    print("\n  Limited features:")
    print("  • No group expansion (direct grants only)")
    print("  • No parent resource inheritance")
    print("  • Simplified permission resolution")
    print("\n  ⚠️  Analysis results will be incomplete!")
    print("\n  To enable SDK:")
    print("  1. Verify brickhound SDK is at: ../../src/brickhound")
    print("  2. Re-run 'Install Dependencies' cell")
    print("  3. Re-run cells after Python restart")

print("="*60)

# COMMAND ----------

# DBTITLE 1,Workspace Coverage
import json

# Get collection metadata for selected run
metadata_row = spark.sql(f"""
    SELECT workspaces_collected, workspaces_failed, collection_mode, collection_timestamp
    FROM {COLLECTION_METADATA_TABLE}
    WHERE run_id = '{SELECTED_RUN_ID}'
    ORDER BY collection_timestamp DESC
    LIMIT 1
""").collect()

print("="*60)
print("📊 COLLECTION COVERAGE")
print("="*60)

if metadata_row:
    meta = metadata_row[0]
    collection_mode = meta['collection_mode'] if 'collection_mode' in meta.asDict() else 'unknown'
    print(f"\nCollection Mode: {collection_mode}")

    # Parse workspaces collected
    if 'workspaces_collected' in meta.asDict() and meta['workspaces_collected']:
        try:
            workspaces_collected = json.loads(meta['workspaces_collected'])
            print(f"\n✓ Workspaces Included ({len(workspaces_collected)}):")
            for ws_name in workspaces_collected:
                print(f"   • {ws_name}")
        except:
            print("\n   Unable to parse workspace data")

    # Parse workspaces failed
    if 'workspaces_failed' in meta.asDict() and meta['workspaces_failed']:
        try:
            workspaces_failed = json.loads(meta['workspaces_failed'])
            if workspaces_failed:
                print(f"\n⚠ Workspaces NOT Included ({len(workspaces_failed)}):")
                for ws_name in workspaces_failed:
                    print(f"   • {ws_name}")
                print(f"\n   Note: Data from failed workspaces is NOT in this report.")
                print(f"   To include them, ensure the Service Principal has access.")
        except:
            pass
else:
    print("\n   No metadata found for this collection run")

print("\n" + "="*60)
print("\n✓ Common setup complete. You can now run analysis functions.")
