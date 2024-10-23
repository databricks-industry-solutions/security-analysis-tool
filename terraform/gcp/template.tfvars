databricks_url     = ""
workspace_id       = ""
account_console_id = ""

# Should follow this format:
# Unity Catalog: catalog.schema
# Hive Metastore: hive_metastore.schema
analysis_schema_name = ""

### GCP Specific Variables
client_id                   = ""
client_secret               = ""
gs_path_to_json             = ""
impersonate_service_account = ""

# If you are behind a proxy, you can specify the proxy server here, if not leave this with the default value
# Example:
# {
#   "http": "http://proxy.example.com:8080",
#   "https": "http://proxy.example.com:8080"
# }
proxies = {}