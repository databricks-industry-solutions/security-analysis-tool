# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** install_sat_sdk  
# MAGIC **Functionality:** Installs the necessary sat sdk

# COMMAND ----------

SDK_VERSION='0.1.32'

# COMMAND ----------

#%pip install dbl-sat-sdk=={SDK_VERSION} --find-links /dbfs/FileStore/tables/dbl_sat_sdk-0.1.28-py3-none-any.whl

# COMMAND ----------

# MAGIC %pip install dbl-sat-sdk=={SDK_VERSION}
