variable "databricks_url" {
  description = "Should look like https://<workspace>.cloud.databricks.com"
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.cloud.databricks.com/?o=1234567890123456)"
}

variable "workspace_PAT" {
  description = "PAT should look like dapixxxxxxxxxxxxxxxxxxxx"
}

variable "account_user" {
  description = "Account Console Username"
}
variable "account_pass" {
  description = "Account Console Password"
}

variable "account_console_id" {
  description = "Databricks Account Console ID"
}
