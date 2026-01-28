terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.88.0"
    }
  }
}

provider "databricks" {
  host = var.databricks_url
}

module "common" {
  source               = "../common/"
  account_console_id   = var.account_console_id
  workspace_id         = var.workspace_id
  sqlw_id              = var.sqlw_id
  analysis_schema_name = var.analysis_schema_name
  proxies              = var.proxies
  run_on_serverless    = var.run_on_serverless
  secret_scope_name    = var.secret_scope_name
}
