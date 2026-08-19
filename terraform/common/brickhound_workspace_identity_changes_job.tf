# SAT Permissions Analysis - Workspace & Identity Changes Detection Job
# Detects (and optionally remediates) identities created/changed outside the AIM
# sync, and non-IdP identities assigned to workspaces. Writes findings to
# brickhound_workspace_identity_changes.

resource "databricks_job" "brickhound_workspace_identity_changes" {
  name = "SAT Permissions Analysis - Workspace & Identity Changes (Experimental)"

  tags = {
    Application = "SAT"
  }

  dynamic "job_cluster" {
    for_each = var.run_on_serverless ? [] : [1]
    content {
      job_cluster_key = "brickhound_workspace_identity_changes_cluster"
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
    task_key        = "BrickHoundWorkspaceIdentityChanges"
    job_cluster_key = var.run_on_serverless ? null : "brickhound_workspace_identity_changes_cluster"
    environment_key = var.run_on_serverless ? "default" : null

    notebook_task {
      notebook_path = "${databricks_repo.security_analysis_tool.path}/notebooks/brickhound/08_workspace_identity_changes"

      # Detection-only by default. Set remediate=yes deliberately to enable
      # continuous removal of non-IdP workspace assignments.
      base_parameters = {
        last_n_days   = "30"
        finding_scope = "workspace_assignment,account_workspace_access,identity_creation,group_membership,admin_grant"
        remediate     = "no"
      }
    }

    timeout_seconds = 3600 # 1 hour
  }

  # Schedule: weekly (Sunday 6 AM ET), staggered after the other SAT jobs
  schedule {
    quartz_cron_expression = "0 0 6 ? * SUN"
    timezone_id            = "America/New_York"
  }
}

output "brickhound_workspace_identity_changes_job_id" {
  description = "The ID of the SAT workspace & identity changes detection job"
  value       = databricks_job.brickhound_workspace_identity_changes.id
}
