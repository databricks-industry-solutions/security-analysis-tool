### AWS Specific Secrets

resource "databricks_secret" "user" {
  key          = "user"
  string_value = var.account_user
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "pass" {
  key          = "pass"
  string_value = var.account_pass
  scope        = module.common.secret_scope_id
}

