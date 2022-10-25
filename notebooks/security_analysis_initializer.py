# Databricks notebook source
# MAGIC %md
# MAGIC Notebook to initialize setup of SAT 

# COMMAND ----------

dbutils.notebook.run('./Setup/1. list_account_workspaces_to_conf_file', 3000)
dbutils.notebook.run('./Setup/2. generate_secrets_setup_file', 3000)
dbutils.notebook.run('./Setup/3. test_connections', 3000)
dbutils.notebook.run('./Setup/4. enable_workspaces_for_sat', 3000)
dbutils.notebook.run('./Setup/5. import_dashboard_template', 3000)
dbutils.notebook.run('./Setup/6. configure_alerts_template (optional)', 3000)

