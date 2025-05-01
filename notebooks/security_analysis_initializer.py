# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** security_analysis_initializer.
# MAGIC **Functionality:** Main notebook to initialize setup of SAT
# MAGIC

# COMMAND ----------

# MAGIC %run ./diagnosis/pre_run_config_check

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)

# COMMAND ----------

if cloud_type == "gcp":
    # generate account level tokens for GCP for connection
    gcp_status1 = dbutils.notebook.run(
        f"{basePath()}/notebooks/Setup/gcp/configure_sa_auth_tokens", 3000
    )
    if gcp_status1 != "OK":
        loggr.exception("Error Encountered in GCP Step#1", gcp_status1)
        dbutils.notebook.exit()


# COMMAND ----------

def run_notebook(notebook_path, timeout):
    status = dbutils.notebook.run(notebook_path, timeout)
    if status != "OK":
        loggr.exception(f"Error Encountered in {notebook_path}", status)
        dbutils.notebook.exit()

# COMMAND ----------

notebooks = [
    ("1. list_account_workspaces_to_conf_file", 3000),
    ("3. test_connections", 12000),
    ("4. enable_workspaces_for_sat", 3000),
    ("5. import_dashboard_template_lakeview", 3000),
    ("6. configure_alerts_template", 3000),
    ("9. self_assess_workspace_configuration", 3000),
]

for notebook, timeout in notebooks:
    status=run_notebook(f"{basePath()}/notebooks/Setup/{notebook}", timeout)

# COMMAND ----------

spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")

# COMMAND ----------

# MAGIC %md
# MAGIC Read manual self assesment file and load workspace configurations for analysis
