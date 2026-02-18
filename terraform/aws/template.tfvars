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
secrets_scanner_cron_expression = "0 0 8 ? * *" # Every day at 8:00 AM

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

#Flag to scan for hardcoded secrets in all the SAT configured workspace notebooks
