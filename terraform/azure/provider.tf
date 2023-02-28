terraform {
  required_providers {
    databricks = { source = "databricks/databricks" }
  }
}

provider "databricks" {
  host       = "https://adb-5571068294043718.18.azuredatabricks.net"
  auth_type  = "azure-cli"
}