resource "databricks_secret_scope" "sat" {
  count = var.manage_secrets ? 1 : 0
  name  = var.secret_scope_name
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
  count      = var.manage_secrets ? 1 : 0
  principal  = data.databricks_current_user.me.user_name
  permission = "MANAGE"
  scope      = databricks_secret_scope.sat[0].id
}

resource "databricks_secret_acl" "sat_scope_readers" {
  for_each   = var.manage_secrets ? toset(var.sat_authorized_principals) : toset([])
  principal  = each.value
  permission = "READ"
  scope      = databricks_secret_scope.sat[0].id
}

# App config scope for BrickHound Databricks App valueFrom bindings.
# Holds only analysis_schema_name + sql-warehouse-id (non-credential config).
# Created separately so manage_secrets=false users keep their credential scope
# pristine while SAT still manages the app config entries.
resource "databricks_secret_scope" "sat_app_config" {
  count = local.create_app_scope ? 1 : 0
  # Use the fully-resolved name, not the raw var which may be "" in the default BYO case.
  name  = local.resolved_app_config_scope
}

# App config secret — analysis_schema_name for the BrickHound App valueFrom
# binding (BRICKHOUND_SCHEMA env var).  This is the only secret the app still
# needs; WAREHOUSE_ID now resolves from the sql_warehouse resource directly.
#
# Skipped when the user pre-populated this key in their own scope
# (scope_provided_keys contains "analysis_schema_name") — SAT must not write
# to a scope it doesn't own, and the app binding is redirected to that scope
# by brickhound_app.tf.
resource "databricks_secret" "app_analysis_schema" {
  count        = contains(var.scope_provided_keys, "analysis_schema_name") ? 0 : 1
  key          = local.secret_keys["analysis_schema_name"]
  string_value = var.analysis_schema_name
  scope = (
    local.create_app_scope
    ? databricks_secret_scope.sat_app_config[0].id
    : local.scope_ref
  )
}
