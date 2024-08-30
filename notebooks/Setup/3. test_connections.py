# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 3. test_connections.      
# MAGIC **Functionality:** Tests account and workspace connections and writes workspaces that can be connected with status into the config file

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")

# COMMAND ----------

#replace values for accounts exec
token = 'dapijedi'
if cloud_type =='azure': #use client secret
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':token, 'client_secret': client_secret})
elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':'dapijedi', 'client_secret': client_secret})
    mastername =' ' # this will not be present when using SPs
    masterpwd = ' '  # we still need to send empty user/pwd.
    json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})
else: #lets populate master key for accounts api
    mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
    json_.update({'token':'dapijedi', 'mastername':mastername, 'masterpwd':masterpwd})
json_.update({'url':hostname, 'workspace_id': 'accounts', 'cloud_type': cloud_type, 'clusterid':clusterid})


# COMMAND ----------

import requests
from core.dbclient import SatDBClient

def test_connection(jsonarg, accounts_test=False):
  db_client = SatDBClient(jsonarg)
  token = db_client.get_temporary_oauth_token()
  if accounts_test == True:
    hostname='Accounts'
    workspace_id='Accounts_Cred'
  else:
    hostname=jsonarg['url']
    workspace_id = jsonarg['workspace_id']
  is_successful_ws=False
  try:
    is_successful_ws = db_client.test_connection(master_acct=accounts_test)
    if is_successful_ws == True:
      loggr.info(f"{hostname} {workspace_id} : Connection successful!")
    else:
      loggr.info(f"Unsuccessful {hostname} {workspace_id} connection. Verify credentials.")
  except requests.exceptions.RequestException as e:
    is_successful_ws=False
    loggr.exception(f"Unsuccessful {hostname} {workspace_id} workspace connection. Verify credentials.")
  except Exception:
    is_successful_ws=False
    loggr.exception("Exception encountered")
  finally:
    stat_tuple = (workspace_id, is_successful_ws)     
  return stat_tuple

# COMMAND ----------

#master account connectionn test.
ret_tuple = test_connection(json_, True)
if ret_tuple[1]==False:
  loggr.info("\033[1mUnsuccessful Account connection. Verify credentials.\033[1m") 
  dbutils.notebook.exit("Unsuccessful account connection. Verify credentials.")
else:
  loggr.info("\033[1mAccount Connection successful!\033[1m")


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
          allwsm.sso_enabled,
          allwsm.scim_enabled,
          allwsm.vpc_peering_done,
          allwsm.object_storage_encrypted,
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

def renewWorkspaceTokens():
  if cloud_type == "gcp":
    # refesh workspace level tokens if PAT tokens are not used as the temp tokens expire in 10 hours
    gcp_status2 = dbutils.notebook.run("../Setup/gcp/configure_tokens_for_worksaces", 3000)
    if gcp_status2 != "OK":
      loggr.exception("Error Encountered in GCP Step#2", gcp_status2)
      dbutils.notebook.exit()

# COMMAND ----------

input_status_arr=[]
renewWorkspaceTokens()
for ws in workspaces:
  import json
  
  hostname = 'https://' + ws.deployment_url
  workspace_id = ws.workspace_id
  clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
  json_.update({'url':hostname, 'workspace_id': workspace_id,  'clusterid':clusterid})  

  token = ''
  if cloud_type =='azure': #use client secret
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
  elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
    mastername =' ' # this will not be present when using SPs
    masterpwd = ' '  # we still need to send empty user/pwd.
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
  else: #lets populate master key for accounts api
    mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
      
  if (json_['use_mastercreds']) is False:
    tokenscope = json_['workspace_pat_scope']
    tokenkey = f"{json_['workspace_pat_token_prefix']}-{json_['workspace_id']}"
    try:
      token = dbutils.secrets.get(tokenscope, tokenkey)
    except Exception as e:#pat may not be setup.
      loggr.info(f"\033[1m {e} - {tokenscope}:{tokenkey}\033[0m")
      ret_tuple=(ws.workspace_id, False)
      input_status_arr.append(ret_tuple)
      loggr.info(f"\033[1m{hostname} workspace connection. Connection Status: {ret_tuple[1]}\033[0m") 
      continue;
    json_.update({'token':token})
    
  ret_tuple = test_connection(json_, False)  
  input_status_arr.append(ret_tuple)
  loggr.info(f"\033[1m{hostname} workspace connection. Connection Status: {ret_tuple[1]}\033[0m")    
  
modifyWorkspaceConfigFile(input_status_arr)

# COMMAND ----------

dbutils.notebook.exit('OK')
