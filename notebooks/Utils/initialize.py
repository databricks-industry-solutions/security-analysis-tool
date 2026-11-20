# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** initialize
# MAGIC **Functionality:** initializes the necessary configuration values for the rest of the process into a json

# COMMAND ----------

# MAGIC %run ./common

# COMMAND ----------

# replace values for accounts exec
hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Modify JSON values
# MAGIC * **account_id** Account ID. Can get this from the accounts console
# MAGIC * **sql_warehouse_id** SQL Warehouse ID to import dashboard
# MAGIC * **verbosity** (optional). debug, info, warning, error, critical
# MAGIC * **maxpages** for paginated calls, how many max pages to iterate before stopping
# MAGIC * **timebetweencalls** time in secs between api calls. This is to prevent rejections with too many api calls
# MAGIC * **use_mastercreds** (optional) Use master account credentials for all workspaces
# MAGIC * **sat_version** Version of the SAT version being used

# COMMAND ----------

import json

# Configuration comes from the job parameters the SAT app sets when it provisions
# a collection job. Values the app stored as Unity Catalog secrets (in the results
# schema) are read from there as a fallback. No legacy secret scope is involved.
for _w in ("account_id", "sql_warehouse_id", "analysis_schema_name", "proxies",
           "scan_scope", "collect_notebooks"):
    try:
        dbutils.widgets.text(_w, "")
    except Exception:
        pass


def _param(name):
    try:
        value = dbutils.widgets.get(name)
        return value.strip() if value else ""
    except Exception:
        return ""


def _uc_secret(key):
    """Read a Unity Catalog secret from the results schema ({catalog}.{schema}),
    located from the analysis_schema_name parameter. Empty when absent."""
    schema = _param("analysis_schema_name")
    parts = schema.split(".") if schema else []
    if len(parts) >= 2:
        try:
            return dbutils.secrets.get(
                catalog=parts[0].strip("`"), schema=parts[1].strip("`"), key=key)
        except Exception:
            return ""
    return ""


def _conf(param_name, secret_key, default=""):
    return _param(param_name) or _uc_secret(secret_key) or default


json_ = {
    "account_id": _conf("account_id", "account-console-id"),
    "sql_warehouse_id": _conf("sql_warehouse_id", "sql-warehouse-id"),
    "analysis_schema_name": _conf("analysis_schema_name", "analysis_schema_name"),
    "verbosity": "info",
    "maxpages":10,
    "timebetweencalls":1,
    "proxies": json.loads(_conf("proxies", "proxies", "{}") or "{}"),
    # Collection-scope job parameters set by the app (plain params, not secrets).
    "scan_scope": _param("scan_scope") or "current",
    "collect_notebooks": _param("collect_notebooks") or "false",
}

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Intermediate Schema Creation
# MAGIC The following section creates an intermediate schema for storing temporary tables. Previously, these were created as global temp views, but since serverless does not support global temp views, they are now created as tables.

# COMMAND ----------

intermediate_schema_name = (
    f"{json_['analysis_schema_name'].split('.')[0]}.intermediate_schema"
    if '.' in json_['analysis_schema_name']
    else "hive_metastore.intermediate_schema"
)
json_.update(
    {
        "intermediate_schema" : intermediate_schema_name
    }

)

# COMMAND ----------

json_.update(
    {
        "use_mastercreds": True,
        "use_parallel_runs": True,
        # accounts_console: URL for accounts console in special environments (gov cloud, DoD)
        # Leave empty for standard environments. Examples:
        #   - GovCloud (FedRAMP): "https://accounts.cloud.databricks.us"
        #   - DoD (IL4/IL5): See https://docs.databricks.com/aws/en/security/privacy/gov-cloud
        "accounts_console": "",
        "sat_version": "1.0.0",
    }
)


# COMMAND ----------

# DBTITLE 1,GCP configurations
if cloud_type == "gcp":
    sp_auth = {
        "use_sp_auth": "False",
        "client_id": "",
        "client_secret_key": "client-secret",
    }
    if _uc_secret("use-sp-auth").lower() == "true":
        sp_auth["use_sp_auth"] = "True"
        sp_auth["client_id"] = _uc_secret("client-id")
    json_.update(sp_auth)

# COMMAND ----------

# DBTITLE 1,Azure configurations
if cloud_type == "azure":
    # Azure authenticates with Databricks OAuth (M2M), same as AWS/GCP -- no
    # Microsoft Entra / tenant / subscription. The service principal needs a
    # Databricks OAuth secret (client-id / client-secret in the results schema).
    json_.update(
        {
            "client_id": _uc_secret("client-id"),  # Databricks SP application (client) ID
            "client_secret_key": "client-secret",  # Key of the client secret in UC
            "use_mastercreds": True,
        }
    )


# COMMAND ----------

# DBTITLE 1,AWS configurations
if cloud_type == "aws":
    sp_auth = {
        "use_sp_auth": "False",
        "client_id": "",
        "client_secret_key": "client-secret",
    }
    if _uc_secret("use-sp-auth").lower() == "true":
        sp_auth["use_sp_auth"] = "True"
        sp_auth["client_id"] = _uc_secret("client-id")
    json_.update(sp_auth)

# COMMAND ----------

# COMMAND ----------


from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

#spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")

# COMMAND ----------

# Creating the schema/tables and loading reference data is one-time setup owned by
# the initializer job. Re-running it in every collection notebook causes Delta
# metadata-change conflicts on shared tables (e.g. run_number_table) when jobs run
# concurrently. In app mode (config comes from job parameters) this runs only when
# the initializer asks for it via the sat_init parameter; a classic installer
# deployment passes no parameters and always runs it (its driver is sequential, so
# there is no concurrency to conflict with).
_app_mode = bool(_param("analysis_schema_name"))
_run_setup = (not _app_mode) or (_param("sat_init").lower() == "true")

if _run_setup:
    create_schema()
    create_account_info_table()
    create_account_workspaces_table()
    create_notebooks_secret_scan_results_table()
    create_clusters_secret_scan_results_table()
    create_workspace_run_complete_table()

