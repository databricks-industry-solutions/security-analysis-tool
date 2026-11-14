databricks_url = ""

### Databricks Service Principal used to authenticate Terraform
client_id     = "" // Databricks Service Principal Application ID
client_secret = "" // Databricks Service Principal secret

# SQL Warehouse ID (Optional)
# Default: "new" - Terraform creates a new SQL warehouse
# To use an existing warehouse, provide its 16-character ID (e.g. "782228d75bf63e5c")
# sqlw_id = "new"
# sql_warehouse_enable_serverless = true
# sql_warehouse_auto_stop_mins = 120

# Everything else -- catalog/schema, account id, account credentials, the Genie
# space and model endpoint -- is configured in the app's setup flow after it is
# deployed. The app stores credentials as Unity Catalog secrets.
