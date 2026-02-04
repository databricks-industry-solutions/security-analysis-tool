terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.88.0"
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
  analysis_schema_name            = var.analysis_schema_name
  proxies                         = var.proxies
  run_on_serverless               = var.run_on_serverless
  secret_scope_name               = var.secret_scope_name
  secrets_scanner_cron_expression = var.secrets_scanner_cron_expression
  driver_cron_expression          = var.driver_cron_expression
  job_compute_num_workers         = var.job_compute_num_workers
  sql_warehouse_enable_serverless = var.sql_warehouse_enable_serverless
  sql_warehouse_auto_stop_mins    = var.sql_warehouse_auto_stop_mins
}

output "deploy_app" {
  value = "Now please run `databricks apps deploy sat-permission-app --source-code-path /Workspace/Repos/Applications/SAT_TF/app/brickhound`"
}
