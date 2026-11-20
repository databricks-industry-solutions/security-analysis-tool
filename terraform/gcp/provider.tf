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
  cloud_type                      = "gcp"
  sqlw_id                         = var.sqlw_id
  sql_warehouse_enable_serverless = var.sql_warehouse_enable_serverless
  sql_warehouse_auto_stop_mins    = var.sql_warehouse_auto_stop_mins
}
