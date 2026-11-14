# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Security Analysis Tool (SAT)** is a Databricks App that analyzes a Databricks account's security posture. It provides:

- **Permission Analysis** (BrickHound) — a graph of who can access what, privilege-escalation paths, resources shared to the whole account, privileged non-IdP identities, and denylist candidates.
- **Credential Exposure** — API keys and tokens found hardcoded in notebook source and cluster configurations (scanned with TruffleHog).
- **Security Assistant** — natural-language questions over the findings, backed by a Databricks Genie space and a model-serving endpoint.

The app is the **sole supported delivery**. The classic notebook + Lakeview-dashboard product (security checks, the driver job, dashboards, the DASF mapping) has been retired. The app serves its own UI, provisions its own collection jobs, and reads results from Unity Catalog.

## Repository Layout

- `app/security-analysis-tool/` — the Flask app. `app.py` serves the UI and API, provisions the collection jobs, and manages credentials. `assets_data.py` holds `ASSETS_ZIP_B64`: a base64-zipped bundle of the `notebooks/`, `configs/`, and `lib/` files the app imports and runs. See `app/security-analysis-tool/README.md`.
- `notebooks/` — the collection notebooks the app provisions as jobs:
  - `security_analysis_initializer.py` — one-time schema/table setup.
  - `permission_analysis_data_collection.py` — the BrickHound graph collector.
  - `security_analysis_secrets_scanner.py` + `Includes/scan_secrets/` — TruffleHog secret scanning.
  - `brickhound/` — permission-graph config (`00_config`) and analysis/detection notebooks (`05`–`07`).
  - `Utils/{initialize,common}.py` — shared config resolution + table/helper functions.
  - `diagnosis/pre_run_config_check.py` — TruffleHog/network pre-flight (run by the scanner).
- `src/securityanalysistoolproject/` — source of the `dbl-sat-sdk` wheel (`SatDBClient`, the Databricks REST client the notebooks use). `src/brickhound/` — the BrickHound graph SDK.
- `lib/` — the prebuilt SDK wheel the notebooks install.
- `configs/` — TruffleHog detectors and the Genie space template.
- `terraform/`, `dabs/` — the two installers; both deploy the app (see Install model).
- `docs/` — the SAT docs website. Do not remove or restructure it.

## Development Commands

### SDK (dbl-sat-sdk)

The notebooks install the SDK wheel from `lib/`. To rebuild it from source:

```bash
cd src/securityanalysistoolproject
python setup.py sdist bdist_wheel
cp dist/dbl_sat_sdk-<version>-py3-none-any.whl ../../lib/
```

**CRITICAL:** after copying a new wheel to `lib/`, update `SDK_VERSION` in `notebooks/Includes/install_sat_sdk.py` to match (currently `0.1.54`). A mismatch makes every notebook fail at install.

### App asset bundle

When you change anything under `notebooks/`, `configs/`, or `lib/`, rebuild the app bundle so the deployed app ships the new files: decode `app/security-analysis-tool/assets_data.py` (`ASSETS_ZIP_B64`), refresh each entry from disk, re-zip (`ZIP_DEFLATED`), and write it back as `ASSETS_ZIP_B64 = "<base64>"`. The app imports this bundle into its service principal's home when it provisions the jobs.

### Install / deploy

`./install.sh` (repo root) drives the DABS installer: it creates a venv, installs `dabs/requirements.txt`, and runs `dabs/main.py`, which renders the bundle and deploys the app via `dabs/setup.sh`. Terraform under `terraform/{aws,azure,gcp}` is the alternative installer. Both **only deploy the app** — see the Install model below.

### App local development

See `app/security-analysis-tool/README.md`.

## Architecture

### The app is the source of truth

Configuration (catalog/schema, SQL warehouse, account id) and account credentials are captured in the app's **setup flow**, not at deploy time. Credentials are stored as **Unity Catalog secrets** in the results schema (`{catalog}.{schema}.<key>`) — there is no `sat_scope` (or any other) secret scope. The rest of the config is persisted in `app_config.json` in the app service principal's home.

### Self-provisioned collection jobs

The app creates and re-creates its own serverless jobs from `PROVISION_SPECS` in `app.py`: the initializer plus five collection jobs (permissions, secrets, shared-to-account, privileged-non-IdP, denylist). Each job receives its configuration as **job parameters** (notably `analysis_schema_name`), so the notebooks need no secret scope. Jobs that read Unity Catalog secrets run on serverless environment **client ≥ 4** (client 3 cannot read them).

