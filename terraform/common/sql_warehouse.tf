resource "databricks_sql_endpoint" "new" {
  count            = var.sqlw_id == "new" ? 1 : 0
  name             = "SAT Warehouse"
  cluster_size     = "Small"
  max_num_clusters = 1
  enable_serverless_compute = var.serverless ? true : false
  warehouse_type = var.serverless ? "PRO" : "CLASSIC"

  tags {
    custom_tags {
      key   = "owner"
      value = data.databricks_current_user.me.alphanumeric
    }
  }
}

data "databricks_sql_warehouse" "old" {
  count = var.sqlw_id == "new" ? 0 : 1
  id    = var.sqlw_id
}
