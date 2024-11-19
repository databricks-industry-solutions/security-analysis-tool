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
#sanity check in case there is major and minor version
#strip minor version since we need to compare as number
if(dbr_version.startswith("client")):
    is_sat_compatible = True
else:
    dbrarray = dbr_version.split('.')
    dbr_version =  f'{dbrarray[0]}.{dbrarray[1]}'
    dbr_version = float(dbr_version)
    is_sat_compatible = True if dbr_version >= RECOMMENDED_DBR_FOR_SAT else False

#test version

if is_sat_compatible== False:
    dbutils.notebook.exit(f"Detected DBR version {dbr_version} . Please use the DBR {RECOMMENDED_DBR_FOR_SAT} for SAT and try again , please refer to docs/setup.md")

# COMMAND ----------

SDK_VERSION='0.0.102' 

# COMMAND ----------

#%pip install dbl-sat-sdk=={SDK_VERSION} --find-links /dbfs/FileStore/tables/dbl_sat_sdk-0.1.37-py3-none-any.whl

# COMMAND ----------

# MAGIC %pip install PyYAML dbl-sat-sdk=={SDK_VERSION} 
