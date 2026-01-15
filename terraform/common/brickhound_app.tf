# BrickHound Web App Deployment
# Deploys the BrickHound Flask app for interactive permissions analysis
# Only deployed if deploy_brickhound_app variable is true

locals {
  # Extract catalog and schema from analysis_schema_name
  # Format: "catalog.schema" or "`catalog`.`schema`"
  brickhound_catalog = replace(split(".", var.analysis_schema_name)[0], "`", "")
  brickhound_schema  = replace(split(".", var.analysis_schema_name)[1], "`", "")

  # Determine warehouse ID (new or existing)
  brickhound_warehouse_id = var.sqlw_id == "new" ? databricks_sql_endpoint.new[0].id : var.sqlw_id
}

# Conditional deployment based on variable
resource "databricks_app" "brickhound" {
  count = var.deploy_brickhound_app ? 1 : 0

  name = "brickhound-sat"

  description = "BrickHound - Databricks Permissions Analysis (integrated with SAT)"

  # Source code from deployed Git repo
  source_code_path = "${databricks_repo.security_analysis_tool.path}/app/brickhound"

  # App configuration
  config {
    command = ["python", "working_app.py"]
  }

  # Environment variables (templated from Terraform)
  env = [
    {
      name  = "BRICKHOUND_CATALOG"
      value = local.brickhound_catalog
    },
    {
      name  = "BRICKHOUND_SCHEMA"
      value = local.brickhound_schema
    },
    {
      name  = "WAREHOUSE_ID"
      value = local.brickhound_warehouse_id
    },
    {
      name  = "PORT"
      value = "8000"
    }
  ]

  # Resource requirements
  resources {
    compute {
      size = "small"
    }
  }

  # Health check
  health_check {
    path    = "/health"
    port    = 8000
    timeout = 30
  }

  # Tags
  tags = {
    Application = "SAT-BrickHound"
    Component   = "WebApp"
    Purpose     = "Interactive Permissions Analysis"
  }

  # Dependencies - wait for repo and data collection job
  depends_on = [
    databricks_repo.security_analysis_tool,
    databricks_job.brickhound_data_collection
  ]
}

# Output app URL (conditional on deployment)
output "brickhound_app_url" {
  value       = var.deploy_brickhound_app ? "https://${data.databricks_current_user.me.workspace_url}/apps/${databricks_app.brickhound[0].id}" : "BrickHound app not deployed"
  description = "URL to access BrickHound web application"
}

# Output app ID (conditional on deployment)
output "brickhound_app_id" {
  value       = var.deploy_brickhound_app ? databricks_app.brickhound[0].id : "N/A"
  description = "BrickHound app ID"
}
