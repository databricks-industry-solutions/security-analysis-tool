# Databricks notebook source
# MAGIC %run ../Utils/common

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceGlobalTempView('all_workspaces') 
if dfexist.rdd.isEmpty():
    dbutils.notebook.exit("Workspace list is empty. At least one should be configured for analysis and be accessible from current workspace")

# COMMAND ----------

display(dfexist)

# COMMAND ----------

# MAGIC %sql
# MAGIC --delete from security_analysis.account_workspaces;
# MAGIC insert into security_analysis.account_workspaces  (select workspace_id, deployment_url, workspace_name, workspace_status, ws_token, alert_subscriber_user_id, analysis_enabled, sso_enabled, scim_enabled, vpc_peering_done, object_storage_encrypted, table_access_control_enabled  from `global_temp`.`all_workspaces` where workspace_id not in (select workspace_id from security_analysis.account_workspaces)); 

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from security_analysis.account_workspaces

# COMMAND ----------

dbutils.notebook.exit('OK')
