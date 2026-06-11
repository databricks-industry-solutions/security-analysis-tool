# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Initializes the setup and configuration of the **Security Analysis Tool (SAT)**.
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

def run_notebook(notebook_path, timeout):
    status = dbutils.notebook.run(notebook_path, timeout)
    if status != "OK":
        loggr.exception(f"Error Encountered in {notebook_path}", status)
        dbutils.notebook.exit()

# COMMAND ----------

# DBTITLE 1,Run Setup notebooks (guarded by ENABLE_ACCOUNT_CHECKS)
if ENABLE_ACCOUNT_CHECKS:
    notebooks = [
        ("1. list_account_workspaces_to_conf_file", 3000),
        ("3. test_connections", 12000),
        ("4. enable_workspaces_for_sat", 3000),
        ("5. import_dashboard_template_lakeview", 3000),
    ]

    for notebook, timeout in notebooks:
        status = run_notebook(f"{basePath()}/notebooks/Setup/{notebook}", timeout)
else:
    # Single-workspace bootstrap: populate account_workspaces with current workspace
    # so the dashboard has data without needing the account-level API.
    from dbruntime.databricks_repl_context import get_context
    _ctx = get_context()
    _ws_id = str(_ctx.workspaceId)
    _deploy_url = spark.conf.get("spark.databricks.workspaceUrl")
    _schema = json_["analysis_schema_name"]

    # Insert current workspace if not already registered
    spark.sql(f"""
        MERGE INTO {_schema}.account_workspaces AS target
        USING (SELECT '{_ws_id}' AS workspace_id, '{_deploy_url}' AS deployment_url,
                      '{_deploy_url}' AS workspace_name, 'RUNNING' AS workspace_status,
                      true AS analysis_enabled) AS source
        ON target.workspace_id = source.workspace_id
        WHEN NOT MATCHED THEN INSERT *
    """)
    loggr.info(f"[SAT POC] Single-workspace bootstrap: registered workspace {_ws_id} in {_schema}.account_workspaces")
    loggr.info("[SAT POC] Setup notebooks SKIPPED — account checks disabled.")

# COMMAND ----------

spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")
