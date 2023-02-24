resource "databricks_sql_endpoint" "this" {
  name             = "SAT Warehouse"
  cluster_size     = "Small"
  max_num_clusters = 1

  tags {
    custom_tags {
      key     = "owner"
      value   = data.databricks_current_user.me.user_name
    }
  }
}