### Collection notebooks → Unity Catalog

Results land in the results schema: `brickhound_vertices` / `brickhound_edges` / `brickhound_collection_metadata` (plus `brickhound_shared_to_account`, `brickhound_privileged_non_idp`, `brickhound_denylist_candidates`) and `notebooks_secret_scan_results` / `clusters_secret_scan_results`. The app queries these through the SQL warehouse.

### Install model

Both installers **deploy the app only** and grant it the SQL warehouse; the app does everything else (setup, UC secrets, and self-provisioning its jobs and Genie space). Terraform: `terraform/common/brickhound_app.tf` (`databricks_app`). DABS: `dabs/setup.sh` renders `dabs/dabs_template` and runs `databricks bundle deploy`. Neither creates a secret scope or any collection jobs.

### Authentication

The collection notebooks authenticate to the Databricks REST APIs as the account service principal (`client-id`/`client-secret` read from UC secrets). `SatDBClient` handles AWS/GCP OAuth and Azure MSAL. On serverless compute, collection is scoped to the current workspace.

## Code Patterns

### SDK client pattern

```python
from core.dbclient import SatDBClient

class ExampleClient(SatDBClient):
    def get_example_list(self):
        return self.get("/api/2.0/example/list")
```

### Notebook integration

```python
# %run ./Includes/install_sat_sdk
# %run ./Utils/initialize
# %run ./Utils/common
```

`initialize.py` resolves config from job parameters (`_param`) with a Unity Catalog secret fallback (`_uc_secret`, located via `analysis_schema_name`). Collection notebooks read account credentials from UC secrets the same way (`_sat_cred` / `_bh_cred`), never from a secret scope.

## Schema Comment Sync Rule

The `create_*_table()` functions in `notebooks/Utils/common.py` set table and column comments inline via `_set_table_comment()` and `_set_column_comments()`. Whenever you add, remove, or rename a table or column, update the matching `_set_table_comment` / `_set_column_comments` call so the comments stay in sync. Quick check:

```bash
grep -n "<table_or_column_name>" notebooks/Utils/common.py
```

## Versioning

This project follows Semantic Versioning (MAJOR.MINOR.PATCH):
- **MAJOR:** Incompatible changes (deployment method, breaking API changes)
- **MINOR:** New features (backward-compatible)
- **PATCH:** Bug fixes, documentation updates

See `VERSIONING.md` for the detailed branching strategy.

## Git Workflow Rules

**Feature branches are created from release branches, NEVER from main or other feature branches.**

1. **Always branch from release branches**: Feature branches come from `release/X.X.X` branches (e.g., `release/0.6.0`).
2. **Never branch from main**: Main is protected and should never be used as a source.
3. **Never branch from other feature branches.**
4. **Branch naming**: Descriptive names like `SFE-XXXX_feature_name` or `bugfix/description`.

```bash
git checkout release/0.6.0
git checkout -b SFE-1234_new_feature
# make changes, commit, push
git push -u origin SFE-1234_new_feature
```

## Pre-Commit Typo Check

Before every `git commit`, scan staged files for typos with `codespell`:

```bash
git diff --cached --name-only | xargs codespell
```

If `codespell` is not installed: `pip install codespell`. If it flags an intentional word, add it to `.codespell-ignore` at the repo root and re-run with `--ignore-words=.codespell-ignore`. If typos are found, fix them before committing.

## Communicating Changes

When summarizing changes made during a session, always state:

1. **Git status** — committed and pushed, committed but not pushed, or modified but not committed.
2. **Commit info** (if committed) — short hash, branch, message summary.
3. **Files changed** — the files touched, with a brief description of each change.

This gives users complete visibility into what changed and whether they need to pull updates.

## Cloud-Specific Notes

### AWS
- Service principal with client ID/secret.
- Accounts URL: `https://accounts.cloud.databricks.{domain}`

### Azure
- Requires `tenant_id`, `subscription_id`, `client_id`, `client_secret`.
- Two token endpoints: Databricks Accounts API + Azure Management API.
- Accounts URL: `https://accounts.azuredatabricks.{domain}`; Management URL: `https://management.azure.com`

### GCP
- Service principal with client ID/secret.
- Accounts URL: `https://accounts.gcp.databricks.{domain}`
