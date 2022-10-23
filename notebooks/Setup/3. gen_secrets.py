# Databricks notebook source
# MAGIC %md
# MAGIC #### Generate secrets helper sh file

# COMMAND ----------

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

dfexist = readWorkspaceConfigFile()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceTempView('configured_workspaces') 

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from configured_workspaces

# COMMAND ----------

#overwrite this file. Secrets should not be persisted within any file. This should be a generate, run, destroy op.
def generateSecretsConfigFile(url, scope):  
  all_ws = spark.sql('select workspace_id, ws_token from `configured_workspaces`').collect()
  prefix = getConfigPath()
  with open(f"{prefix}/gen_secrets.sh", "w+") as file:
    file.write('#--------------****************--------------\n')
    file.write('#---SENSITIVE FILE. May contain Personal Access Tokens. Please secure---\n')
    file.write('\n')
    for ws in all_ws:
      cmd = f"""curl --netrc --request POST '{url}/api/2.0/secrets/put' -d '{{"scope":"{scope}", "key":"{ws.ws_token}", "string_value":"<dapireplace>"}}'\n"""
      file.write(cmd)      
    cmd = f"""curl --netrc --request GET '{url}/api/2.0/secrets/list?scope={scope}'\n"""
    file.write(cmd)

# COMMAND ----------

generateSecretsConfigFile(json_['url'], json_['workspace_pat_scope'])

# COMMAND ----------

# MAGIC %sql
# MAGIC --delete from security_analysis.account_workspaces;
# MAGIC --used by dashboard
# MAGIC insert into security_analysis.account_workspaces  (select * from `configured_workspaces` where analysis_enabled = true and workspace_id not in (select workspace_id from security_analysis.account_workspaces)); 

# COMMAND ----------

# MAGIC %md 
# MAGIC #### Look in the Configs folder for generated Files
# MAGIC * ##### Modify and run gen_secrets.sh to generate the secrets to hold your tokens