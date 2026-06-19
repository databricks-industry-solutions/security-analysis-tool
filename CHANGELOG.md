# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- **Workspace-admin mode (Azure)** — SAT can now run without account-admin credentials. When account-level secrets are not configured, SAT automatically enters workspace-admin mode via `ENABLE_ACCOUNT_CHECKS`, skipping the 13 checks that require Account Admin or Metastore Admin privileges.
- **SP token fallback (Azure)** — when `client-secret` is not in the secret scope, SAT uses the run-as Service Principal's native token via `getContext().apiToken()`.
- **Single-workspace bootstrap** — in workspace-admin mode, the current workspace is registered into `account_workspaces` via MERGE so dashboards render data without account-level discovery.
- **Portable dashboard** — removed hardcoded catalog/schema references from `SAT_Dashboard_definition.json`.
- **Workspace-admin limitations documentation** — added `docs/sat/docs/workspace-admin-limitations.mdx` documenting which checks are skipped and why.
- **Workspace-admin mode test suite** — added `tests/automated/test_workspace_admin_mode.py` validating that account-level checks are skipped, workspace-level checks produce results, and single-workspace bootstrap registers the current workspace.

### Changed

- `notebooks/Utils/initialize.py` — secrets-first config resolution with widget parameter fallback.
- `notebooks/Utils/workspace_bootstrap.py` — Azure SP token fallback; monkey-patch only activates in workspace-only mode.
- `notebooks/diagnosis/pre_run_config_check.py` — secret scope validation skipped when `ENABLE_ACCOUNT_CHECKS` is `False`.
- `notebooks/security_analysis_driver.py` — `accounts_bootstrap` call guarded by `ENABLE_ACCOUNT_CHECKS`.
- `notebooks/security_analysis_initializer.py` — single-workspace bootstrap added for workspace-only mode.

## [0.1.0]

### Added

- Initial public release version.
