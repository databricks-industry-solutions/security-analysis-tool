resource "databricks_secret_scope" "sat" {
  name = var.secret_scope_name
}

# Explicit ACLs on the SAT secret scope.
#
# The stored client_secret for the SAT service principal typically holds
# account-admin privileges. Without explicit ACLs the scope defaults grant
# broad workspace-admin visibility. These rules make the authorized set
# explicit in Terraform and prevent accidental expansion.
#
# Note: The workspace `admins` group has inherent MANAGE on all Databricks-
# backed scopes and cannot be restricted via ACL. Deploy SAT in a workspace
# whose admin membership is already tightly controlled.
resource "databricks_secret_acl" "sat_scope_owner" {
  principal  = data.databricks_current_user.me.user_name
  permission = "MANAGE"
  scope      = databricks_secret_scope.sat.id
}

resource "databricks_secret_acl" "sat_scope_readers" {
  for_each   = toset(var.sat_authorized_principals)
  principal  = each.value
  permission = "READ"
  scope      = databricks_secret_scope.sat.id
}

resource "databricks_secret" "user_email" {
  key          = "user-email-for-alerts"
  string_value = var.notification_email == "" ? data.databricks_current_user.me.user_name : var.notification_email
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

resource "databricks_secret" "analysis_schema_name" {
  key          = "analysis_schema_name"
  string_value = var.analysis_schema_name
  scope        = databricks_secret_scope.sat.id
}

resource "databricks_secret" "proxies" {
  key          = "proxies"
  string_value = jsonencode(var.proxies)
  scope        = databricks_secret_scope.sat.id
}
