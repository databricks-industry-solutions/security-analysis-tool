# Permission Grants for BrickHound App
# Grants app service principal SELECT access to graph tables
# Only applied if app is deployed

# Get the app's service principal (conditional on app deployment)
data "databricks_service_principal" "brickhound_app" {
  count = var.deploy_brickhound_app ? 1 : 0

  application_id = databricks_app.brickhound[0].service_principal_id

  depends_on = [databricks_app.brickhound]
}

# Grant USE SCHEMA permission
resource "databricks_grant" "brickhound_schema" {
  count = var.deploy_brickhound_app ? 1 : 0

  schema = "${local.brickhound_catalog}.${local.brickhound_schema}"

  principal  = data.databricks_service_principal.brickhound_app[0].application_id
  privileges = ["USE_SCHEMA"]

  depends_on = [databricks_app.brickhound]
}

# Grant SELECT on all tables in schema
resource "databricks_grant" "brickhound_tables" {
  count = var.deploy_brickhound_app ? 1 : 0

  schema = "${local.brickhound_catalog}.${local.brickhound_schema}"

  principal  = data.databricks_service_principal.brickhound_app[0].application_id
  privileges = ["SELECT"]

  depends_on = [databricks_grant.brickhound_schema]
}

# Alternative: Grant on specific tables only
# Uncomment these if you want to be more restrictive instead of granting on entire schema

# resource "databricks_grant" "brickhound_vertices" {
#   count = var.deploy_brickhound_app ? 1 : 0
#
#   table = "${local.brickhound_catalog}.${local.brickhound_schema}.brickhound_vertices"
#
#   principal  = data.databricks_service_principal.brickhound_app[0].application_id
#   privileges = ["SELECT"]
#
#   depends_on = [databricks_app.brickhound]
# }
#
# resource "databricks_grant" "brickhound_edges" {
#   count = var.deploy_brickhound_app ? 1 : 0
#
#   table = "${local.brickhound_catalog}.${local.brickhound_schema}.brickhound_edges"
#
#   principal  = data.databricks_service_principal.brickhound_app[0].application_id
#   privileges = ["SELECT"]
#
#   depends_on = [databricks_app.brickhound]
# }
#
# resource "databricks_grant" "brickhound_metadata" {
#   count = var.deploy_brickhound_app ? 1 : 0
#
#   table = "${local.brickhound_catalog}.${local.brickhound_schema}.brickhound_collection_metadata"
#
#   principal  = data.databricks_service_principal.brickhound_app[0].application_id
#   privileges = ["SELECT"]
#
#   depends_on = [databricks_app.brickhound]
# }
