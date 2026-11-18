# Changelog
All notable changes to this project will be documented in this file.

## [1.0.0]

The first fully **app-based** release of SAT. SAT is now a single Databricks App
that owns the whole experience — setup, data collection, permissions analysis,
secret scanning, alerts, and the security assistant. The classic dashboards, the
standalone Initializer/Driver notebook workflow, and the configuration-vs-best-
practice security checks are retired; 1.0 focuses on access/permissions risk and
exposed secrets, all configured and viewed in the app.

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
- **In-app secret-scan settings** — set scan coverage (all notebooks vs. a recent
  window) and manage custom detection rules directly from the Secrets page; they
  take effect on the next scan with no redeploy or notebook edits.
- **Per-user authorization (OBO)** — the app queries as the signed-in user, so
  Unity Catalog enforces each viewer's own grants on the results. Alert
  create/update/delete is restricted to workspace or account admins.

### Changed

- **Secret scanning defaults to full scans** (`days_back: 0`) so the dashboard
  reflects complete current exposure, and is hardened for heavy concurrent load
  (batched/retried Delta writes, completeness accounting, job-cluster de-duping,
  no artificial run timeouts).
- **Government cloud support** — account-console host resolution now covers AWS
  GovCloud (FedRAMP) and DoD IL5 in addition to commercial AWS, Azure, and GCP.

## [0.1.0]

### Added

- Initial public release version.
