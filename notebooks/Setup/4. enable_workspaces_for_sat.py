# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 4. enable_workspaces_for_sat.      
# MAGIC **Functionality:** Pulls the worskpaces from config file and pushes them into the schema for the pulldown and join queries.  

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceGlobalTempView('all_workspaces') 
if dfexist.rdd.isEmpty():
    dbutils.notebook.exit("Workspace list is empty. At least one should be configured for analysis and be accessible from current workspace")

# COMMAND ----------

display(dfexist)

# COMMAND ----------

display(spark.sql(f"""insert into {json_["analysis_schema_name"]}.account_workspaces  (select workspace_id, deployment_url, workspace_name, workspace_status, ws_token, analysis_enabled, sso_enabled, scim_enabled, vpc_peering_done, object_storage_encrypted, table_access_control_enabled  from `global_temp`.`all_workspaces` where workspace_id not in (select workspace_id from {json_["analysis_schema_name"]}.account_workspaces))"""))

# COMMAND ----------

display(spark.sql(f"""select * from {json_["analysis_schema_name"]}.account_workspaces""")) 

# COMMAND ----------

dbutils.notebook.exit('OK')
