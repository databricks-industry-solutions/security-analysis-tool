databricks_url     = ""
workspace_id       = ""
account_console_id = ""

# Analysis Schema Name Should follow this format: YourUnityCatalogName.SchemaName 
# Catalog must exist, schema will be created by SAT
# Hive Metastore is no longer supported
analysis_schema_name = "" #example: sat.security_analysis_tool 

### Azure Specific Variables
client_id       = ""
client_secret   = ""
tenant_id       = ""
subscription_id = ""

# If you are behind a proxy, you can specify the proxy server here, if not leave this with the default value
# Example:
# {
#   "http": "http://proxy.example.com:8080",
#   "https": "http://proxy.example.com:8080"
# }
proxies = {}

#Flag to run SAT initializer/Driver on Serverless
run_on_serverless = false # [Only monitor current workspace]