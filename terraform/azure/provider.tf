terraform {
  required_providers {
    databricks = { source = "databricks/databricks" }
  }
}

provider "databricks" {
  host      = var.databricks_url
  auth_type = "azure-cli"
}
