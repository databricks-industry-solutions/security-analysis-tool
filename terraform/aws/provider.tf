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
  source             = "../common/"
  account_console_id = var.account_console_id
  workspace_id       = var.workspace_id
  sqlw_id            = var.sqlw_id
  proxies            = var.proxies
}
