output "secret_scope_id" {
  value       = var.manage_secrets ? databricks_secret_scope.sat[0].id : var.secret_scope_name
  description = "ID/name of the SAT secret scope (created or pre-existing)"
}

output "app_config_scope_id" {
  value       = local.resolved_app_config_scope
  description = "Name/ID of the scope used for BrickHound app valueFrom bindings"
}

output "secret_keys_resolved" {
  value       = local.secret_keys
  description = "Resolved logical->physical secret key name map (defaults merged with overrides)"
}

output "sat_base_parameters" {
  value       = local.sat_base_parameters
  description = "Base parameters map injected into every SAT notebook_task"
  sensitive   = false
}

