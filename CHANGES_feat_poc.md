# Changes in `feat/poc` vs `main`

## Summary

Adds **workspace-admin support** to SAT without breaking existing account-admin functionality. Secret scope remains the primary config source — widget parameters serve as fallback only when secrets are unavailable.

**Design principle:** If the runner is an account admin with secret scope configured → original behavior preserved. If not → SP token fallback kicks in automatically.

---

## Modified Files

### `notebooks/Utils/initialize.py`

- **Secrets-first config resolution** — tries `dbutils.secrets.get()` for `sql-warehouse-id`, `analysis_schema_name`, `account-console-id` first. Falls back to widget parameters (`warehouse_id`, `analysis_catalog`, `analysis_schema`) only when secrets are missing.
- **Auto-detects account-admin mode** — if `account-console-id` exists in secret scope, `ENABLE_ACCOUNT_CHECKS = True` automatically. No manual flag needed for account admins.
- Widget override (`enable_account_checks`) available for edge cases where secrets exist but account checks should be skipped.
- AWS/GCP credential blocks **preserved** using `_try_secret()` helper (graceful fallback, no hard failure).
- Intermediate schema derivation unchanged from `main` logic.

### `notebooks/Utils/workspace_bootstrap.py`

- **Azure: secrets-first, SP token fallback** — tries `client-secret` from secret scope. If unavailable, uses the run-as SP native token (`getContext().apiToken()`).
- **AWS/GCP auth paths restored** — original multi-cloud logic preserved (SP auth for AWS, master key for others).
- **Per-workspace PAT fallback preserved** — when `use_mastercreds=False`, reads workspace-specific PAT from scope (with graceful fallback).
- **Monkey-patch only activates in workspace-only mode** — when `client_id` is empty (no SP credentials), patches `SatDBClient._update_token()` to use native token. Does NOT activate for account admins.

### `notebooks/diagnosis/pre_run_config_check.py`

- Secret scope validation **skipped** when `ENABLE_ACCOUNT_CHECKS` is auto-detected as `False`.
- AWS and GCP secret key validation now also guarded by `ENABLE_ACCOUNT_CHECKS`.
- When secrets exist (account admin), all validations run exactly as in `main`.

### `notebooks/security_analysis_driver.py`

- `clusterid` lookup wrapped in try/except — defaults to `"serverless"` on serverless compute.
- `accounts_bootstrap` notebook call guarded by `ENABLE_ACCOUNT_CHECKS`.
- Same `clusterid` fix applied inside `processWorkspace()`.

### `notebooks/security_analysis_initializer.py`

- Setup notebooks (list workspaces, test connections, etc.) run when `ENABLE_ACCOUNT_CHECKS=True` (account admin path — unchanged).
- Single-workspace bootstrap added for workspace-only mode — registers current workspace into `account_workspaces` via MERGE so the dashboard has data.

### `dashboards/SAT_Dashboard_definition.json`

- Removed hardcoded `` `sat`.security_analysis.<table> `` references — tables now unqualified, making the dashboard portable across catalogs.
