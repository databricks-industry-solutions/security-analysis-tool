# Databricks notebook source
# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

#replace values for accounts exec
hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
#dont know workspace token yet.
json_.update({'url':hostname, 'workspace_id': 'accounts', 'cloud_type': cloud_type, 'clusterid':clusterid})

# COMMAND ----------

from core.logging_utils import LoggingUtils
import logging
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()


# COMMAND ----------

if cloud_type=='gcp':
    #refresh account level tokens    
    gcp_status1 = dbutils.notebook.run('./Setup/gcp/configure_sa_auth_tokens', 3000)
    if (gcp_status1 != 'OK'):
        loggr.exception('Error Encountered in GCP Step#1', gcp_status1)
        dbutils.notebook.exit()


# COMMAND ----------

import json

out = dbutils.notebook.run('./Utils/accounts_bootstrap', 300, {"json_":json.dumps(json_)})
loggr.info(out)

# COMMAND ----------

readBestPracticesConfigsFile()

# COMMAND ----------

dfexist = getWorkspaceConfig()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceGlobalTempView('all_workspaces') 

# COMMAND ----------

# MAGIC %md
# MAGIC ##### These are the workspaces we will run the analysis on
# MAGIC ##### Check the workspace_configs.csv and security_analysis.account_workspaces if analysis_enabled and see if analysis_enabled flag is enabled to True if you don't see your workspace

# COMMAND ----------

workspacesdf = spark.sql('select * from `global_temp`.`all_workspaces`')
display(workspacesdf)
workspaces = workspacesdf.collect()
if workspaces is None or len(workspaces) == 0:
    loggr.info('Workspaes are not configured for analyis, check the workspace_configs.csv and security_analysis.account_workspaces if analysis_enabled flag is enabled to True. Use security_analysis_initializer to auto configure workspaces for analysis. ')
    #dbutils.notebook.exit("Unsuccessful analysis.")

# COMMAND ----------

def renewWorkspaceTokens(workspace_id):
    if cloud_type=='gcp':
        #refesh workspace level tokens if PAT tokens are not used as the temp tokens expire in 10 hours
        gcp_status2 = dbutils.notebook.run('./Setup/gcp/configure_tokens_for_worksaces', 3000, {"workspace_id":workspace_id})
        if (gcp_status2 != 'OK'):
            loggr.exception('Error Encountered in GCP Step#2', gcp_status2)
            dbutils.notebook.exit()        


# COMMAND ----------

insertNewBatchRun() #common batch number for each run
def processWorkspace(wsrow):
  import json
  hostname = 'https://' + wsrow.deployment_url
  cloud_type = getCloudType(hostname)
  workspace_id = wsrow.workspace_id
  sso = wsrow.sso_enabled
  scim = wsrow.scim_enabled
  vpc_peering_done = wsrow.vpc_peering_done
  object_storage_encrypted = wsrow.object_storage_encrypted  
  table_access_control_enabled = wsrow.table_access_control_enabled

  clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
  json_.update({"sso":sso, "scim":scim,"object_storage_encryption":object_storage_encrypted, "vpc_peering":vpc_peering_done,"table_access_control_enabled":table_access_control_enabled, 'url':hostname, 'workspace_id': workspace_id, 'cloud_type': cloud_type, 'clusterid':clusterid})
  loggr.info(json_)
  retstr = dbutils.notebook.run('./Utils/workspace_bootstrap', 3000, {"json_":json.dumps(json_)})
  if "Completed SAT" not in retstr:
    raise Exception('Workspace Bootstrap failed. Skipping workspace analysis')
  else:
    dbutils.notebook.run('./Includes/workspace_analysis', 3000, {"json_":json.dumps(json_)})
    dbutils.notebook.run('./Includes/workspace_stats', 1000, {"json_":json.dumps(json_)})
    dbutils.notebook.run('./Includes/workspace_settings', 3000, {"json_":json.dumps(json_)})

'''
for ws in workspaces:
  try:
    renewWorkspaceTokens(ws.workspace_id)
    processWorkspace(ws)
    notifyworkspaceCompleted(ws.workspace_id, True)
    loggr.info(f"Completed analyzing {ws.workspace_id}!")
  except Exception as e:
    loggr.info(e)
    notifyworkspaceCompleted(ws.workspace_id, False)
'''

# COMMAND ----------

from concurrent.futures import ThreadPoolExecutor

def combine(ws):
    renewWorkspaceTokens(ws.workspace_id)
    processWorkspace(ws)
    notifyworkspaceCompleted(ws.workspace_id, True)

with ThreadPoolExecutor(max_workers=4) as executor:
  for ws in workspaces:
    try:
        result = executor.submit(combine, ws)
        loggr.info(f"{result.result()}")
        loggr.info(f"Completed analyzing {ws.workspace_id}!")
    except Exception as e:
        loggr.info(e)
        notifyworkspaceCompleted(ws.workspace_id, False)

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from security_analysis.security_checks order by run_id desc, workspaceid asc, check_time asc

# COMMAND ----------

# MAGIC %sql use security_analysis;
# MAGIC select * from workspace_run_complete;
