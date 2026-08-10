### AWS Specific Secrets
#
# Only the credential secret is stored in the scope. All other values
# (account_id, client_id, use_sp_auth, etc.) are passed as direct job
# base_parameters via locals.sat_base_parameters and never need to be secrets.

resource "databricks_secret" "client_secret" {
  count        = var.manage_secrets ? 1 : 0
  key          = module.common.secret_keys_resolved["client_secret"]
  string_value = var.client_secret
  scope        = module.common.secret_scope_id
}
