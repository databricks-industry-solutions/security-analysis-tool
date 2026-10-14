# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Initializes the setup and configuration of the **Security Analysis Tool (SAT)**.
# MAGIC

# COMMAND ----------

# The initializer only creates the schema and tables, so it skips
# diagnosis/pre_run_config_check -- that notebook validates the legacy sat_scope
# setup and probes GitHub for TruffleHog (10s-timeout network calls), none of
# which the initializer needs. Dropping it also avoids re-running the SDK install
# and initialize a second time.

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

def run_notebook(notebook_path, timeout):
    status = dbutils.notebook.run(notebook_path, timeout)
    if status != "OK":
        loggr.exception(f"Error Encountered in {notebook_path}", status)
        dbutils.notebook.exit()

# COMMAND ----------

# These Setup notebooks are the classic multi-workspace flow: they enumerate
# account workspaces, test connections, enable workspaces, and import the legacy
# Lakeview dashboards. They require account-admin credentials and serve the
# classic driver + dashboard experience, none of which the SAT app uses -- the
# app has its own UI and its collection jobs run per workspace. In app mode
# (config supplied as job parameters) the initializer only creates the schema and
# tables (done above via %run initialize), so skip these to avoid the account
# access they need and the time they take.
_app_mode = bool(_param("analysis_schema_name"))
notebooks = [
    ("1. list_account_workspaces_to_conf_file", 3000),
    ("3. test_connections", 12000),
    ("4. enable_workspaces_for_sat", 3000),
    ("5. import_dashboard_template_lakeview", 3000),
]

if not _app_mode:
    for notebook, timeout in notebooks:
        status=run_notebook(f"{basePath()}/notebooks/Setup/{notebook}", timeout)

# COMMAND ----------

# The intermediate schema is created by initialize for the collection jobs' temp
# tables, so the initializer must not drop it. (The classic driver dropped it as
# end-of-run cleanup; here it would also require BROWSE on the catalog, which the
# app service principal is not granted.) Classic deployments keep the cleanup.
if not _app_mode:
    spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")