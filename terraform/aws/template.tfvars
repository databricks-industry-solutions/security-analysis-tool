databricks_url     = ""
workspace_id       = ""
account_console_id = ""

# Analysis Schema Name Should follow this format: YourUnityCatalogName.SchemaName
# Catalog must exist, schema will be created by SAT
# Hive Metastore is no longer supported
analysis_schema_name = "" #example: sat.security_analysis_tool

### Databricks Service Principal
client_id     = "" // Databricks Service Principal Application ID
client_secret = "" //Databricks Service Principal ID Secret

# Scheduling
job_compute_num_workers = 3
job_schedule_timezone_id = "America/New_York"
driver_cron_expression = "0 0 8 ? * Mon,Wed,Fri" # Every Monday, Wednesday, and Friday at 8:00 AM
secrets_scanner_cron_expression = "0 0 10 ? * *" # Every day at 10:00 AM (offset 2h after the driver to avoid Delta write conflicts)

# If you are behind a proxy, you can specify the proxy server here, if not leave this with the default value
# Example:
# {
#   "http": "http://proxy.example.com:8080",
#   "https": "http://proxy.example.com:8080"
# }
proxies = {}

#Flag to run SAT initializer/Driver on Serverless
run_on_serverless = false # [Only monitor current workspace]

# SQL Warehouse ID (Optional)
# Default: "new" - Will create a new SQL warehouse
# To use an existing warehouse, provide its 16-character ID
# Example: "782228d75bf63e5c"
# sqlw_id = "new"
# sql_warehouse_enable_serverless = true
# sql_warehouse_auto_stop_mins = 120

# Secret Scope Name (Optional)
# Default: "sat_scope"
# Customize to use a different scope name (useful for multiple SAT instances or naming conventions)
# Example: "sat_scope_prod" or "sat_scope_scan1"
# secret_scope_name = "sat_scope"

# Bring Your Own Secret Scope (Optional)
# Set manage_secrets = false if you have a pre-existing secret scope that SAT should read from
# instead of creating its own. SAT will only write the client_secret key (the only true credential).
# When false, ensure the scope exists and the client_secret key is readable by the SAT service principal.
# manage_secrets = true

# Secret Key Name Overrides (Optional)
# If your existing scope uses different key names, map logical names to physical names.
# Only specify the keys you want to override; unspecified keys use SAT defaults.
# Example: { client_secret = "my-sp-client-secret" }
# secret_key_names = {}

# App Config Scope (Optional — only relevant when manage_secrets = false)
# When manage_secrets=false, SAT still needs to write analysis_schema_name and sql-warehouse-id
# to *some* scope for the BrickHound Databricks App to read via valueFrom.
# Leave blank to have SAT create a dedicated "sat_app_scope", or specify an existing scope name.
# app_config_scope_name = ""

#Flag to scan for hardcoded secrets in all the SAT configured workspace notebooks

# Pre-existing scope keys (Optional — only relevant when manage_secrets = false)
# List the logical names of values that are already in your scope.
# SAT will not write them and the BrickHound app binding will point at your scope.
# Supported: client_secret, account_id, client_id, tenant_id, subscription_id,
#            proxies, analysis_schema_name
# Example: scope_provided_keys = ["client_secret", "analysis_schema_name"]
# scope_provided_keys = []
