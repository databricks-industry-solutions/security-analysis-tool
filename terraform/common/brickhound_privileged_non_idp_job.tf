# SAT Permissions Analysis - Privileged Non-IdP Identities Detection Job
# Detects (and optionally remediates) privileged identities (Account Admin /
# Workspace Admin) that are not IdP-managed, plus users/SPs with those roles
# assigned directly. Writes findings to brickhound_privileged_non_idp.

resource "databricks_job" "brickhound_privileged_non_idp" {
  name = "SAT Permissions Analysis - Privileged Non-IdP Identities (Experimental)"

  tags = {
    Application = "SAT"
  }

  dynamic "job_cluster" {
    for_each = var.run_on_serverless ? [] : [1]
    content {
      job_cluster_key = "brickhound_privileged_non_idp_cluster"
      new_cluster {
        data_security_mode = "SINGLE_USER"
        num_workers        = 3
        spark_version      = data.databricks_spark_version.latest_lts.id
        node_type_id       = data.databricks_node_type.smallest.id
        runtime_engine     = "PHOTON"

        dynamic "aws_attributes" {
          for_each = var.cloud_type == "aws" ? [1] : []
          content {
            availability    = "SPOT_WITH_FALLBACK"
            first_on_demand = 1
          }
        }

        dynamic "gcp_attributes" {
          for_each = var.gcp_impersonate_service_account == "" ? [] : [var.gcp_impersonate_service_account]
          content {
            google_service_account = var.gcp_impersonate_service_account
          }
        }
      }
    }
  }

  dynamic "environment" {
    for_each = var.run_on_serverless ? [1] : []
    content {
      environment_key = "default"
      spec {
        client = "5"
      }
    }
  }

  task {
    task_key        = "BrickHoundPrivilegedNonIdp"
    job_cluster_key = var.run_on_serverless ? null : "brickhound_privileged_non_idp_cluster"
    environment_key = var.run_on_serverless ? "default" : null

    notebook_task {
      notebook_path = "${databricks_repo.security_analysis_tool.path}/notebooks/brickhound/06_privileged_non_idp_identities"

      # Detection-only by default. Set remediate=yes deliberately to enable
      # continuous auto-removal of privileged roles from non-IdP identities.
      base_parameters = {
        finding_types       = "account_admin,workspace_admin"
        include_idp_managed = "no"
        remediate           = "no"
      }
    }

    timeout_seconds = 3600 # 1 hour
  }

  # Schedule: weekly (Sunday 4 AM ET), staggered after the other SAT jobs
  schedule {
    quartz_cron_expression = "0 0 4 ? * SUN"
    timezone_id            = "America/New_York"
  }
}

output "brickhound_privileged_non_idp_job_id" {
  description = "The ID of the SAT privileged-non-IdP detection job"
  value       = databricks_job.brickhound_privileged_non_idp.id
}
