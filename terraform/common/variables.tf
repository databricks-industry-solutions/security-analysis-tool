variable "sqlw_id" {
  type        = string
  description = "16 character SQL Warehouse ID: Type new to have one created or enter an existing SQL Warehouse ID"
  validation {
    condition     = can(regex("^(new|[a-f0-9]{16})$", var.sqlw_id))
    error_message = "Format 16 characters (0-9 and a-f). For more details reference: https://docs.databricks.com/administration-guide/account-api/iam-role.html."
  }
  default = "new"
}

variable "cloud_type" {
  description = "Cloud where SAT is being deployed: \"aws\", \"azure\", or \"gcp\". Set by each cloud-specific wrapper module."
  type        = string
  default     = ""
  validation {
    condition     = contains(["", "aws", "azure", "gcp"], var.cloud_type)
    error_message = "cloud_type must be one of: aws, azure, gcp (or empty)."
  }
}

variable "provisioner_name" {
  type        = string
  description = "Optional owner tag value for SQL warehouse compute resources; defaults to the current user."
  default     = ""
}

variable "sql_warehouse_enable_serverless" {
  type        = bool
  description = "Flag to run SQL Warehouse on Serverless Compute"
  default     = false
}

variable "sql_warehouse_auto_stop_mins" {
  type        = number
  description = "Time in minutes until an idle SQL warehouse terminates all clusters and stops. This field is optional. The default is 120, set to 0 to disable the auto stop."
  default     = 120
}
