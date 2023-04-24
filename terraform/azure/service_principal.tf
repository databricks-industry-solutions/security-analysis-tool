data "databricks_group" "admins" {
  display_name = "admins"
}

resource "databricks_service_principal" "sp" {
  application_id = var.client_id
  display_name   = "SP for Security Analysis Tool"
}

resource "databricks_group_member" "admin" {
  group_id  = data.databricks_group.admins.id
  member_id = databricks_service_principal.sp.id
}
