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

# DBTITLE 1,Widget-based configuration (replaces secret scope)
# ---------- POC: Widget-based configuration (no secret scope) ----------
# These values are passed in as job base_parameters from the DAB bundle.
required_keys = [
    "warehouse_id",
    "analysis_catalog",
    "analysis_schema",
    "enable_account_checks",
]

for k in required_keys:
    dbutils.widgets.text(k, "")

def get_cfg(key, default=None, required=False):
    """Read a widget value; raise if required and missing."""
    v = dbutils.widgets.get(key)
    if v is None or str(v).strip() == "":
        v = default
    if required and (v is None or str(v).strip() == ""):
        raise ValueError(f"Missing required config: {key}")
    return v

WAREHOUSE_ID = get_cfg("warehouse_id", required=True)
ANALYSIS_CATALOG = get_cfg("analysis_catalog", required=True)
ANALYSIS_SCHEMA = get_cfg("analysis_schema", required=True)
ENABLE_ACCOUNT_CHECKS = get_cfg("enable_account_checks", default="false").lower() == "true"

# Build the analysis_schema_name in catalog.schema format expected downstream
ANALYSIS_SCHEMA_NAME = f"{ANALYSIS_CATALOG}.{ANALYSIS_SCHEMA}"

# Legacy reference kept for any downstream code that still reads it
SECRETS_SCOPE = "sat_scope"

# COMMAND ----------

# DBTITLE 1,Build json_ config from widgets (no secrets)
import json

# ---------- POC: Build config from widget params, not secret scope ----------
# account_id is only needed for account-level checks; empty when disabled.
_account_id = ""
if ENABLE_ACCOUNT_CHECKS:
    try:
        _account_id = dbutils.secrets.get(scope=SECRETS_SCOPE, key="account-console-id")
    except Exception:
        raise ValueError(
            "enable_account_checks is true but 'account-console-id' secret is missing. "
            "Either set enable_account_checks=false or create the secret."
        )

# Proxies: try reading from secret scope; default to empty dict if unavailable.
try:
    _proxies = json.loads(dbutils.secrets.get(scope=SECRETS_SCOPE, key="proxies"))
except Exception:
    _proxies = {}

json_ = {
    "account_id": _account_id,
    "sql_warehouse_id": WAREHOUSE_ID,
    "analysis_schema_name": ANALYSIS_SCHEMA_NAME,
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

# DBTITLE 1,Intermediate schema from widget-derived catalog
# Intermediate schema lives in the same catalog as analysis tables
intermediate_schema_name = f"{ANALYSIS_CATALOG}.intermediate_schema"
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

# DBTITLE 1,GCP configurations (skipped for Azure POC)
# GCP configurations — not applicable for Azure-only POC
if cloud_type == "gcp":
    pass

# COMMAND ----------

# DBTITLE 1,Azure configurations (guarded by ENABLE_ACCOUNT_CHECKS)
if cloud_type == "azure":
    if ENABLE_ACCOUNT_CHECKS:
        # Full Azure SP credentials needed only for account-level API calls
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
        # Workspace-only POC: use run-as SP identity; no secrets needed
        loggr = None  # logger not yet initialized; print instead
        print("[SAT POC] Azure account-level checks DISABLED — skipping SP credential load.")
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
# AWS configurations — not applicable for Azure-only POC
if cloud_type == "aws":
    pass

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

