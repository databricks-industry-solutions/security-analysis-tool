locals {
  # Resolved key names: DEFAULT_SECRET_KEYS merged with per-user overrides.
  # Only the credential secret (client_secret) and the PAT prefix need to live
  # in a secret scope; all other values are passed as direct job base_parameters.
  secret_keys = merge(
    {
      client_secret              = "client-secret"
      workspace_pat_token_prefix = "sat-token"
      # Legacy keys — present here so BYO users who override one entry don't have
      # to re-specify the others; these are NOT written to the scope for new installs.
      account_id           = "account-console-id"
      sql_warehouse_id     = "sql-warehouse-id"
      analysis_schema_name = "analysis_schema_name"
      proxies              = "proxies"
      use_sp_auth          = "use-sp-auth"
      client_id            = "client-id"
      tenant_id            = "tenant-id"
      subscription_id      = "subscription-id"
    },
    var.secret_key_names
  )

  # For `manage_secrets = false` we reference the scope by name only
  # (the provider has no data source for existing scopes; a scope's TF id is its name).
  scope_ref = var.manage_secrets ? databricks_secret_scope.sat[0].id : var.secret_scope_name

  # App config scope: holds analysis_schema_name for the BrickHound App
  # valueFrom binding (BRICKHOUND_SCHEMA env var).
  # WAREHOUSE_ID now resolves from the sql_warehouse resource directly.
  #
  # Resolution order (mirrors dabs/sat/config.py:_resolve_app_config_scope):
  #   1. analysis_schema_name in scope_provided_keys  -> secret_scope_name
  #      (key already in user's scope; app binds there directly, no new scope)
  #   2. manage_secrets = true, no provided key       -> secret_scope_name
  #   3. explicit app_config_scope_name               -> use it
  #   4. fallback                                     -> "sat_app_scope"
  resolved_app_config_scope = (
    contains(var.scope_provided_keys, "analysis_schema_name")
    ? var.secret_scope_name
    : var.manage_secrets
      ? var.secret_scope_name
      : var.app_config_scope_name != ""
        ? var.app_config_scope_name
        : "sat_app_scope"
  )

  # Create the app config scope whenever it differs from the main scope.
  create_app_scope = local.resolved_app_config_scope != var.secret_scope_name

  # Base parameters injected into every SAT notebook_task.
  # Non-secret config values travel here; client_secret stays scope-only.
  sat_base_parameters = {
    secret_scope              = var.secret_scope_name
    secret_key_names          = jsonencode(var.secret_key_names)
    account_id_param          = var.account_console_id
    client_id_param           = var.client_id
    tenant_id_param           = var.tenant_id
    subscription_id_param     = var.subscription_id
    sql_warehouse_id_param    = var.sqlw_id == "new" ? "" : var.sqlw_id
    analysis_schema_name_param = var.analysis_schema_name
    proxies_param             = jsonencode(var.proxies)
    use_sp_auth_param         = tostring(var.use_sp_auth)
  }
}
