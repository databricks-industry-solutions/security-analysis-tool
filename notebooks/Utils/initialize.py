# Databricks notebook source
# MAGIC %md
# MAGIC ##### Modify JSON values
# MAGIC * **account_id** Account ID. Can get this from the accounts console
# MAGIC * **export_db** (optional)
# MAGIC * **verify_ssl** (optional)
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

json_ = {"account_id":"dcdbb945-e659-4e8c-b108-db6b3ac3d0eb", "export_db": "logs", "verify_ssl": "False", "verbosity":"debug", 
  "email_alerts": "", "master_name_scope":"sat_master_scope", 
  "master_name_key":"user", "master_pwd_scope":"sat_master_scope", "master_pwd_key":"pass",
      "workspace_pat_scope":"sat_master_scope",  "workspace_pat_token_prefix":"sat_token" , "use_mastercreds":"true"}