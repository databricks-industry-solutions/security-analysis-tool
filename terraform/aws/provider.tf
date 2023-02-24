terraform {
  required_providers {
    databricks = { source = "databricks/databricks" }
  }
}

provider "databricks" {
  host  = var.databricks_url
  token = var.workspace_PAT
}
