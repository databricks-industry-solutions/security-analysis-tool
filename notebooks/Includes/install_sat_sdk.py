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

def getLibPath():
    path = (
        dbutils.notebook.entry_point.getDbutils()
        .notebook()
        .getContext()
        .notebookPath()
        .get()
    )
    path = path[: path.find("/notebooks")]
    return f"/Workspace{path}/lib"

# COMMAND ----------

# Construct workspace path to wheel file dynamically
WHEEL_PATH = f'{getLibPath()}/dbl_sat_sdk-{SDK_VERSION}-py3-none-any.whl'
print(f"Installing SAT SDK from: {WHEEL_PATH}")

# COMMAND ----------

# MAGIC %pip install PyYAML {WHEEL_PATH} 
