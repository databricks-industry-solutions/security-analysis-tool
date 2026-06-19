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
# MAGIC * **master_name_scope** Secret Scope for Account Name
# MAGIC * **master_name_key** Secret Key for Account Name
# MAGIC * **master_pwd_scope** Secret Scope for Account Password
# MAGIC * **master_pwd_key** Secret Key for Account Password
# MAGIC * **workspace_pat_scope** Secret Scope for Workspace PAT
# MAGIC * **workspace_pat_token_prefix** Secret Key prefix for Workspace PAT. Workspace ID will automatically be appended to this per workspace
# MAGIC * **use_mastercreds** (optional) Use master account credentials for all workspaces
# MAGIC * **sat_version** Version of the SAT version being used

# COMMAND ----------

# DBTITLE 1,Configuration: secret scope first, widget fallback
# Widget parameters as optional overrides (passed via DAB bundle job parameters)
for k in ["warehouse_id", "analysis_catalog", "analysis_schema", "enable_account_checks", "secrets_scope"]:
    dbutils.widgets.text(k, "")


def _try_secret(scope, key):
    """Try to read a secret; return None if scope/key doesn't exist."""
    try:
        val = dbutils.secrets.get(scope=scope, key=key)
        if val and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return None


def _get_widget(key):
    """Get a non-empty widget value, or None."""
    try:
        val = dbutils.widgets.get(key)
        if val and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return None


# Resolve SECRETS_SCOPE: widget override or default
SECRETS_SCOPE = _get_widget("secrets_scope") or "sat_scope"

# --- Resolve configuration: secret scope takes priority, widgets are fallback ---
_secret_account_id = _try_secret(SECRETS_SCOPE, "account-console-id")
_secret_warehouse_id = _try_secret(SECRETS_SCOPE, "sql-warehouse-id")
_secret_schema_name = _try_secret(SECRETS_SCOPE, "analysis_schema_name")

# Final values: secret scope wins, widget is fallback
_warehouse_id = _secret_warehouse_id or _get_widget("warehouse_id")
_schema_name = _secret_schema_name  # may be "catalog.schema" from secrets
if not _schema_name:
    _catalog = _get_widget("analysis_catalog")
    _schema = _get_widget("analysis_schema")
    if _catalog and _schema:
        _schema_name = f"{_catalog}.{_schema}"

if not _warehouse_id:
    raise ValueError(
        "Missing warehouse_id: set it in secret scope (key='sql-warehouse-id') "
        "or pass as widget parameter 'warehouse_id'."
    )
if not _schema_name:
    raise ValueError(
        "Missing analysis schema: set it in secret scope (key='analysis_schema_name') "
        "or pass widget parameters 'analysis_catalog' and 'analysis_schema'."
    )

# Auto-detect ENABLE_ACCOUNT_CHECKS:
#   - If account-console-id exists in secret scope -> account admin (original behavior)
#   - Otherwise check the widget override; default to False (workspace-only mode)
if _secret_account_id:
    ENABLE_ACCOUNT_CHECKS = True
else:
    _widget_flag = _get_widget("enable_account_checks") or "false"
    ENABLE_ACCOUNT_CHECKS = _widget_flag.lower() == "true"

# Derive catalog name from the resolved schema (for intermediate schema, etc.)
ANALYSIS_CATALOG = _schema_name.split(".")[0] if "." in _schema_name else "hive_metastore"

# COMMAND ----------

# DBTITLE 1,Build json_ config (secrets-first, widget-fallback)
import json

# Proxies: try reading from secret scope; default to empty dict if unavailable.
_proxies_raw = _try_secret(SECRETS_SCOPE, "proxies")
_proxies = json.loads(_proxies_raw) if _proxies_raw else {}

json_ = {
    "account_id": _secret_account_id or "",
    "sql_warehouse_id": _warehouse_id,
    "analysis_schema_name": _schema_name,
    "verbosity": "info",
    "maxpages": 10,
    "timebetweencalls": 1,
    "proxies": _proxies,
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
json_.update({"intermediate_schema": intermediate_schema_name})

# COMMAND ----------

json_.update(
    {
        "master_name_scope": SECRETS_SCOPE,
        "master_name_key": "user",
        "master_pwd_scope": SECRETS_SCOPE,
        "master_pwd_key": "pass",
        "workspace_pat_scope": SECRETS_SCOPE,
        "workspace_pat_token_prefix": "sat-token",
        "dashboard_id": "317f4809-8d9d-4956-a79a-6eee51412217",
        "dashboard_folder": f"{basePath()}/dashboards/",
        "dashboard_tag": "SAT",
        "use_mastercreds": True,
        "use_parallel_runs": True,
        # accounts_console: URL for accounts console in special environments (gov cloud, DoD)
        # Leave empty for standard environments. Examples:
        #   - GovCloud (FedRAMP): "https://accounts.cloud.databricks.us"
        #   - DoD (IL4/IL5): See https://docs.databricks.com/aws/en/security/privacy/gov-cloud
        "accounts_console": "",
        "sat_version": "0.7.0",
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
    try:
        use_sp_auth = (
            _try_secret(SECRETS_SCOPE, "use-sp-auth") or "false"
        ).lower() == "true"
        if use_sp_auth:
            sp_auth["use_sp_auth"] = "True"
            sp_auth["client_id"] = _try_secret(SECRETS_SCOPE, "client-id") or ""
    except:
        pass
    json_.update(sp_auth)

# COMMAND ----------

# DBTITLE 1,Azure configurations
if cloud_type == "azure":
    if ENABLE_ACCOUNT_CHECKS:
        # Full Azure SP credentials from secret scope (account admin path)
        json_.update(
            {
                "subscription_id": dbutils.secrets.get(
                    scope=SECRETS_SCOPE, key="subscription-id"
                ),
                "tenant_id": dbutils.secrets.get(
                    scope=SECRETS_SCOPE, key="tenant-id"
                ),
                "client_id": dbutils.secrets.get(
                    scope=SECRETS_SCOPE, key="client-id"
                ),
                "client_secret_key": "client-secret",
                "use_mastercreds": True,
            }
        )
    else:
        # Workspace-only mode: no SP credentials needed; use run-as identity
        print("[SAT] Azure account-level checks DISABLED — skipping SP credential load.")
        json_.update(
            {
                "subscription_id": "",
                "tenant_id": "",
                "client_id": "",
                "client_secret_key": "",
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
    try:
        use_sp_auth = (
            _try_secret(SECRETS_SCOPE, "use-sp-auth") or "false"
        ).lower() == "true"
        if use_sp_auth:
            sp_auth["use_sp_auth"] = "True"
            sp_auth["client_id"] = _try_secret(SECRETS_SCOPE, "client-id") or ""
    except:
        pass
    json_.update(sp_auth)

# COMMAND ----------



# COMMAND ----------


from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

#spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")

# COMMAND ----------

create_schema()
create_security_checks_table()
create_account_info_table()
create_account_workspaces_table()
create_notebooks_secret_scan_results_table()
create_clusters_secret_scan_results_table()
create_workspace_run_complete_table()

# COMMAND ----------

# Initialize best practices
readBestPracticesConfigsFile()

# COMMAND ----------

# Initialize sat dasf mapping
load_sat_dasf_mapping()
