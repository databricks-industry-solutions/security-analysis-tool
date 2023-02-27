resource "databricks_secret_scope" "sat" {
  name = "sat_scope"
}

resource "databricks_secret" "user" {
  key          = "user-email-for-alerts"
  string_value = data.databricks_current_user.me.user_name
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "pass" {
  key          = "pass"
  string_value = var.account_pass
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "pat" {
  key          = "sat-token-${var.workspace_id}"
  string_value = var.workspace_PAT
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "account_console_id" {
  key          = "account-console-id"
  string_value = var.account_console_id
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "sql_warehouse_id" {
  key          = "sql-warehouse-id"
  string_value = databricks_sql_endpoint.this.id
  scope        = databricks_secret_scope.sat.id
}
