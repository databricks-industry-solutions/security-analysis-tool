terraform {
  required_providers {
    databricks = {
      source = "databricks/databricks"
    }
  }
}

provider "databricks" {
  host          = var.databricks_url
  client_id     = var.client_id
  client_secret = var.client_secret
}

module "common" {
  source                          = "../common/"
  account_console_id              = var.account_console_id
  workspace_id                    = var.workspace_id
  sqlw_id                         = var.sqlw_id
  gcp_impersonate_service_account = var.impersonate_service_account
  analysis_schema_name            = var.analysis_schema_name
  proxies                         = var.proxies
  run_on_serverless               = var.run_on_serverless
}
