# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** install_sat_sdk  
# MAGIC **Functionality:** Installs the necessary sat sdk

# COMMAND ----------

RECOMMENDED_DBR_FOR_SAT= 14.3
import os
#Get databricks runtime configured to run SAT
dbr_version = os.environ.get('DATABRICKS_RUNTIME_VERSION','0.0')
is_sat_compatible = False
is_serverless= False
#sanity check in case there is major and minor version
#strip minor version since we need to compare as number
if(dbr_version.startswith("client")):
    is_sat_compatible = True
    is_serverless = True
else:
    dbrarray = dbr_version.split('.')
    dbr_version =  f'{dbrarray[0]}.{dbrarray[1]}'
    dbr_version = float(dbr_version)
    is_sat_compatible = True if dbr_version >= RECOMMENDED_DBR_FOR_SAT else False

#test version

if is_sat_compatible== False:
    dbutils.notebook.exit(f"Detected DBR version {dbr_version} . Please use the DBR {RECOMMENDED_DBR_FOR_SAT} for SAT and try again , please refer to docs/setup.md")

# COMMAND ----------

SDK_VERSION='0.1.40'

# COMMAND ----------

# Construct workspace path to wheel file dynamically
NOTEBOOK_PATH = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
# Extract repo root by finding 'security-analysis-tool' in the path
path_parts = NOTEBOOK_PATH.split('/')
try:
    sat_index = path_parts.index('security-analysis-tool')
    REPO_ROOT = '/'.join(path_parts[:sat_index+1])
except ValueError:
    # Fallback if repo name not found in path
    REPO_ROOT = '/Workspace/Repos/production/security-analysis-tool'

WHEEL_PATH = f'{REPO_ROOT}/lib/dbl_sat_sdk-{SDK_VERSION}-py3-none-any.whl'
print(f"Installing SAT SDK from: {WHEEL_PATH}")

# COMMAND ----------

# MAGIC %pip install PyYAML {WHEEL_PATH} 
