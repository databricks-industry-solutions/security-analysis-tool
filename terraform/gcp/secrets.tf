### GCP Specific Secrets

resource "databricks_secret" "gs-path-to-json" {
  key          = "gs-path-to-json"
  string_value = var.gs_path_to_json
  scope        = module.common.secret_scope_id
}

resource "databricks_secret" "impersonate-service-account" {
  key          = "impersonate-service-account"
  string_value = var.impersonate_service_account
  scope        = module.common.secret_scope_id
}
