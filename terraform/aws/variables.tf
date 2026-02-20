variable "databricks_url" {
  description = "Should look like https://<workspace>.cloud.databricks.com"
  type        = string
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.cloud.databricks.com/?o=1234567890123456)"
  type        = string
}

variable "account_console_id" {
  description = "Databricks Account Console ID"
  type        = string
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

variable "warehouse_type" {
  description = "Type of SQL warehouse to deploy: CLASSIC, PRO, or SERVERLESS"
  type        = string
  validation {
    condition     = contains(["CLASSIC", "PRO", "SERVERLESS"], var.warehouse_type)
    error_message = "warehouse_type must be one of: CLASSIC, PROD, or SERVERLESS"
  }
  default = "CLASSIC"
variable "secret_scope_name" {
  description = "Name of secret scope for SAT secrets"
  type        = string
  default     = "sat_scope"
}

### AWS Specific Variables

variable "account_user" {
  description = "Account Console Username"
  type        = string
  default     = " "
}

variable "account_pass" {
  description = "Account Console Password"
  type        = string
  default     = " "
}

variable "use_sp_auth" {
  description = "Authenticate with Service Principal OAuth tokens instead of user and password"
  type        = bool
  default     = true
}

variable "client_id" {
  description = "Service Principal Application (client) ID"
  type        = string
  default     = "value"
}

variable "client_secret" {
  description = "SP Secret"
  type        = string
  default     = "value"
  sensitive   = true
}

variable "analysis_schema_name" {
  type        = string
  description = "Name of the schema to be used for analysis"
}

variable "proxies" {
  type        = map(any)
  description = "Proxies to be used for Databricks API calls"
}

variable "run_on_serverless" {
  type        = bool
  description = "Flag to run SAT initializer/Driver on Serverless"
}

variable "secrets_scanner_cron_expression" {
  type        = string
  description = "Quartz cron expression for the secrets scanner job schedule"
  default     = "0 0 8 ? * *"
}

variable "driver_cron_expression" {
  type        = string
  description = "Quartz cron expression for the driver job schedule"
  default     = "0 0 8 ? * Mon,Wed,Fri"
}

variable "job_compute_num_workers" {
  type        = number
  description = "Number of worker nodes that this cluster should have."
  default     = 5
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

variable "job_schedule_timezone_id" {
  type        = string
  description = "Time zone ID for job schedules."
  default     = "UTC"
  validation {
    condition     = can(regex("^([A-Za-z]+(/[A-Za-z0-9_+\\-]+)+|UTC)$", var.job_schedule_timezone_id))
    error_message = "Must be a valid IANA time zone ID (e.g. America/New_York, Etc/UTC) or UTC."
  }
}

