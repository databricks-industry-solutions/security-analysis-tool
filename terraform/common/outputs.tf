output "secret_scope_id" {
  value       = databricks_secret_scope.sat.id
  description = "ID of the created secret scope to add more secrets if necessary"
}

output "initializer_job_id" {
  value       = databricks_job.initializer.id
  description = "Job ID of the initializer notebook"
}

output "driver_job_id" {
  value       = databricks_job.driver.id
  description = "Job ID of the driver notebook"
}
