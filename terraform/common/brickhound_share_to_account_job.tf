# SAT Permissions Analysis - Shared to Account Users Detection Job
# Detects (and optionally remediates) resources shared with the built-in
# "account users" group. Writes findings to brickhound_shared_to_account.

resource "databricks_job" "brickhound_share_to_account" {
  name = "SAT Permissions Analysis - Shared to Account Users (Experimental)"

  tags = {
    Application = "SAT"
  }

  # Use same serverless/cluster pattern as SAT
  dynamic "job_cluster" {
    for_each = var.run_on_serverless ? [] : [1]
    content {
      job_cluster_key = "brickhound_share_to_account_cluster"
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

        # GCP service account impersonation (if configured)
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
    task_key        = "BrickHoundShareToAccount"
    job_cluster_key = var.run_on_serverless ? null : "brickhound_share_to_account_cluster"
    environment_key = var.run_on_serverless ? "default" : null

    notebook_task {
      notebook_path = "${databricks_repo.security_analysis_tool.path}/notebooks/brickhound/05_share_to_account"

      # Detection-only by default. Set remediate=yes deliberately to enable
      # continuous auto-removal of the "account users" ACL entry.
      base_parameters = {
        last_n_days    = "30"
        resource_types = "dashboards,genie,apps"
        remediate      = "no"
      }
    }

    timeout_seconds = 3600 # 1 hour
  }

  # Schedule: weekly (Sunday 3 AM ET), aligned with the BrickHound collection cadence
  schedule {
    quartz_cron_expression = "0 0 3 ? * SUN"
    timezone_id            = "America/New_York"
  }
}

# Output the job ID for reference
output "brickhound_share_to_account_job_id" {
  description = "The ID of the SAT shared-to-account-users detection job"
  value       = databricks_job.brickhound_share_to_account.id
}
