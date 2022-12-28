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
      dbutils.notebook.exit("Unsuccessful account connection. Verify credentials.")
except requests.exceptions.RequestException as e:
  loggr.exception('Unsuccessful connection. Verify credentials.')
  loggr.exception(e)
  dbutils.notebook.exit("Unsuccessful account connection. Verify credentials.")
except Exception:
  loggr.exception("Exception encountered")
  dbutils.notebook.exit("Unsuccessful account connection. Verify credentials.")

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceTempView('configured_workspaces') 

# COMMAND ----------

workspacesdf = spark.sql('select * from `configured_workspaces`')
display(workspacesdf)
if workspacesdf.rdd.isEmpty():
    dbutils.notebook.exit("Workspace list is empty. At least one should be configured for analysis")
workspaces = workspacesdf.collect()

# COMMAND ----------

#Based on the connection test, modify the connection_test flag so rogue workspaces are not included in the analysis
def modifyWorkspaceConfigFile(input_connection_arr):
  print(input_connection_arr)
  dfworkspaces = readWorkspaceConfigFile()
  if dfworkspaces.rdd.isEmpty() or not input_connection_arr:
    loggr.info('No changes to workspace config file')
    return
  
  dfworkspaces.createOrReplaceTempView('allwsm')
  schema = 'workspace_id string, connection_test boolean'
  spark.createDataFrame(input_connection_arr, schema).createOrReplaceTempView('incomsm')
  #incomsm has only analysis_enabled true, lets add the false rows too use left outer join.
  dfmerge = spark.sql(f'''select 
          allwsm.workspace_id,
          allwsm.deployment_url,
          allwsm.workspace_name,
          allwsm.workspace_status,
          allwsm.ws_token,
          allwsm.alert_subscriber_user_id,
          allwsm.sso_enabled,
          allwsm.scim_enabled,
          allwsm.vpc_peering_done,
          allwsm.object_storage_encypted,
          allwsm.table_access_control_enabled,
          coalesce(incomsm.connection_test, False) as connection_test, 
          allwsm.analysis_enabled 
            from allwsm left outer join incomsm on allwsm.workspace_id=incomsm.workspace_id''')
  
  display(dfmerge)
  prefix = getConfigPath()
  dfmerge.toPandas().to_csv(f'{prefix}/workspace_configs.csv', mode='w', index=False, header=True) #Databricks Runtime 11.2 or above.

# COMMAND ----------

import json
#Get current workspace id
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

def renewWorkspaceTokens(workspace_id):
    if cloud_type=='gcp' and bool(eval(json_['generate_pat_tokens'])) is False :
        #refesh workspace level tokens if PAT tokens are not used as the temp tokens expire in 10 hours
        gcp_status2 = dbutils.notebook.run('../Setup/gcp/configure_tokens_for_worksaces', 3000, {"workspace_id":workspace_id})
        if (gcp_status2 != 'OK'):
            loggr.exception('Error Encountered in GCP Step#2', gcp_status2)
            dbutils.notebook.exit()        
        
    if cloud_type=='azure' and bool(eval(json_['generate_pat_tokens'])) is False :
        #refesh workspace level tokens if PAT tokens are not used as the temp tokens expire in 10 hours
        gcp_status2 = dbutils.notebook.run('../Setup/azure/configure_tokens_for_worksaces', 3000, {"workspace_id":workspace_id})
        if (gcp_status2 != 'OK'):
            loggr.exception('Error Encountered in Azure Step#2', gcp_status2)
            dbutils.notebook.exit()

# COMMAND ----------

input_status_arr=[]
for ws in workspaces:
  import json
  mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
  masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key']) 
  
  # Use configured token if use_mastercreds is set to false or the worspace we are testing is the master (current) workspace 
  # We need the current workspace connection tested with the token to configure alerts and dashboard later
  if((bool(eval(json_['use_mastercreds'])) is False ) or (ws.workspace_id ==current_workspace)):
      tokenscope = json_['workspace_pat_scope']
      tokenkey = ws.ws_token #already has prefix in config file
      renewWorkspaceTokens(ws.workspace_id)
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
    is_successful_ws=False
    loggr.exception(f"Unsuccessful {hostname} workspace connection. Verify credentials.")
  except Exception:
    is_successful_ws=False
    loggr.exception("Exception encountered")
  finally:
    stat_tuple = (ws.workspace_id, is_successful_ws)     
    input_status_arr.append(stat_tuple)
    
modifyWorkspaceConfigFile(input_status_arr)

# COMMAND ----------

dbutils.notebook.exit('OK')
