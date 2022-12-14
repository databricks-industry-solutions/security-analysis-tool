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

import json
out = dbutils.notebook.run('./Utils/accounts_bootstrap', 300, {"json_":json.dumps(json_)})
loggr.info(out)

# COMMAND ----------

readBestPracticesConfigsFile()

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceGlobalTempView('all_workspaces') 

# COMMAND ----------

# MAGIC %md
# MAGIC ##### These are the workspaces we will run the analysis on
# MAGIC ##### Check the workspace_configs.csv and see if analysis_enabled flag is enabled to True if you dont see your workspace

# COMMAND ----------

workspacesdf = spark.sql('select * from `global_temp`.`all_workspaces`')
display(workspacesdf)
workspaces = workspacesdf.collect()

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
  object_storage_encypted = wsrow.object_storage_encypted  
  table_access_control_enabled = wsrow.table_access_control_enabled

  clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
  json_.update({"sso":sso, "scim":scim,"object_storage_encryption":object_storage_encypted, "vpc_peering":vpc_peering_done,"table_access_control_enabled":table_access_control_enabled, 'url':hostname, 'workspace_id': workspace_id, 'cloud_type': cloud_type, 'clusterid':clusterid})
  loggr.info(json_)
  dbutils.notebook.run('./Utils/workspace_bootstrap', 3000, {"json_":json.dumps(json_)})
  dbutils.notebook.run('./Includes/workspace_analysis', 3000, {"json_":json.dumps(json_)})
  dbutils.notebook.run('./Includes/workspace_stats', 1000, {"json_":json.dumps(json_)})
  dbutils.notebook.run('./Includes/workspace_settings', 3000, {"json_":json.dumps(json_)})


for ws in workspaces:
  processWorkspace(ws)
  loggr.info(f"Completed analyzing {ws.workspace_id}!")
    


# COMMAND ----------

# MAGIC %sql
# MAGIC select * from security_analysis.security_checks order by run_id desc, workspaceid asc, check_time asc
