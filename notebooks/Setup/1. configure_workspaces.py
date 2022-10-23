# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

#replace values for accounts exec
hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
#dont know workspace token yet.
json_.update({'url':hostname, 'workspace_id': 'accounts', 'cloud_type': cloud_type, 'clusterid':clusterid})


# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

import json
dbutils.notebook.run('../Utils/accounts_bootstrap', 300, {"json_":json.dumps(json_)})

# COMMAND ----------

#this logic does not overwrite the previous config file. It just appends new lines so users can
#easily modify the new lines for new workspaces.
def generateWorkspaceConfigFile(workspace_prefix):
  from pyspark.sql.functions import lit,concat,col
  dfexist = readWorkspaceConfigFile()
  excluded_configured_workspace = ''
  if dfexist is not None: 
    dfexist.createOrReplaceTempView('configured_workspaces')
    excluded_configured_workspace = ' AND workspace_id not in (select workspace_id from `configured_workspaces`)'
  else:
    excluded_configured_workspace = '' #running first time
  #get current workspaces that are not yet configured for analysis
  spsql = f'''select workspace_id, deployment_name as deployment_url, workspace_name, workspace_status from `global_temp`.`acctworkspaces` 
            where workspace_status = "RUNNING" {excluded_configured_workspace}'''
  df = spark.sql(spsql)
  if(not df.rdd.isEmpty()):
    df = df.withColumn("deployment_url", concat(col('deployment_url'), lit('.cloud.databricks.com'))) #AWS
    df = df.withColumn("workspace_token", concat(lit(workspace_prefix), lit('_'), col('workspace_id')))   #added with workspace prfeix
    df = df.withColumn("alert_subscriber_user_id", lit(''))
    df = df.withColumn("analysis_enabled", lit(False)) 
    df = df.withColumn("sso_enabled", lit(False)) 
    df = df.withColumn("scim_enabled", lit(False)) 
    df = df.withColumn("vpc_peering_done", lit(False)) 
    df = df.withColumn("object_storage_encypted", lit(False)) 
    df = df.withColumn("table_access_control_enabled", lit(False)) 
    loggr.info('Appending following workspaces to configurations ...')
    display(df)
    prefix = getConfigPath()
    df.toPandas().to_csv('.{prefix}/workspace_configs.csv', mode='a+', index=False, header=True) #Databricks Runtime 11.2 or above.
  else:
    loggr.info('No new workspaces found for appending into configurations')


# COMMAND ----------

generateWorkspaceConfigFile(json_['workspace_pat_token_prefix'])

# COMMAND ----------

# MAGIC %md 
# MAGIC #### Look in the Configs folder for generated Files
# MAGIC * ##### Modify workspace_configs.csv. Change the analysis_enabled flag to True and add alert_subscriber_user_id for the alerts subscription
# MAGIC * ##### New entries will be added to es
