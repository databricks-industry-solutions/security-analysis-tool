databricks_url       = ""
workspace_id         = ""
account_console_id   = ""

# Should follow this format:
# Unity Catalog: catalog.schema
# Hive Metastore: hive_metastore.schema
analysis_schema_name = ""

### Databricks Service Principal
client_id     = "" // Databricks Service Principal Application ID
client_secret = "" //Databricks Service Principal ID Secret

# If you are behind a proxy, you can specify the proxy server here, if not leave this with the default value
# Example:
# {
#   "http": "http://proxy.example.com:8080",
#   "https": "http://proxy.example.com:8080"
# }
proxies = {} 