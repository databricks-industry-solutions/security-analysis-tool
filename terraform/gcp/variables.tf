variable "databricks_url" {
  description = "Should look like https://<workspace>.gcp.databricks.com"
  type        = string
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.gcp.databricks.com/?o=1234567890123456)"
  type        = string
}

variable "account_console_id" {
  description = "Databricks Account Console ID"
  type        = string
}

variable "sqlw_id" {
  type        = string
  description = "16 character SQL Warehouse ID: Type new to have one created or enter an existing SQL Warehouse ID"
  default     = "new"
  validation {
    condition     = can(regex("^(new|[a-f0-9]{16})$", var.sqlw_id))
    error_message = "Format 16 characters (0-9 and a-f). For more details reference: https://docs.databricks.com/administration-guide/account-api/iam-role.html."
  }
}

variable "analysis_schema_name" {
  type        = string
  description = "Name of the schema to be used for analysis"
}

variable "proxies" {
  type        = map
  description = "Proxies to be used for Databricks API calls"
}

### GCP Specific Variables

variable "use_sp_auth" {
  description = "Authenticate with Service Principal OAuth tokens instead of user and password"
  type        = bool
  default     = true
}


variable "client_id" {
  description = "Service Principal (client) ID"
  type        = string
}

variable "client_secret" {
  description = "SP Secret"
  type        = string
}

variable "run_on_serverless" {
  type        = bool
  description = "Flag to run SAT initializer/Driver on Serverless"
  default     = false
}

variable "scan_for_secrets" {
  type        = bool
  description = "Flag to scan for hard coded secrets in notebooks"
}