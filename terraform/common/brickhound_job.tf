# BrickHound Permissions Analysis Job
# This job collects permissions data and builds the permissions graph for security analysis

resource "databricks_job" "brickhound_data_collection" {
  name = "SAT Permissions Analysis - Data Collection (Experimental)"

  tags = {
    Application = "SAT-PermissionsAnalysis"
  }

  # Use same serverless/cluster pattern as SAT
  dynamic "job_cluster" {
    for_each = var.run_on_serverless ? [] : [1]
    content {
      job_cluster_key = "brickhound_cluster"
      new_cluster {
        data_security_mode = "SINGLE_USER"
        num_workers        = 3
        spark_version      = data.databricks_spark_version.latest_lts.id
        node_type_id       = data.databricks_node_type.smallest.id
        runtime_engine     = "PHOTON"

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

  task {
    task_key        = "BrickHoundDataCollection"
    job_cluster_key = var.run_on_serverless ? null : "brickhound_cluster"

    notebook_task {
      notebook_path = "${databricks_repo.security_analysis_tool.path}/notebooks/permission_analysis_data_collection"
    }

    timeout_seconds = 14400  # 4 hours max (permissions collection can take time for large accounts)
  }

  # Schedule: Run daily (2 AM ET)
  # Daily collection ensures fresh permissions data for analysis
  schedule {
    quartz_cron_expression = "0 0 2 * * ?"
    timezone_id            = "America/New_York"
  }
}

# Output the job ID for reference
output "brickhound_job_id" {
  description = "The ID of the BrickHound data collection job"
  value       = databricks_job.brickhound_data_collection.id
}
