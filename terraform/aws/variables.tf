variable "databricks_url" {
  description = "Should look like https://<workspace>.cloud.databricks.com"
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.cloud.databricks.com/?o=1234567890123456)"
}

variable "workspace_PAT" {
  description = "PAT should look like dapixxxxxxxxxxxxxxxxxxxx"
}

variable "account_console_id" {
  description = "Databricks Account Console ID"
}

variable "sqlw_id" {
  type = string
  description = "16 character SQL Warehouse ID: Type new to have one created or enter an existing SQL Warehouse ID"
  validation {
      condition     = can(regex("^(new|[a-f0-9]{16})$", var.sqlw_id))
      error_message = "Format 16 characters (0-9 and a-f). For more details reference: https://docs.databricks.com/administration-guide/account-api/iam-role.html"
    }
}

### AWS Specific Variables

variable "account_user" {
  description = "Account Console Username"
}
variable "account_pass" {
  description = "Account Console Password"
}

### Azure Specific Variables

#variable "client_id" {
#  description = "Service Principal Application (client) ID"
#}
#
#variable "tenant_id" {
#  description = "The Directory (tenant) ID for the application registered in Azure AD"
#}
#
#variable "subscription_id" {
#  description = "Azure subscriptionId"
#}
#
#variable "client_secret" {
#  description = "SP Secret"
#}

### GCP Specific Variables

#variable "dbfs_path_prefix" {
#  description = "Path to the JSON on DBFS"
#  default = "/dbfs/FileStore/tables/"
#}
#
#variable "local_path_to_json" {
#  description = "Path to the JSON on your local machine not including the file name (e.g. /Users/first.last/Downloads/)"
#}
#
#variable "json_file_name" {
#  description = "Service Account Key File name (e.g. SA_1_key.json)"
#}
#
#variable "impersonate_service_account" {
#  description = "Impersonate Service Account String (e.g. xyz-sa-2@project.iam.gserviceaccount.com)"
#}
