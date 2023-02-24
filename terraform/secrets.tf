resource "databricks_secret_scope" "sat" {
  name = "sat_scope_ai"
}

resource "databricks_secret" "user" {
  key          = "user"
  string_value = var.account_user
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
  key          = "account_console_id"
  string_value = var.account_console_id
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "sql_warehouse_id" {
  key          = "sql_warehouse_id"
  string_value = databricks_sql_endpoint.this.id
  scope        = databricks_secret_scope.sat.id
}
