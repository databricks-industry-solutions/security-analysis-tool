# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** install_brickhound_sdk
# MAGIC **Functionality:** Installs the BrickHound SDK for permissions analysis
# MAGIC
# MAGIC This notebook installs the BrickHound Python SDK which provides:
# MAGIC - Graph-based permissions analysis
# MAGIC - Data collection from Databricks APIs
# MAGIC - Permission path finding and escalation analysis
# MAGIC
# MAGIC **Required for:** All BrickHound analysis notebooks

# COMMAND ----------

RECOMMENDED_DBR_FOR_BRICKHOUND = 14.3
import os

dbr_version = os.environ.get('DATABRICKS_RUNTIME_VERSION','0.0')
is_compatible = False
is_serverless = False

if(dbr_version.startswith("client")):
    is_compatible = True
    is_serverless = True
else:
    dbrarray = dbr_version.split('.')
    dbr_version = f'{dbrarray[0]}.{dbrarray[1]}'
    dbr_version = float(dbr_version)
    is_compatible = True if dbr_version >= RECOMMENDED_DBR_FOR_BRICKHOUND else False

if is_compatible == False:
    dbutils.notebook.exit(f"Detected DBR version {dbr_version}. Please use DBR {RECOMMENDED_DBR_FOR_BRICKHOUND} or higher")

# COMMAND ----------

BRICKHOUND_VERSION = '0.1.0'
print(f"Installing BrickHound SDK version {BRICKHOUND_VERSION}...")

# COMMAND ----------

# DBTITLE 1,Install BrickHound SDK
# Install BrickHound SDK and dependencies

# Option 1: Install from PyPI (once published)
# %pip install brickhound=={BRICKHOUND_VERSION}

# Option 2: Install from local wheel during development/testing
# Build wheel first: cd src/brickhound && python setup.py sdist bdist_wheel
import os
import sys

# Check if we're in a repo that has the SDK source
sdk_path = os.path.abspath(os.path.join(os.getcwd(), '../../src/brickhound'))
if os.path.exists(os.path.join(sdk_path, 'setup.py')):
    print(f"Found BrickHound SDK source at: {sdk_path}")
    print("Installing from source...")
    %pip install -e {sdk_path}
else:
    print("SDK source not found locally. Attempting to install from PyPI...")
    %pip install brickhound=={BRICKHOUND_VERSION}

# COMMAND ----------

# DBTITLE 1,Install Additional Dependencies
# Install graph analysis libraries
%pip install databricks-sdk>=0.18.0 networkx>=3.1 pandas>=2.0.0

# COMMAND ----------

# DBTITLE 1,Verify Installation
try:
    from brickhound.collector.core import DatabricksCollector
    from brickhound.graph.builder import GraphBuilder
    from brickhound.graph.permissions_resolver import PermissionsResolver
    from brickhound.graph.analyzer import GraphAnalyzer
    from brickhound.utils.api_client import DatabricksAPIClient

    print("✓ BrickHound SDK installed successfully!")
    print(f"  Version: {BRICKHOUND_VERSION}")
    print("  Components available:")
    print("    - DatabricksCollector (data collection)")
    print("    - GraphBuilder (graph construction)")
    print("    - PermissionsResolver (permission analysis)")
    print("    - GraphAnalyzer (advanced analysis)")
    print("    - DatabricksAPIClient (API wrapper)")
except ImportError as e:
    print(f"✗ BrickHound SDK installation failed: {e}")
    print("\nTroubleshooting:")
    print("1. Ensure DBR version >= 14.3")
    print("2. Check if SDK wheel exists in workspace")
    print("3. Verify network connectivity for PyPI")
    dbutils.notebook.exit("SDK installation failed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC 1. **Configure**: Run `00_config.py` to set up catalog/schema
# MAGIC 2. **Collect Data**: Run `/notebooks/permission_analysis_data_collection.py` to build the permissions graph
# MAGIC 3. **Analyze**: Use analysis notebooks (01-04) to explore permissions
