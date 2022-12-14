# Databricks notebook source
# MAGIC %md
# MAGIC ##### Modify JSON values
# MAGIC * **account_id** Account ID. Can get this from the accounts console
# MAGIC * **sql_warehouse_id** SQL Warehouse ID to import dashboard
# MAGIC * **username_for_alerts** A valid Databricks username to receive alerts 
# MAGIC * **verbosity** (optional). debug, info, warning, error, critical
# MAGIC * **master_name_scope** Secret Scope for Account Name
# MAGIC * **master_name_key** Secret Key for Account Name
# MAGIC * **master_pwd_scope** Secret Scope for Account Password
# MAGIC * **master_pwd_key** Secret Key for Account Password
# MAGIC * **workspace_pat_scope** Secret Scope for Workspace PAT
# MAGIC * **workspace_pat_token_prefix** Secret Key prefix for Workspace PAT. Workspace ID will automatically be appended to this per workspace
# MAGIC * **use_mastercreds** (optional) Use master account credentials for all workspaces

# COMMAND ----------

import json

json_ = {
   "account_id":"",
   "sql_warehouse_id":"",
   "username_for_alerts":"",
   "verbosity":"info"
}

# COMMAND ----------

json_.update({
   "master_name_scope":"sat_scope",
   "master_name_key":"user",
   "master_pwd_scope":"sat_scope",
   "master_pwd_key":"pass",
   "workspace_pat_scope":"sat_scope",
   "workspace_pat_token_prefix":"sat_token",
   "dashboard_id":"317f4809-8d9d-4956-a79a-6eee51412217",
   "dashboard_folder":"../../dashboards/",
   "dashboard_tag":"SAT",
   "use_mastercreds":"true"
})

#also obfuscate out json JSONLOCALTEST in common
