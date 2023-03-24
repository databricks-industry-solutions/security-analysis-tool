resource "databricks_secret_scope" "sat" {
  name = "sat_scope"
}

resource "databricks_secret" "user-email" {
  key          = "user-email-for-alerts"
  string_value = data.databricks_current_user.me.user_name
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
  string_value = var.sqlw_id == "new" ? databricks_sql_endpoint.new[0].id : data.databricks_sql_warehouse.old[0].id
  scope        = databricks_secret_scope.sat.id
}

### AWS Specific Secrets

#resource "databricks_secret" "user" {
#  key          = "user"
#  string_value = var.account_user
#  scope        = databricks_secret_scope.sat.id
#}
#
#resource "databricks_secret" "pass" {
#  key          = "pass"
#  string_value = var.account_pass
#  scope        = databricks_secret_scope.sat.id
#}

### Azure Specific Secrets

#resource "databricks_secret" "client-secret" {
#  key          = "client-secret"
#  string_value = var.client_secret
#  scope        = databricks_secret_scope.sat.id
#}
#
#resource "databricks_secret" "subscription-id" {
#  key          = "subscription-id"
#  string_value = var.subscription_id
#  scope        = databricks_secret_scope.sat.id
#}
#
#resource "databricks_secret" "tenant-id" {
#  key          = "tenant-id"
#  string_value = var.tenant_id
#  scope        = databricks_secret_scope.sat.id
#}
#
#resource "databricks_secret" "client-id" {
#  key          = "client-id"
#  string_value = var.client_id
#  scope        = databricks_secret_scope.sat.id
#}

### GCP Specific Secrets

resource "databricks_secret" "gs-path-to-json" {
  key          = "gs-path-to-json"
  string_value = var.gs_path_to_json
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "impersonate-service-account" {
  key          = "impersonate-service-account"
  string_value = var.impersonate_service_account
  scope        = databricks_secret_scope.sat.id
}
