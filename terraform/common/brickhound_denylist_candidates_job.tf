# SAT Permissions Analysis - Denylist Candidates Job
# Ranks account groups by inactive-member count as candidates for the account
# access denylist. Writes findings to brickhound_denylist_candidates.

resource "databricks_job" "brickhound_denylist_candidates" {
  name = "SAT Permissions Analysis - Denylist Candidates (Experimental)"

  tags = {
    Application = "SAT"
  }

  dynamic "job_cluster" {
    for_each = var.run_on_serverless ? [] : [1]
    content {
      job_cluster_key = "brickhound_denylist_candidates_cluster"
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
    task_key        = "BrickHoundDenylistCandidates"
    job_cluster_key = var.run_on_serverless ? null : "brickhound_denylist_candidates_cluster"
    environment_key = var.run_on_serverless ? "default" : null

    notebook_task {
      notebook_path = "${databricks_repo.security_analysis_tool.path}/notebooks/brickhound/07_denylist_candidates"

      base_parameters = {
        inactive_days = "90"
        min_inactive  = "1"
      }
    }

    timeout_seconds = 3600 # 1 hour
  }

  # Schedule: weekly (Sunday 5 AM ET), staggered after the other SAT jobs
  schedule {
    quartz_cron_expression = "0 0 5 ? * SUN"
    timezone_id            = "America/New_York"
  }
}

output "brickhound_denylist_candidates_job_id" {
  description = "The ID of the SAT denylist-candidates job"
  value       = databricks_job.brickhound_denylist_candidates.id
}
