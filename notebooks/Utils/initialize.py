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
# MAGIC * **master_name_scope** Secret Scope that holds the SAT client secret
# MAGIC * **workspace_pat_scope** Secret Scope for Workspace PAT
# MAGIC * **workspace_pat_token_prefix** Secret Key prefix for Workspace PAT. Workspace ID will automatically be appended to this per workspace
# MAGIC * **use_mastercreds** (optional) Use master account credentials for all workspaces
# MAGIC * **sat_version** Version of the SAT version being used
# MAGIC
# MAGIC ##### BYO secret scope / key names
# MAGIC * **secret_scope** Name of the Databricks secret scope SAT reads from (default: ``sat_scope``)
# MAGIC * **secret_key_names** JSON map of logical -> physical key name overrides, e.g.
# MAGIC   ``{"client_secret": "my-sp-secret"}`` (empty = use defaults)
# MAGIC
# MAGIC ##### Direct configuration parameters (new in 0.9)
# MAGIC The values below can be supplied as job ``base_parameters`` (or notebook
# MAGIC widgets) instead of—or in addition to—storing them in the secret scope.
# MAGIC When a parameter is non-empty it takes priority; an empty value falls back
# MAGIC to the scope so that 0.8.x installs continue to work unchanged.
# MAGIC * **account_id_param** – Databricks Account UUID
# MAGIC * **client_id_param** – Service Principal Application (client) ID
# MAGIC * **tenant_id_param** – Azure Tenant ID (Azure only)
# MAGIC * **subscription_id_param** – Azure Subscription ID (Azure only)
# MAGIC * **sql_warehouse_id_param** – SQL Warehouse ID
# MAGIC * **analysis_schema_name_param** – Unity Catalog schema for SAT tables
# MAGIC * **proxies_param** – JSON proxy map, e.g. ``{"http": "http://proxy:8080"}``
# MAGIC * **use_sp_auth_param** – ``"true"`` or ``"false"`` (AWS/GCP only)

# COMMAND ----------

import json

# ---------------------------------------------------------------------------
# Widget declarations
# All widgets default to empty string; non-empty value wins over scope lookup.
#
# When running a Setup notebook interactively (not via a job):
#   - The secret_scope widget defaults to "sat_scope" for the common case.
#     If you used a different scope during install, change this widget first.
#   - Leave value widgets blank to read from the scope, or fill them in directly.
# When running via a SAT job, base_parameters populate these automatically.
# ---------------------------------------------------------------------------
dbutils.widgets.text("secret_scope",            "sat_scope", "Secret Scope Name")
dbutils.widgets.text("secret_key_names",         "{}",        "Secret Key Name Overrides (JSON)")
dbutils.widgets.text("account_id_param",         "",          "Account ID")
dbutils.widgets.text("client_id_param",          "",          "Client ID")
dbutils.widgets.text("tenant_id_param",          "",          "Tenant ID (Azure)")
dbutils.widgets.text("subscription_id_param",    "",          "Subscription ID (Azure)")
dbutils.widgets.text("sql_warehouse_id_param",   "",          "SQL Warehouse ID")
dbutils.widgets.text("analysis_schema_name_param","",         "Analysis Schema Name")
dbutils.widgets.text("proxies_param",            "",          "Proxies JSON")
dbutils.widgets.text("use_sp_auth_param",        "",          "Use SP Auth (true/false)")

# ---------------------------------------------------------------------------
# Resolve scope and key map
# ---------------------------------------------------------------------------
SECRETS_SCOPE = dbutils.widgets.get("secret_scope").strip() or "sat_scope"

_key_overrides = {}
try:
    _raw = dbutils.widgets.get("secret_key_names").strip()
    if _raw and _raw != "{}":
        _key_overrides = json.loads(_raw)
except Exception:
    pass

SECRET_KEYS = {**DEFAULT_SECRET_KEYS, **_key_overrides}

# COMMAND ----------

# ---------------------------------------------------------------------------
# Resolve non-secret config values (param → scope fallback → safe default)
# ---------------------------------------------------------------------------
_account_id           = resolve_sat_value("account_id",           dbutils.widgets.get("account_id_param"),          SECRETS_SCOPE, SECRET_KEYS)
_sql_warehouse_id     = resolve_sat_value("sql_warehouse_id",     dbutils.widgets.get("sql_warehouse_id_param"),    SECRETS_SCOPE, SECRET_KEYS)
_analysis_schema_name = resolve_sat_value("analysis_schema_name", dbutils.widgets.get("analysis_schema_name_param"),SECRETS_SCOPE, SECRET_KEYS)

_proxies_raw = resolve_sat_value("proxies", dbutils.widgets.get("proxies_param"), SECRETS_SCOPE, SECRET_KEYS, default="{}")
try:
    _proxies = json.loads(_proxies_raw)
except (json.JSONDecodeError, TypeError):
    _proxies = {}

