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
  source                          = "../common/"
  cloud_type                      = "azure"
  sqlw_id                         = var.sqlw_id
  sql_warehouse_enable_serverless = var.sql_warehouse_enable_serverless
  sql_warehouse_auto_stop_mins    = var.sql_warehouse_auto_stop_mins
}
