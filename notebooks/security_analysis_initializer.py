# Databricks notebook source
# MAGIC %md
# MAGIC Notebook to initialize setup of SAT 

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

if cloud_type=='gcp':
    #generate account level tokens    
    gcp_status1 = dbutils.notebook.run('./Setup/gcp/configure_sa_auth_tokens', 3000)
    if (gcp_status1 != 'OK'):
        loggr.exception('Error Encountered in GCP Step#1', gcp_status1)
        dbuilts.notebook.exit()
    
if cloud_type=='gcp':
    #generate workspace level tokens
    gcp_status2 = dbutils.notebook.run('./Setup/gcp/configure_tokens_for_worksaces', 3000)
    if (gcp_status2 != 'OK'):
        loggr.exception('Error Encountered in GCP Step#2', gcp_status2)
        dbuilts.notebook.exit()
    
status1 = dbutils.notebook.run('./Setup/1. list_account_workspaces_to_conf_file', 3000)
if (status1 != 'OK'):
    loggr.exception('Error Encountered in Step#1', status1)
    dbuilts.notebook.exit()
    
status2 = dbutils.notebook.run('./Setup/2. generate_secrets_setup_file', 3000)
if (status2 != 'OK'):
    loggr.exception('Error Encountered in Step#2', status2)
    dbuilts.notebook.exit()
    
status3 = dbutils.notebook.run('./Setup/3. test_connections', 3000)
if (status3 != 'OK'):
    loggr.exception('Error Encountered in Step#3', status3)
    dbuilts.notebook.exit()
    
status4 = dbutils.notebook.run('./Setup/4. enable_workspaces_for_sat', 3000)
if (status4 != 'OK'):
    loggr.exception('Error Encountered in Step#4', status4)
    dbuilts.notebook.exit()
    
status5 = dbutils.notebook.run('./Setup/5. import_dashboard_template', 3000)
if (status5 != 'OK'):
    loggr.exception('Error Encountered in Step#5', status5)
    dbuilts.notebook.exit()
    
status6 = dbutils.notebook.run('./Setup/6. configure_alerts_template', 3000)
if (status6 != 'OK'):
    loggr.exception('Error Encountered in Step#6', status6)
    dbuilts.notebook.exit()
