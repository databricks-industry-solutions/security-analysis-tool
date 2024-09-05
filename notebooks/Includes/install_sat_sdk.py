# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** install_sat_sdk  
# MAGIC **Functionality:** Installs the necessary sat sdk

# COMMAND ----------

RECOMMENDED_DBR_FOR_SAT= 14.3
import os
#Get databricks runtime configured to run SAT
dbr_version = os.environ.get('DATABRICKS_RUNTIME_VERSION','0.0')
#sanity check in case there is major and minor version
#strip minor version since we need to compare as number
dbrarray = dbr_version.split('.')
dbr_version =  f'{dbrarray[0]}.{dbrarray[1]}'
dbr_version = float(dbr_version)

#test version

if dbr_version < RECOMMENDED_DBR_FOR_SAT:
    dbutils.notebook.exit(f"Detected DBR version {dbr_version} . Please use the DBR {RECOMMENDED_DBR_FOR_SAT} for SAT and try again , please refer to docs/setup.md")

# COMMAND ----------

SDK_VERSION='0.1.35'

# COMMAND ----------

#%pip install dbl-sat-sdk=={SDK_VERSION} --find-links /dbfs/FileStore/tables/dbl_sat_sdk-0.1.28-py3-none-any.whl

# COMMAND ----------

# MAGIC %pip install PyYAML dbl-sat-sdk=={SDK_VERSION} 
