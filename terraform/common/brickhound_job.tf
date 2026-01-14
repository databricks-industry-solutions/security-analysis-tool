# BrickHound Permissions Analysis Job
# This job collects permissions data and builds the permissions graph for security analysis

resource "databricks_job" "brickhound_data_collection" {
  name = "BrickHound Permissions Analysis - Data Collection"

  tags = {
    Application = "SAT-BrickHound"
    Component   = "Permissions"
    Purpose     = "Security Analysis"
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

  # Schedule: Run weekly (Sunday 2 AM ET)
  # Less frequent than SAT (Mon/Wed/Fri) since permissions change less frequently
  schedule {
    quartz_cron_expression = "0 0 2 ? * Sun"
    timezone_id            = "America/New_York"
    pause_status           = "UNPAUSED"
  }

  email_notifications {
    on_failure                = var.notification_email != "" ? [var.notification_email] : []
    no_alert_for_skipped_runs = true
  }

  notification_settings {
    no_alert_for_skipped_runs = true
    no_alert_for_canceled_runs = true
  }
}

# Output the job ID for reference
output "brickhound_job_id" {
  description = "The ID of the BrickHound data collection job"
  value       = databricks_job.brickhound_data_collection.id
}
