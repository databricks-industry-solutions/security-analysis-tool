variable "databricks_url" {
  description = "Should look like https://<workspace>.gcp.databricks.com"
  type        = string
}

### Provider authentication (service principal used to deploy)

variable "client_id" {
  description = "Service Principal Application (client) ID used to authenticate the Databricks provider"
  type        = string
  default     = "value"
}

variable "client_secret" {
  description = "Service Principal OAuth secret used to authenticate the Databricks provider"
  type        = string
  default     = "value"
  sensitive   = true
}

variable "sqlw_id" {
  type        = string
  description = "16 character SQL Warehouse ID: Type new to have one created or enter an existing SQL Warehouse ID"
  validation {
    condition     = can(regex("^(new|[a-f0-9]{16})$", var.sqlw_id))
    error_message = "Format 16 characters (0-9 and a-f). For more details reference: https://docs.databricks.com/administration-guide/account-api/iam-role.html."
  }
  default = "new"
}

variable "sql_warehouse_enable_serverless" {
  type        = bool
  description = "Flag to enable serverless compute for the SQL warehouse"
  default     = false
}

variable "sql_warehouse_auto_stop_mins" {
  type        = number
  description = "Auto stop time in minutes for the SQL warehouse"
  default     = 120
}
