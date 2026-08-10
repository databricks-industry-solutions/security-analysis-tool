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

variable "cloud_type" {
  description = "Cloud where SAT is being deployed: \"aws\", \"azure\", or \"gcp\". Set by each cloud-specific wrapper module. Gates cloud-specific cluster attributes (e.g., AWS driver-on-demand protection)."
  type        = string
  default     = ""
  validation {
    condition     = contains(["", "aws", "azure", "gcp"], var.cloud_type)
    error_message = "cloud_type must be one of: aws, azure, gcp (or empty)."
  }
}

variable "sat_authorized_principals" {
  description = "Additional principals (user email, service principal applicationId, or group display name) granted READ access on the SAT secret scope. The Terraform-apply identity always receives MANAGE. Keep this list tight — members can read the SAT service principal credentials, which typically hold account-admin privileges."
  type        = list(string)
  default     = []
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
  type        = map(any)
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

variable "secrets_scanner_cron_expression" {
  type        = string
  description = "Quartz cron expression for the secrets scanner job schedule. Default is 10:00 UTC daily, offset 2 hours after the Driver job to avoid Delta write conflicts on shared control tables (security_checks, account_info, run_number_table)."
  default     = "0 0 10 ? * *"
}

variable "driver_cron_expression" {
  type        = string
  description = "Quartz cron expression for the driver job schedule"
  default     = "0 0 8 ? * Mon,Wed,Fri"
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

variable "manage_secrets" {
  type        = bool
  description = "When true (default), SAT creates the secret scope and writes the client_secret. Set to false to bring a pre-existing scope — SAT will only validate that the required secret key is readable."
  default     = true
}

variable "secret_key_names" {
  type        = map(string)
  description = "Override map from logical key name to physical secret key name (e.g. { client_secret = \"my-sp-secret\" }). Unspecified keys use SAT defaults."
  default     = {}
}

variable "app_config_scope_name" {
  type        = string
  description = "Secret scope for BrickHound app valueFrom bindings (analysis_schema_name, sql-warehouse-id). Defaults to secret_scope_name. Only relevant when manage_secrets=false and you need to keep your credential scope pristine."
  default     = ""
}

variable "client_id" {
  type        = string
  description = "Service Principal Application (client) ID"
  default     = ""
}

variable "tenant_id" {
  type        = string
  description = "Azure Tenant ID (Azure only)"
  default     = ""
}

variable "subscription_id" {
  type        = string
  description = "Azure Subscription ID (Azure only)"
  default     = ""
}

variable "use_sp_auth" {
  type        = bool
  description = "Use Service Principal OAuth authentication (AWS and GCP only)"
  default     = true
}

variable "scope_provided_keys" {
  type        = list(string)
  description = "Logical key names that are pre-populated in the user's existing scope and must not be written by SAT. Mirrors the scope_contains checkbox in the DABS installer. Supported values: client_secret, account_id, client_id, tenant_id, subscription_id, proxies, analysis_schema_name."
  default     = []
}
