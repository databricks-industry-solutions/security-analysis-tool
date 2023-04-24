### Azure Specific Secrets

resource "databricks_secret" "client_secret" {
  key          = "client-secret"
  string_value = var.client_secret
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "subscription_id" {
  key          = "subscription-id"
  string_value = var.subscription_id
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "tenant_id" {
  key          = "tenant-id"
  string_value = var.tenant_id
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "client_id" {
  key          = "client-id"
  string_value = var.client_id
  scope        = module.common.secret_scope_id
}
