# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** pre_run_config_check  
# MAGIC **Functionality:** Diagnose basic setup before running the job

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

secret_scopes = dbutils.secrets.listScopes()


# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there is an SAT scope configured

# COMMAND ----------

found = False
for secret_scope in secret_scopes:
   
   if secret_scope.name == json_['master_name_scope']:
      print('Your SAT configuration has the required scope name')
      found=True
      break
if not found:
   dbutils.notebook.exit(f'Your SAT configuration is missing required scope {json_["master_name_scope"]}, please review setup instructions')

      

# COMMAND ----------

# replace values for accounts exec
hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope

# COMMAND ----------


if cloud_type == "aws":
   try:
      dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='use-sp-auth')
      dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
      print("Your SAT configuration is has required secret names")
   except Exception as e:
      dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  

# COMMAND ----------

if cloud_type == "azure":
   try:
      dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='subscription-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='tenant-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret')
      dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
      print("Your SAT configuration has required secret names")
   except Exception as e:
      dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  

# COMMAND ----------

if cloud_type == "gcp":
   try:
      dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json')
      dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account')
      dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
      print("Your SAT configuration has required secret names")
   except Exception as e:
      dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  
