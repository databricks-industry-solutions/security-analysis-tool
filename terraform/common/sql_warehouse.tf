locals {
    provisioner_name = var.provisioner_name != "" ? var.provisioner_name: data.databricks_current_user.me.alphanumeric
}

resource "databricks_sql_endpoint" "new" {
  count            = var.sqlw_id == "new" ? 1 : 0
  name             = "SAT Warehouse"
  cluster_size     = "Small"
  max_num_clusters = 1
  auto_stop_mins   = var.sql_warehouse_auto_stop_mins
  enable_serverless_compute = var.sql_warehouse_enable_serverless
  warehouse_type            = var.warehouse_type

  tags {
    custom_tags {
      key   = "owner"
      value = local.provisioner_name
    }
  }
}

data "databricks_sql_warehouse" "old" {
  count = var.sqlw_id == "new" ? 0 : 1
  id    = var.sqlw_id
}
