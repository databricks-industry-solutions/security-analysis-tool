# Changelog
All notable changes to this project will be documented in this file.

## [0.7.0]

### Added

- **14 new security checks** — DP-10 (disable legacy DBFS), DP-11 (SQL results download), DP-12 (web terminal disabled), DP-13 (DBFS file browser disabled), GOV-38 (disable legacy table ACL), GOV-39 (personal compute policy), GOV-40 (AI/BI embedding policy), GOV-41 (secret scope ACLs), GOV-42 (jobs run as service principal), IA-8 (PAT token creation restricted), IA-9 (SP secret staleness), NS-10 (serverless egress network policy), INFO-41 (account-level ESM enforcement), INFO-42 (Git repo allowlist).
- **Security checks audit document** — `docs/sat_checks_audit.md` with full per-check rationale, removal justifications, severity change analysis, and new check specifications.

### Changed

- **12 severity upgrades** — DP-2 (Low→Medium), DP-6 (Low→Medium), DP-8 (Medium→High), GOV-10 (Low→Medium), GOV-11 (Low→Medium), GOV-13 (Medium→High), GOV-14 (Low→High), GOV-35 (Medium→High), INFO-37 (Low→Medium), INFO-38 (Low→High), INFO-39 (Low→Medium), INFO-40 (Low→Medium), NS-6 (Medium→High).
- **5 severity downgrades** — DP-9 (Medium→Low), GOV-4 (Medium→Low), GOV-24 (High→Medium), GOV-26 (High→Medium).

### Removed

- **7 obsolete/non-security checks** — INFO-12 (X-Frame-Options, platform-managed), INFO-13 (X-Content-Type-Options, platform-managed), INFO-14 (X-XSS-Protection, platform-managed), INFO-17 (serverless availability, not a security control), IA-3 (Hive table ACLs, deprecated), GOV-6 (cluster tags, cost management only), GOV-7 (job tags, cost management only).

## [0.6.0]

### Added

- **SAT Permissions Analysis** — New graph-based permissions analysis tool integrated into SAT. Collects all Databricks objects and permissions across account and workspaces. Includes a Databricks web app.
- **Serverless Egress Control security checks** — New checks NS-9 evaluating workspace network policies and serverless egress controls across AWS, Azure, and GCP.
- **GOV-37: Disable Legacy Features check** — New account-level security check detecting whether legacy features are disabled.
- **Cluster Config Secrets Scanning** — Extended the secrets scanner to scan cluster environment variables for hardcoded secrets using TruffleHog. Results unified with notebook scanning in the dashboard.
- **Government / Staging cloud support** — Accounts console authentication now supports gov cloud, DoD, and staging environments.
- **Centralized SDK distribution** — SAT SDK wheel now stored in `lib/` directory for reliable notebook installation across all compute types.

## [0.5.0]

### Added

- **Revamped AI/BI Dashboards** — Fully redesigned dashboards with a tabular approach for a simpler, cleaner look.
- **Secret Scanning** — New feature to scan Databricks notebooks for hardcoded secrets using TruffleHog.
- **Accounts Console IP Allow List check** — New security check for accounts console IP allow list configuration.
- **Streamlined Documentation** — Refined instructions with improved clarity and enhanced readability.

### Fixed

- Various bug fixes.

## [0.1.0]

### Added

- Initial public release version.
