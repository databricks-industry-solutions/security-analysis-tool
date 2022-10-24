# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

#replace values for accounts exec
mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
#dont know workspace token yet.
json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd, 'url':hostname, 'workspace_id': 'accounts', 'cloud_type': cloud_type, 'clusterid':clusterid})

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

import requests
from core.dbclient import SatDBClient

db_client = SatDBClient(json_)

# COMMAND ----------

is_successful_acct=False
try:
  is_successful_acct = db_client.test_connection(master_acct=True)
  if is_successful_acct == True:
      loggr.info("Account Connection successful!")
  else:
      loggr.info("Unsuccessful account connection. Verify credentials.") 
except requests.exceptions.RequestException as e:
  loggr.exception('Unsuccessful connection. Verify credentials.')
  loggr.exception(e)
except Exception:
  loggr.exception("Exception encountered")

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceTempView('configured_workspaces') 

# COMMAND ----------

workspacesdf = spark.sql('select * from `configured_workspaces`')
display(workspacesdf)
workspaces = workspacesdf.collect()

# COMMAND ----------

for ws in workspaces:
  import json
  mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
  masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])  
  if(bool(json_['use_mastercreds']) is False):
      tokenscope = json_['workspace_pat_scope']
      tokenkey = ws.ws_token #already has prefix in config file
      token = dbutils.secrets.get(tokenscope, tokenkey)
  else:
      token = ''
  
  json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
  hostname = 'https://' + ws.deployment_url
  workspace_id = ws.workspace_id
  clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
  json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd, 'url':hostname, 'workspace_id': workspace_id,  'clusterid':clusterid})

  db_client = SatDBClient(json_)
  
  is_successful_ws=False
  try:
    is_successful_ws = db_client.test_connection()

    if is_successful_ws == True:
      loggr.info(f"Workspace {hostname} Connection successful!")
    else:
      loggr.info(f"Unsuccessful {hostname} workspace connection. Verify credentials.")
  except requests.exceptions.RequestException as e:
      loggr.exception(f"Unsuccessful {hostname} workspace connection. Verify credentials.")
  except Exception:
      loggr.exception("Exception encountered")
