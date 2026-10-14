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
        # When the user pre-populated analysis_schema_name in their own scope
        # (scope_provided_keys contains "analysis_schema_name"), bind directly
        # to that scope so SAT never writes to it.  Otherwise use the app
        # config scope SAT owns.
        scope      = contains(var.scope_provided_keys, "analysis_schema_name") ? var.secret_scope_name : local.resolved_app_config_scope
        key        = local.secret_keys["analysis_schema_name"]
        permission = "READ"
      }
    },
    {
      # WAREHOUSE_ID env var resolves from the sql_warehouse resource below.
      # A secret is no longer needed — valueFrom: "warehouse" in app.yaml
      # returns the warehouse ID directly from the sql_warehouse resource,
      # so the granted warehouse and the queried warehouse are always the same.
      name = "warehouse"
      sql_warehouse = {
        id         = var.sqlw_id == "new" ? databricks_sql_endpoint.new[0].id : data.databricks_sql_warehouse.old[0].id
        permission = "CAN_USE"
      }
    }
  ]
}
