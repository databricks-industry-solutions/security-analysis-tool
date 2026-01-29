variable "account_console_id" {
  type        = string
  description = "Databricks Account ID"
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.azuredatabricks.net/?o=1234567890123456)"
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

variable "secret_scope_name" {
  description = "Name of secret scope for SAT secrets"
  type        = string
  default     = "sat_scope"
}

variable "notification_email" {
  type        = string
  description = "Optional user email for notifications. If not specified, current user's email will be used"
  default     = ""
}

variable "provisioner_name" {
  type        = string
  description = "Optional owner tag value for SQL warehouse compute resources; defaults to the current user."
  default     = ""
}

variable "gcp_impersonate_service_account" {
  type        = string
  description = "GCP Service Account to impersonate (e.g. xyz-sa-2@project.iam.gserviceaccount.com)"
  default     = ""
}

variable "analysis_schema_name" {
  type        = string
  description = "Name of the schema to be used for analysis"
}

variable "proxies" {
  type        = map
  description = "Proxies to be used for Databricks API calls"
}

variable "run_on_serverless" {
  type        = bool
  description = "Flag to run SAT initializer/Driver on Serverless"
}

variable "job_compute_num_workers" {
  type        = number
  description = "Number of worker nodes that this cluster should have."
  default     = 5
}

variable "job_schedule_timezone_id" {
  type        = string
  description = "Time zone ID for job schedules. The system default is UTC; For more details: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
  default     = "UTC"
  validation {
    condition     = can(regex("^([A-Za-z]+(/[A-Za-z0-9_+\\-]+)+|UTC)$", var.job_schedule_timezone_id))
    error_message = "Must be a valid IANA time zone ID (e.g. America/New_York, Etc/UTC) or UTC."
  }
}

variable "driver_cron_expression" {
  type        = string
  description = "Quartz cron expression for the driver job schedule"
  default     = "0 0 7 ? * Mon,Wed,Fri"
  validation {
    condition = (
      can(regex("^\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+([ ]+\\S+)?$", trimspace(var.driver_cron_expression)))
      &&
      can(regex("^[0-9A-Za-z,*/?LW#\\-\\s]+$", trimspace(var.driver_cron_expression)))
    )
    error_message = "Must be a Quartz-style cron with 6 or 7 fields and only contain typical Quartz cron characters. For more details: http://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html."
  }
}

variable "secrets_scanner_cron_expression" {
  type        = string
  description = "Quartz cron expression for the secrets scanner job schedule"
  default     = "0 0 8 * * ?"
  validation {
  condition = (
      can(regex("^\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+[ ]+\\S+([ ]+\\S+)?$", trimspace(var.secrets_scanner_cron_expression)))
      &&
      can(regex("^[0-9A-Za-z,*/?LW#\\-\\s]+$", trimspace(var.secrets_scanner_cron_expression)))
    )
    error_message = "Must be a Quartz-style cron with 6 or 7 fields and only contain typical Quartz cron characters. For more details: http://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html."
  }
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
