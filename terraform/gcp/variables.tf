variable "databricks_url" {
  description = "Should look like https://<workspace>.gcp.databricks.com"
  type        = string
}

variable "workspace_id" {
  description = "Should be the string of numbers in the workspace URL arg (e.g. https://<workspace>.gcp.databricks.com/?o=1234567890123456)"
  type        = string
}

variable "workspace_PAT" {
  description = "PAT should look like dapixxxxxxxxxxxxxxxxxxxx"
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

### GCP Specific Variables

variable "gs_path_to_json" {
  type        = string
  description = "File path to this resource in Cloud Storage (as gs://<bucket>/<folder>/<file>.json)"
}

variable "impersonate_service_account" {
  type        = string
  description = "Impersonate Service Account String (e.g. xyz-sa-2@project.iam.gserviceaccount.com)"
}
