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

def _sql_str(val):
    return str(val).replace("'", "''")

def register_current_workspace():
    """Register this workspace in CSV + account_workspaces without account APIs."""
    from dbruntime.databricks_repl_context import get_context

    workspace_id = str(get_context().workspaceId)
    host = hostname or ""
    if host.startswith("https://"):
        deployment_url = host[len("https://") :]
    elif host.startswith("http://"):
        deployment_url = host[len("http://") :]
    else:
        deployment_url = host
    deployment_url = deployment_url.rstrip("/")

    schema = json_["analysis_schema_name"]
    spark.sql(
        f"""INSERT INTO {schema}.account_workspaces
            SELECT '{_sql_str(workspace_id)}', '{_sql_str(deployment_url)}',
                   '{_sql_str(workspace_id)}', 'RUNNING', true
            WHERE NOT EXISTS (
                SELECT 1 FROM {schema}.account_workspaces
                WHERE workspace_id = '{_sql_str(workspace_id)}'
            )"""
    )

    dfexist = readWorkspaceConfigFile()
    already = (
        dfexist is not None
        and len(dfexist.take(1)) > 0
        and dfexist.filter(dfexist.workspace_id == workspace_id).count() > 0
    )
    if already:
        loggr.info(f"workspace_configs.csv already contains workspace {workspace_id}")
        return
    header_value = dfexist is None or len(dfexist.take(1)) == 0
    csv_schema = (
        "workspace_id string, deployment_url string, workspace_name string, "
        "workspace_status string, connection_test boolean, analysis_enabled boolean"
    )
    df = spark.createDataFrame(
        [(workspace_id, deployment_url, workspace_id, "RUNNING", True, True)],
        csv_schema,
    )
    prefix = getConfigPath()
    df.toPandas().to_csv(
        f"{prefix}/workspace_configs.csv",
        mode="a+",
        index=False,
        header=header_value,
    )
    loggr.info(f"Registered workspace {workspace_id} ({deployment_url}) for SAT")

def disable_account_level_checks():
    """Avoid FAIL scores for account checks that were not collected."""
    account_check_ids = [
        "3", "8", "35", "36", "39", "103", "110", "111", "112", "119", "122", "124",
    ]
    if (
        cloud_type == "azure"
        and str(json_.get("tenant_id", "")).strip()
        and str(json_.get("subscription_id", "")).strip()
    ):
        account_check_ids = [i for i in account_check_ids if i != "8"]
    in_list = ",".join(account_check_ids)
    table = f"{json_['analysis_schema_name']}.security_best_practices"
    spark.sql(f"UPDATE {table} SET enable = 0 WHERE id IN ({in_list})")
    loggr.info(f"Disabled account-level SAT checks: {in_list}")

# COMMAND ----------

notebooks = [
    ("1. list_account_workspaces_to_conf_file", 3000),
    ("3. test_connections", 12000),
    ("4. enable_workspaces_for_sat", 3000),
    ("5. import_dashboard_template_lakeview", 3000),
]

if json_.get("workspace_only"):
    loggr.info("Workspace-only install: skip account listing and account connection tests")
    register_current_workspace()
    disable_account_level_checks()
    if str(json_.get("sql_warehouse_id", "")).strip():
        run_notebook(f"{basePath()}/notebooks/Setup/5. import_dashboard_template_lakeview", 3000)
    else:
        loggr.info("Skipping dashboard import; sql-warehouse-id is empty")
else:
    for notebook, timeout in notebooks:
        run_notebook(f"{basePath()}/notebooks/Setup/{notebook}", timeout)

# COMMAND ----------

spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")