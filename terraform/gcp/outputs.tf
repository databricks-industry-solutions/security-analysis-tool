output "initializer_job_id" {
  value       = module.common.initializer_job_id
  description = "Job ID of the initializer notebook"
}

output "driver_job_id" {
  value       = module.common.driver_job_id
  description = "Job ID of the driver notebook"
}
