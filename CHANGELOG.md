# Changelog
All notable changes to this project will be documented in this file.

## [1.0.0]

The first fully **app-based** release of SAT. SAT is now a single Databricks App
that owns the whole experience — setup, data collection, permissions analysis,
secret scanning, alerts, and the security assistant. The classic dashboards, the
standalone Initializer/Driver notebook workflow, and the core security posture checks are retired — those checks are now native in the
Databricks Governance Hub Security tab. 1.0 focuses on the capabilities
Governance Hub doesn't cover: access/permissions risk and exposed secrets, all
configured and viewed in the app.

### Added

- **Single Security Analysis app** — a unified UI for findings, Principal &
  Resource Analysis, Credential Exposure (secret scanning), alerts, and the
  security assistant. Replaces the General and Executive dashboards.
- **In-app first-run setup** — pick the results catalog/schema and SQL warehouse,
  and (optionally) enter an account ID + service-principal credentials for
  account-wide data. Credentials are stored as Unity Catalog secrets; no secret
  scope is required.
- **In-app job provisioning** — the app creates and manages its own collection
  jobs (initializer, permissions data collection, account reports, secret
  scanner). No notebooks to import or schedule by hand.
- **In-app collection controls** — choose scan scope (this workspace vs. every
  workspace the service principal can reach), serverless vs. classic compute, and
  whether to include notebook/folder permissions.
- **Sync workspaces** — from Data Collection → Manage, SAT discovers the account's
  workspaces and enables the ones the service principal is a workspace admin of, so
  adding (or removing) the service principal as a workspace admin and syncing is all
  it takes to add or drop a workspace from scans. No manual SQL and no re-running a
  collection job. Switching scope to "Multiple workspaces" runs a sync for you, and
  the panel shows how many workspaces the next scan will cover.
- **In-app secret-scan settings** — set scan coverage (all objects vs. a recent
  window) and manage custom detection rules directly from the Secrets page; they
  take effect on the next scan with no redeploy or notebook edits.
- **Per-user authorization (OBO)** — the app queries as the signed-in user, so
  Unity Catalog enforces each viewer's own grants on the results. Alert
  create/update/delete is restricted to workspace or account admins.

### Changed

- **Unified Databricks OAuth authentication on every cloud, including Azure** —
  Microsoft Entra (Azure AD) / MSAL is removed. SAT reads only the Databricks
  account and workspace APIs (no Azure Resource Manager calls), so on Azure the
  service principal uses a **Databricks OAuth secret** generated in the account
  console — no tenant ID or subscription.
- **Secret scanning now covers notebook source, workspace files, and cluster
  configurations**, and each finding is typed (Notebook / File / Cluster) with
  matching filters on the Credential Exposure page.
- **Collection scope governs both resource collection and secret scanning** —
  "This workspace only" scopes both to the current workspace; "Multiple workspaces"
  covers every workspace the service principal administers. On serverless, a
  workspace the compute can't reach (cross-workspace network policy) is skipped and
  recorded, not failed.
- **Secret scanning defaults to full scans** (`days_back: 0`) so the view reflects
  complete current exposure, and is hardened for heavy concurrent load
  (batched/retried Delta writes, completeness accounting, job-cluster de-duping,
  no artificial run timeouts).
- **Changing the results catalog/schema** migrates the account-credential Unity
  Catalog secrets into the new schema and re-provisions the collection jobs
  automatically.
- **Government cloud support** — account-console host resolution now covers AWS
  GovCloud (FedRAMP) and DoD IL5 in addition to commercial AWS, Azure, and GCP.

### Fixed

- **Serverless "Permission denied" in the secret scanner** — scratch directories
  are now created with `tempfile.mkdtemp()` instead of fixed `/tmp` paths (a reused
  serverless container under a different OS user could not write to a fixed path),
  so multi-workspace scans no longer fail with `[Errno 13]`.

## [0.1.0]

### Added

- Initial public release version.
