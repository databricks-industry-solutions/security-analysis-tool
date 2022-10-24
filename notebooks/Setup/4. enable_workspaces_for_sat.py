# Databricks notebook source
# MAGIC %run ../Utils/common

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceGlobalTempView('all_workspaces') 

# COMMAND ----------

# MAGIC %sql
# MAGIC --delete from security_analysis.account_workspaces;
# MAGIC insert into security_analysis.account_workspaces  (select * from `global_temp`.`all_workspaces` where analysis_enabled = true and workspace_id not in (select workspace_id from security_analysis.account_workspaces)); 
