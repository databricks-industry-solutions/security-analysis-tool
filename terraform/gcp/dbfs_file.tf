resource "databricks_dbfs_file" "this" {
  source = format("%s%s", var.local_path_to_json, var.json_file_name)
  path   = format("/FileStore/tables/%s", var.json_file_name)
}