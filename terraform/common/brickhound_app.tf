resource "databricks_app" "brickhound" {
  name        = "sat-permissions-exp"
  description = "SAT Permissions Analysis App"

  # OAuth scopes the app may request when forwarding the calling user's
  # token (OBO). `sql` is required by the Statement Execution API used to
  # query the brickhound_* tables. Without this, OBO calls return
  # 403 "Invalid scope, required scopes: sql".
  user_api_scopes = ["sql"]

  resources = [
    {
      name = "analysis_schema_name"
      secret = {
        scope      = databricks_secret_scope.sat.id
        key        = "analysis_schema_name"
        permission = "READ"
      }
    },
    {
      name = "sql-warehouse-id"
      secret = {
        scope      = databricks_secret_scope.sat.id
        key        = "sql-warehouse-id"
        permission = "READ"
      }
    },
    {
      name = "warehouse"
      sql_warehouse = {
        id         = var.sqlw_id == "new" ? databricks_sql_endpoint.new[0].id : data.databricks_sql_warehouse.old[0].id
        permission = "CAN_USE"
      }
    }
  ]
}
