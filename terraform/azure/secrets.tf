### Azure Specific Secrets

resource "databricks_secret" "client_secret" {
  key          = "client-secret"
  string_value = var.client_secret
  scope        = module.common.secret_scope_id

  lifecycle {
    precondition {
      condition     = (var.tenant_id == "") == (var.subscription_id == "")
      error_message = "Set both tenant_id and subscription_id for Entra, or leave both empty for a Databricks-managed service principal."
    }
    precondition {
      condition     = var.skip_account_apis || (var.tenant_id != "" && var.subscription_id != "" && var.account_console_id != "")
      error_message = "Full Azure analysis requires account_console_id, tenant_id, and subscription_id. Set skip_account_apis = true to register this workspace only."
    }
  }
}

resource "databricks_secret" "subscription_id" {
  count        = var.subscription_id == "" ? 0 : 1
  key          = "subscription-id"
  string_value = var.subscription_id
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "tenant_id" {
  count        = var.tenant_id == "" ? 0 : 1
  key          = "tenant-id"
  string_value = var.tenant_id
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "client_id" {
  key          = "client-id"
  string_value = var.client_id
  scope        = module.common.secret_scope_id
}
