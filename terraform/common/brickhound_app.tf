resource "databricks_app" "brickhound" {
  name        = "sat-permissions-exp"
  description = "SAT Permissions Analysis App"

  # OAuth scopes the app requests when forwarding the calling user's token
  # (OBO). `sql` powers the Statement Execution API used to query the
  # brickhound_* tables; `genie` lets the security assistant drive the Genie
  # Conversation API as the signed-in user, so Unity Catalog enforces that
  # user's own grants on the answer. Without a scope, OBO calls return
  # 403 "Invalid scope, required scopes: <name>".
  user_api_scopes = ["sql", "genie"]

  # The app is the source of truth for its configuration: catalog/schema, account
  # id, and credentials are captured in the app's setup flow and stored as Unity
  # Catalog secrets, so no secret-scope bindings are needed here. Only the SQL
  # warehouse is bound, granting the app's service principal CAN_USE.
  resources = [
    {
      name = "warehouse"
      sql_warehouse = {
        id         = var.sqlw_id == "new" ? databricks_sql_endpoint.new[0].id : data.databricks_sql_warehouse.old[0].id
        permission = "CAN_USE"
      }
    }
  ]
}