json_ = {
    "account_id":           _account_id,
    "sql_warehouse_id":     _sql_warehouse_id,
    "analysis_schema_name": _analysis_schema_name,
    "verbosity": "info",
    "maxpages":10,
    "timebetweencalls":1,
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
json_.update(
    {
        "intermediate_schema" : intermediate_schema_name
    }

)

# COMMAND ----------

json_.update(
    {
        "master_name_scope": SECRETS_SCOPE,
        "master_pwd_scope":  SECRETS_SCOPE,
        "workspace_pat_scope": SECRETS_SCOPE,
        "workspace_pat_token_prefix": SECRET_KEYS.get("workspace_pat_token_prefix", "sat-token"),
        "client_secret_key": SECRET_KEYS.get("client_secret", "client-secret"),
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
        # Expose scope + key map so child notebooks and diagnostic notebooks
        # can resolve additional keys without re-reading widgets.
        "secret_scope": SECRETS_SCOPE,
        "secret_keys":  SECRET_KEYS,
    }
)


# COMMAND ----------

# DBTITLE 1,GCP configurations
if cloud_type == "gcp":
    sp_auth = {
        "use_sp_auth": "False",
        "client_id": "",
        "client_secret_key": SECRET_KEYS.get("client_secret", "client-secret"),
    }
    _use_sp_raw = resolve_sat_value(
        "use_sp_auth", dbutils.widgets.get("use_sp_auth_param"), SECRETS_SCOPE, SECRET_KEYS,
        default="False", required=False,
    )
    use_sp_auth = str(_use_sp_raw).lower() == "true"
    if use_sp_auth:
        sp_auth["use_sp_auth"] = "True"
        _client_id = resolve_sat_value(
            "client_id", dbutils.widgets.get("client_id_param"), SECRETS_SCOPE, SECRET_KEYS
        )
        if _client_id:
            sp_auth["client_id"] = _client_id
        else:
            import warnings
            warnings.warn("SAT: use_sp_auth=True but client_id is empty; SP auth disabled.", stacklevel=1)
            sp_auth["use_sp_auth"] = "False"
    json_.update(sp_auth)

# COMMAND ----------

# DBTITLE 1,Azure configurations
if cloud_type == "azure":
    json_.update(
        {
            "subscription_id": resolve_sat_value(
                "subscription_id", dbutils.widgets.get("subscription_id_param"), SECRETS_SCOPE, SECRET_KEYS
            ),
            "tenant_id": resolve_sat_value(
                "tenant_id", dbutils.widgets.get("tenant_id_param"), SECRETS_SCOPE, SECRET_KEYS
            ),
            "client_id": resolve_sat_value(
                "client_id", dbutils.widgets.get("client_id_param"), SECRETS_SCOPE, SECRET_KEYS
            ),
            "client_secret_key": SECRET_KEYS.get("client_secret", "client-secret"),
            "use_mastercreds": True,
        }
    )


# COMMAND ----------

# DBTITLE 1,AWS configurations
if cloud_type == "aws":
    sp_auth = {
        "use_sp_auth": "False",
        "client_id": "",
        "client_secret_key": SECRET_KEYS.get("client_secret", "client-secret"),
    }
    _use_sp_raw = resolve_sat_value(
        "use_sp_auth", dbutils.widgets.get("use_sp_auth_param"), SECRETS_SCOPE, SECRET_KEYS,
        default="False", required=False,
    )
    use_sp_auth = str(_use_sp_raw).lower() == "true"
    if use_sp_auth:
        sp_auth["use_sp_auth"] = "True"
        _client_id = resolve_sat_value(
            "client_id", dbutils.widgets.get("client_id_param"), SECRETS_SCOPE, SECRET_KEYS
        )
        if _client_id:
            sp_auth["client_id"] = _client_id
        else:
            import warnings
            warnings.warn("SAT: use_sp_auth=True but client_id is empty; SP auth disabled.", stacklevel=1)
            sp_auth["use_sp_auth"] = "False"
    json_.update(sp_auth)

# COMMAND ----------

# COMMAND ----------

# ---------------------------------------------------------------------------
# Parameters to forward to child notebooks spawned via dbutils.notebook.run()
#
# dbutils.notebook.run() creates an ISOLATED widget context — the child does
# NOT inherit the parent's widgets.  Any spawner (e.g. security_analysis_initializer)
# must pass SAT_CHILD_PARAMS as the arguments dict, otherwise the child's
# initialize.py falls back to scope reads that fail for installs where values
# travel as job base_parameters.
#
# Placed here (after the cloud-specific blocks) so all json_ keys — including
# client_id / tenant_id / subscription_id / use_sp_auth — are fully populated.
# ---------------------------------------------------------------------------
SAT_CHILD_PARAMS = {
    "secret_scope":                SECRETS_SCOPE,
    "secret_key_names":            json.dumps(_key_overrides) if _key_overrides else "{}",
    "account_id_param":            json_.get("account_id", "") or "",
    "client_id_param":             json_.get("client_id", "") or "",
    "tenant_id_param":             json_.get("tenant_id", "") or "",
    "subscription_id_param":       json_.get("subscription_id", "") or "",
    "sql_warehouse_id_param":      json_.get("sql_warehouse_id", "") or "",
    "analysis_schema_name_param":  json_.get("analysis_schema_name", "") or "",
    "proxies_param":               json.dumps(json_.get("proxies", {})),
    "use_sp_auth_param":           str(json_.get("use_sp_auth", "")),
}

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
