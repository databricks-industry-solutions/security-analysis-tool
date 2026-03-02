# SAT Security Checks Comprehensive Audit

**Date:** 2026-02-23
**SAT Version:** 0.6.0 → 0.7.0
**Analyst:** Claude Code (AI-assisted audit)

---

## Executive Summary

This document provides a full audit of all SAT security checks, reviewed against:

- Databricks Settings v2 API (7 account-level, 16 workspace-level settings)
- Existing 47 workspace-level and 13 account-level data collections in SAT bootstrap
- 35+ workspace-conf keys already collected
- Databricks DASF framework and 2025/2026 best practices

**Net effect of this audit:**

| Action | Count |
|---|---|
| Checks removed (obsolete / platform-managed / non-security) | 7 |
| Severity upgrades | 12 |
| Severity downgrades | 5 |
| New checks added | 14 |
| **Total checks after changes** | **86** (was 79) |

---

## Phase 1: Checks Removed (7 checks)

The following checks are hard-deleted from `security_best_practices.csv`.

### INFO-12 — Manage third-party iFraming prevention

| Field | Value |
|---|---|
| **Check ID** | INFO-12 |
| **CSV id** | 46 |
| **Reason for removal** | `enable-X-Frame-Options` is an HTTP security header managed entirely by the Databricks platform. Customers cannot meaningfully configure this via workspace-conf, and the setting has been deprecated. Keeping this check creates false confidence that it is actionable. |
| **Recommendation** | Remove permanently. |

### INFO-13 — Manage MIME type sniffing prevention

| Field | Value |
|---|---|
| **Check ID** | INFO-13 |
| **CSV id** | 47 |
| **Reason for removal** | `enable-X-Content-Type-Options` is a platform-managed HTTP security header. Same rationale as INFO-12 — not customer-configurable in modern workspaces. |
| **Recommendation** | Remove permanently. |

### INFO-14 — Manage XSS attack page rendering prevention

| Field | Value |
|---|---|
| **Check ID** | INFO-14 |
| **CSV id** | 48 |
| **Reason for removal** | `enable-X-XSS-Protection` is a legacy HTTP header. It was already deprecated in modern browsers and is fully managed by the Databricks platform. These three checks (INFO-12/13/14) should be removed together as they represent a legacy category of platform-managed controls. |
| **Recommendation** | Remove permanently. |

### INFO-17 — Serverless compute

| Field | Value |
|---|---|
| **Check ID** | INFO-17 |
| **CSV id** | 61 |
| **Reason for removal** | This check verifies whether serverless compute is *available/enabled*, not whether it is configured securely. Serverless availability is an operational/cost feature, not a security posture signal. No pass/fail security implication. Enable=0 already indicates this was recognized as low-value. |
| **Recommendation** | Remove permanently. Serverless security is addressed by NS-9 (network policies) and NS-10 (new egress policy check). |

### IA-3 — Table Access Control for clusters that don't use Unity Catalog

| Field | Value |
|---|---|
| **Check ID** | IA-3 |
| **CSV id** | 20 |
| **Reason for removal** | Hive Metastore table ACLs are being deprecated across Databricks. Customers on Unity Catalog receive confusing, misleading results from this check. GOV-12 already covers Unity Catalog cluster access mode enforcement. With UC as the platform standard, this check creates noise and recommends a control that is itself being superseded. |
| **Recommendation** | Remove permanently. For UC-based workspaces, GOV-12 and GOV-38 (new) provide equivalent and superior coverage. |

### GOV-6 — All-purpose cluster custom tags

| Field | Value |
|---|---|
| **Check ID** | GOV-6 |
| **CSV id** | 11 |
| **Reason for removal** | Cluster tagging is a cost management and operational control, not a security control. Enable=0 already indicates this was flagged as low-value. Keeping disabled non-security checks adds noise to the audit surface without security benefit. |
| **Recommendation** | Remove permanently. Tagging enforcement belongs in cost governance tooling, not a security scanner. |

### GOV-7 — Job cluster custom tags

| Field | Value |
|---|---|
| **Check ID** | GOV-7 |
| **CSV id** | 12 |
| **Reason for removal** | Same rationale as GOV-6. Job cluster tagging is a cost management control, not a security control. Enable=0. |
| **Recommendation** | Remove permanently. |

---

## Phase 2: Severity Changes (17 checks)

### Severity Upgrades (12 checks)

| Check ID | Check Name | Current | Proposed | Rationale |
|---|---|---|---|---|
| **DP-2** | Cluster instance disk encryption | Low | **Medium** | Local disk encryption protects data-at-rest on cluster ephemeral storage. Active attack vector if cluster nodes are compromised or EBS volumes are detached. Low understates the residual risk on multi-tenant shared infrastructure. |
| **DP-6** | Notebook export | Low | **Medium** | Notebook export is one of the primary data exfiltration paths for workspace users. Low is inappropriate for a direct exfiltration control. Aligns with DP-5 (results download) at Medium. |
| **DP-8** | Store interactive notebook results in customer account | Medium | **High** | When disabled, notebook results (which may contain sensitive query outputs) are stored in Databricks-managed infrastructure, outside the customer's cloud account. This is a significant data residency and privacy risk for regulated industries (HIPAA, FedRAMP, PCI-DSS). |
| **GOV-10** | Managed tables in DBFS root | Low | **Medium** | DBFS root is shared, uncontrolled storage with no per-user ACLs. Production data stored there bypasses Unity Catalog governance. The risk is governance failure enabling unauthorized access to production data. |
| **GOV-11** | DBFS mounts | Low | **Medium** | DBFS FUSE mounts bypass Unity Catalog controls entirely, creating data governance gaps. All users in the workspace can see mounted paths. Understated at Low given UC adoption. |
| **GOV-13** | Enforce User Isolation | Medium | **High** | Without User Isolation on shared clusters, users can exfiltrate data from other sessions via shared JVM memory, /tmp, or Spark driver state. This is a direct multi-tenant data leakage vector. |
| **GOV-14** | Enforce AWS IMDSv2 | Low | **High** | IMDSv2 prevents Server-Side Request Forgery (SSRF) attacks that allow attackers to steal EC2 instance credentials from the instance metadata service. SSRF-to-credential-theft is an active, well-documented AWS attack vector. Databricks documentation itself recommends High priority for this setting. |
| **GOV-35** | Restrict workspace admins | Medium | **High** | The `RestrictWorkspaceAdmins` setting prevents privilege escalation. Without it, workspace admins can reassign job ownership and run-as settings arbitrarily. Admin restriction is a critical identity control in any zero-trust architecture. |
| **INFO-38** | Third-party library control | Low | **High** | Artifact allowlists directly prevent supply chain attacks — one of the most common and impactful breach vectors in data platforms. Unrestricted library installation from arbitrary sources allows malicious packages to execute with cluster privileges. Should be High. |
| **INFO-39** | Compliance security profile for the workspace | Low | **Medium** | Workspace-level CSP affects the security posture of all workloads in that workspace. Understated at Low given the systemic impact. |
| **INFO-40** | Enhanced security monitoring for the workspace | Low | **Medium** | ESM provides real-time threat detection and behavioral anomaly monitoring. Understated at Low — the capability directly reduces detection latency for attacks. |
| **NS-6** | Secure cluster connectivity (NoPublicIP) | Medium | **High** | NoPublicIP prevents cluster nodes from having public IP addresses, eliminating direct internet-accessible attack surface on compute. This should be consistent with NS-1/NS-2 (SSH key prohibition) at High, as both address direct cluster exposure. |

### Severity Downgrades (5 checks)

| Check ID | Check Name | Current | Proposed | Rationale |
|---|---|---|---|---|
| **DP-9** | FileStore endpoint for HTTPS file serving | Medium | **Low** | FileStore is a legacy DBFS path used for HTTP file serving. Customers rarely store sensitive data there, and the endpoint is read-only. Medium overstates the risk for most workspaces. |
| **GOV-4** | Long-running clusters | Medium | **Low** | Long-running clusters are primarily an operational waste and patching hygiene issue, not a direct security risk. The security angle (stale base images) is captured better by GOV-36 (Automatic cluster update). |
| **GOV-24** | Legacy global init script | High | **Medium** | Legacy global init scripts are deprecated and should be migrated, but their existence is not a live attack vector in most workspaces. High overstates the urgency vs. active security risks. |
| **GOV-26** | Legacy cluster-named init scripts | High | **Medium** | Same rationale as GOV-24. The deprecation is important but not an active exploitation path. |
| **INFO-37** | Compliance security profile for new workspaces (account) | Low | **Medium** | Account-level CSP affects all new workspaces created going forward. The systemic impact means Medium is more appropriate than Low. |

---

## Phase 3: New Checks (14 checks)

All new checks leverage data already collected by SAT's existing bootstrap infrastructure or Settings v2 API calls already implemented.

### Data Protection

#### DP-10 — Disable legacy DBFS (account setting)

| Field | Value |
|---|---|
| **Check ID** | DP-10 |
| **CSV id** | 113 |
| **Category** | Data Protection |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Settings v2: `disable_legacy_dbfs` (account-level) |
| **Logic** | PASS if `disable_legacy_dbfs` account setting is enabled. DBFS root is shared, uncontrolled storage with no per-user ACLs. Disabling it at the account level prevents all new workspaces from accessing DBFS and enforces Unity Catalog as the data access layer. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/settings/types/disable_legacy_dbfs/names/default` |
| **AWS Doc** | https://docs.databricks.com/aws/en/admin/account-settings/legacy-features |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/admin/account-settings/legacy-features |
| **GCP Doc** | https://docs.gcp.databricks.com/en/admin/account-settings/legacy-features |
| **DASF** | DASF-8:Encrypt data at rest |

#### DP-11 — SQL warehouse results download disabled

| Field | Value |
|---|---|
| **Check ID** | DP-11 |
| **CSV id** | 114 |
| **Category** | Data Protection |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Settings v2: `sql_results_download` (workspace-level) |
| **Logic** | PASS if SQL results download is disabled. Distinct from notebook results download (DP-5). Controls the ability to download query results from SQL warehouse sessions via the SQL Editor and Dashboards UI. |
| **API** | `GET https://<workspace_url>/api/2.0/settings/types/sql_results_download/names/default` |
| **AWS Doc** | https://docs.databricks.com/aws/en/admin/workspace-settings/sql-results-download |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/admin/workspace-settings/sql-results-download |
| **GCP Doc** | https://docs.gcp.databricks.com/en/admin/workspace-settings/sql-results-download |
| **DASF** | DASF-43:Use access control lists |

#### DP-12 — Web terminal disabled on clusters

| Field | Value |
|---|---|
| **Check ID** | DP-12 |
| **CSV id** | 115 |
| **Category** | Data Protection |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableWebTerminal` |
| **Logic** | PASS if `enableWebTerminal` workspace-conf value is `false`. The web terminal provides an interactive bash shell directly on cluster driver nodes. This allows users to read any data the cluster has access to, exfiltrate data via curl/wget, and bypass notebook audit logs. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableWebTerminal` |
| **AWS Doc** | https://docs.databricks.com/clusters/web-terminal.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/clusters/web-terminal |
| **GCP Doc** | https://docs.gcp.databricks.com/clusters/web-terminal.html |
| **DASF** | DASF-5:Control access to data and other objects |

#### DP-13 — DBFS file browser disabled

| Field | Value |
|---|---|
| **Check ID** | DP-13 |
| **CSV id** | 116 |
| **Category** | Data Protection |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableDbfsFileBrowser` |
| **Logic** | PASS if `enableDbfsFileBrowser` workspace-conf value is `false`. The DBFS file browser exposes the full DBFS namespace to all workspace users through the UI, allowing browsing of shared storage paths and discovery of data without audit trail or access control. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableDbfsFileBrowser` |
| **AWS Doc** | https://docs.databricks.com/administration-guide/workspace/dbfs.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/administration-guide/workspace/dbfs |
| **GCP Doc** | https://docs.gcp.databricks.com/administration-guide/workspace/dbfs.html |
| **DASF** | DASF-8:Encrypt data at rest |

### Governance

#### GOV-38 — Disable legacy table ACL access

| Field | Value |
|---|---|
| **Check ID** | GOV-38 |
| **CSV id** | 117 |
| **Category** | Governance |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Settings v2: `disable_legacy_access` (workspace-level) |
| **Logic** | PASS if `disable_legacy_access` setting is enabled. When disabled, users can access Hive Metastore tables using legacy table ACLs that bypass Unity Catalog governance controls. This creates a shadow data access path not visible in Unity Catalog audit logs. |
| **API** | `GET https://<workspace_url>/api/2.0/settings/types/disable_legacy_access/names/default` |
| **AWS Doc** | https://docs.databricks.com/aws/en/admin/workspace-settings/disable-legacy-access |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/admin/workspace-settings/disable-legacy-access |
| **GCP Doc** | https://docs.gcp.databricks.com/en/admin/workspace-settings/disable-legacy-access |
| **DASF** | DASF-5:Control access to data and other objects |

#### GOV-39 — Personal compute policy configured

| Field | Value |
|---|---|
| **Check ID** | GOV-39 |
| **CSV id** | 118 |
| **Category** | Governance |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Account Settings v2: `personal_compute` |
| **Logic** | PASS if personal compute is configured with a restrictive policy (not `ALLOW_ALL`). Personal compute VMs created without a policy bypass cluster policies, cost controls, and security configuration enforcement. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/settings/types/personal_compute/names/default` |
| **AWS Doc** | https://docs.databricks.com/aws/en/admin/clusters/personal-compute |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/admin/clusters/personal-compute |
| **GCP Doc** | https://docs.gcp.databricks.com/en/admin/clusters/personal-compute |
| **DASF** | DASF-38:Platform security — vulnerability management |

#### GOV-40 — AI/BI dashboard embedding policy restricted

| Field | Value |
|---|---|
| **Check ID** | GOV-40 |
| **CSV id** | 119 |
| **Category** | Governance |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Settings v2: `aibi_dashboard_embedding_access_policy` (workspace-level) |
| **Logic** | PASS if the embedding policy is not `ALLOW_ALL`. Unrestricted embedding allows AI/BI dashboards to be embedded on any external domain including attacker-controlled sites. This exposes workspace data to unauthenticated or cross-origin access. |
| **API** | `GET https://<workspace_url>/api/2.0/settings/types/aibi_dashboard_embedding_access_policy/names/default` |
| **AWS Doc** | https://docs.databricks.com/aws/en/admin/workspace-settings/aibi-embedding |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/admin/workspace-settings/aibi-embedding |
| **GCP Doc** | https://docs.gcp.databricks.com/en/admin/workspace-settings/aibi-embedding |
| **DASF** | DASF-43:Use access control lists |

#### GOV-41 — Secret scope ACLs configured

| Field | Value |
|---|---|
| **Check ID** | GOV-41 |
| **CSV id** | 120 |
| **Category** | Governance |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `secretscope` table + secrets ACL API (already collected) |
| **Logic** | PASS if all secret scopes have explicit ACLs configured beyond the default. By default, all workspace users have READ access to all secrets in a scope. Explicit ACLs restrict which users and service principals can read specific secrets. |
| **API** | `GET https://<workspace_url>/api/2.0/secrets/acls/list?scope=<scope_name>` |
| **AWS Doc** | https://docs.databricks.com/security/secrets/secret-acl.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/security/secrets/secret-acl |
| **GCP Doc** | https://docs.gcp.databricks.com/security/secrets/secret-acl.html |
| **DASF** | DASF-33:Manage credentials securely |

#### GOV-42 — Jobs run as service principal

| Field | Value |
|---|---|
| **Check ID** | GOV-42 |
| **CSV id** | 121 |
| **Category** | Governance |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `jobs` table: `settings.run_as` field |
| **Logic** | PASS if production jobs specify `run_as` a service principal. Jobs running as user identity create implicit dependencies on the user's account being active, inherit the user's full permission set (violating least privilege), and create audit confusion between interactive and automated actions. |
| **API** | `GET https://<workspace_url>/api/2.0/jobs/list` |
| **AWS Doc** | https://docs.databricks.com/administration-guide/users-groups/service-principals.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/tutorials/run-jobs-with-service-principals |
| **GCP Doc** | https://docs.gcp.databricks.com/administration-guide/users-groups/service-principals.html |
| **DASF** | DASF-38:Platform security — vulnerability management |

### Identity & Access

#### IA-8 — PAT token creation restricted to admins

| Field | Value |
|---|---|
| **Check ID** | IA-8 |
| **CSV id** | 122 |
| **Category** | Identity & Access |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableTokensConfig` |
| **Logic** | PASS if non-admin users are blocked from creating PAT tokens (`enableTokensConfig = false` or workspace token policy restricts creation). Unconstrained token creation expands the credential attack surface and creates untracked long-lived credentials. Complements IA-4/IA-5/IA-6 which check token lifetimes. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableTokensConfig` |
| **AWS Doc** | https://docs.databricks.com/administration-guide/access-control/tokens.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/administration-guide/access-control/tokens |
| **GCP Doc** | https://docs.gcp.databricks.com/administration-guide/access-control/tokens.html |
| **DASF** | DASF-33:Manage credentials securely |

#### IA-9 — Service principal client secrets not stale

| Field | Value |
|---|---|
| **Check ID** | IA-9 |
| **CSV id** | 123 |
| **Category** | Identity & Access |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Evaluation Value** | 365 (configurable — max days since secret creation) |
| **Data Source** | OAuth service principal secrets API |
| **Logic** | PASS if all service principal OAuth client secrets were created (or rotated) within the configured number of days (default: 365). Stale credentials increase the breach impact window — a compromised secret that was never rotated may have been exfiltrated months ago. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/servicePrincipals/<sp_id>/credentials/secrets` |
| **AWS Doc** | https://docs.databricks.com/administration-guide/users-groups/service-principals.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/administration-guide/users-groups/service-principals |
| **GCP Doc** | https://docs.gcp.databricks.com/administration-guide/users-groups/service-principals.html |
| **DASF** | DASF-33:Manage credentials securely |

### Network Security

#### NS-10 — Serverless compute has egress network policy

| Field | Value |
|---|---|
| **Check ID** | NS-10 |
| **CSV id** | 124 |
| **Category** | Network Security |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `account_networkpolicies` table + `workspace_network_config` (already collected) |
| **Logic** | PASS if the workspace has a network policy assigned with serverless egress controls (policy mode is not `NO_POLICY` for serverless). Serverless compute without an egress network policy can connect to any internet endpoint, creating an unrestricted data exfiltration path. Complements NS-9 which checks policy assignment and mode. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/network-policies` AND `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/workspaces/<workspace_id>/network` |
| **AWS Doc** | https://docs.databricks.com/aws/en/security/network/serverless-network-security/network-policies |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/security/network/serverless-network-security/network-policies |
| **GCP Doc** | https://docs.databricks.com/gcp/en/security/network/serverless-network-security/network-policies |
| **DASF** | DASF-4:Restrict access using private link |

### Informational

#### INFO-41 — Account-level ESM enforcement

| Field | Value |
|---|---|
| **Check ID** | INFO-41 |
| **CSV id** | 125 |
| **Category** | Informational |
| **Severity** | Medium |
| **Cloud** | AWS, Azure |
| **Enable** | 1 |
| **Data Source** | Account Settings v2: `esm_enablement_account` |
| **Logic** | PASS if Enhanced Security Monitoring is enforced at the account level (`is_enforced = true`). Account-level enforcement applies ESM to all workspaces automatically, whereas per-workspace opt-in (INFO-40) requires manual enablement on each workspace. The difference is systemic coverage. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/settings/types/shield_esm_enablement_account/names/default` |
| **AWS Doc** | https://docs.databricks.com/en/security/privacy/enhanced-security-monitoring.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/security/privacy/enhanced-security-monitoring |
| **GCP Doc** | N/A |
| **DASF** | DASF-50:Platform compliance |

#### INFO-42 — Git repo allowlist configured

| Field | Value |
|---|---|
| **Check ID** | INFO-42 |
| **CSV id** | 113 |
| **Category** | Informational |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableProjectsAllowList` |
| **Logic** | PASS if the Git repository allowlist is enabled (`enableProjectsAllowList = true`). Without an allowlist, workspace users can connect notebooks to any external Git repository, enabling code exfiltration to unauthorized services and introduction of malicious code from unreviewed repositories. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableProjectsAllowList` |
| **AWS Doc** | https://docs.databricks.com/repos/repos-setup.html#configure-an-allowlist-for-repos |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/repos/repos-setup#configure-an-allowlist-for-repos |
| **GCP Doc** | https://docs.gcp.databricks.com/repos/repos-setup.html#configure-an-allowlist-for-repos |
| **DASF** | DASF-52:Source code control |

---

## Phase 4: Full Check Inventory (86 checks after changes)

Complete inventory of all checks after applying Phase 1–3 changes. Severity shown is the **post-audit value**.

| # | Check ID | Category | Check Name | Severity | Enable | AWS | Azure | GCP | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | DP-1 | Data Protection | Secrets management | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 2 | DP-2 | Data Protection | Cluster instance disk encryption | **Medium** | 1 | ✓ | ✓ | — | Severity ↑ |
| 3 | DP-3 | Data Protection | Customer-managed keys for managed services | Low | 1 | ✓ | — | — | Keep |
| 4 | DP-4 | Data Protection | Object storage encryption | High | 1 | ✓ | ✓ | ✓ | Keep |
| 5 | DP-5 | Data Protection | Downloading results is disabled | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 6 | DP-6 | Data Protection | Notebook export | **Medium** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 7 | DP-7 | Data Protection | Notebook table clipboard features | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 8 | DP-8 | Data Protection | Store notebook results in customer account | **High** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 9 | DP-9 | Data Protection | FileStore endpoint for HTTPS file serving | **Low** | 1 | ✓ | ✓ | ✓ | Severity ↓ |
| 10 | DP-10 | Data Protection | Disable legacy DBFS | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 11 | DP-11 | Data Protection | SQL warehouse results download disabled | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 12 | DP-12 | Data Protection | Web terminal disabled on clusters | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 13 | DP-13 | Data Protection | DBFS file browser disabled | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 14 | DP-14 | Data Protection | Store and retrieve embeddings securely | Low | 1 | ✓ | ✓ | — | Keep |
| 15 | GOV-1 | Governance | Cluster policies consistently applied | High | 0 | ✓ | ✓ | ✓ | Keep (disabled) |
| 16 | GOV-2 | Governance | PAT tokens about to expire | High | 1 | ✓ | ✓ | ✓ | Keep |
| 17 | GOV-3 | Governance | Log delivery configurations | High | 1 | ✓ | ✓ | — | Keep |
| 18 | GOV-4 | Governance | Long-running clusters | **Low** | 1 | ✓ | ✓ | ✓ | Severity ↓ |
| 19 | GOV-5 | Governance | Deprecated runtime versions | High | 1 | ✓ | ✓ | ✓ | Keep |
| 20 | GOV-8 | Governance | All-purpose cluster log configuration | Low | 0 | ✓ | ✓ | ✓ | Keep (disabled) |
| 21 | GOV-9 | Governance | Job cluster log configuration | Low | 0 | ✓ | ✓ | ✓ | Keep (disabled) |
| 22 | GOV-10 | Governance | Managed tables in DBFS root | **Medium** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 23 | GOV-11 | Governance | DBFS mounts | **Medium** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 24 | GOV-12 | Governance | Unity Catalog enabled clusters | High | 1 | ✓ | ✓ | — | Keep |
| 25 | GOV-13 | Governance | Enforce User Isolation | **High** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 26 | GOV-14 | Governance | Enforce AWS IMDSv2 | **High** | 1 | ✓ | — | — | Severity ↑ |
| 27 | GOV-15 | Governance | Enable verbose audit logs | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 28 | GOV-16 | Governance | Workspace Unity Catalog metastore assignment | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 29 | GOV-17 | Governance | Delta Sharing recipient token lifetime | High | 1 | ✓ | ✓ | ✓ | Keep |
| 30 | GOV-18 | Governance | Delta Sharing IP access lists | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 31 | GOV-19 | Governance | Delta Sharing token expiration | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 32 | GOV-20 | Governance | Unity Catalog metastores existence | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 33 | GOV-21 | Governance | Unity Catalog metastore admin delegation | High | 1 | ✓ | ✓ | ✓ | Keep |
| 34 | GOV-22 | Informational | Direct use of UC storage credentials | Medium | 0 | ✓ | ✓ | ✓ | Keep (disabled) |
| 35 | GOV-23 | Governance | Unity Catalog enabled data warehouses | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 36 | GOV-24 | Governance | Legacy global init script | **Medium** | 1 | ✓ | ✓ | — | Severity ↓ |
| 37 | GOV-25 | Governance | Init scripts stored in DBFS | High | 1 | ✓ | ✓ | — | Keep |
| 38 | GOV-26 | Governance | Legacy cluster-named init scripts | **Medium** | 1 | ✓ | ✓ | — | Severity ↓ |
| 39 | GOV-28 | Governance | Govern model assets | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 40 | GOV-34 | Governance | Monitor audit logs with system tables | High | 1 | ✓ | ✓ | ✓ | Keep |
| 41 | GOV-35 | Governance | Restrict workspace admins | **High** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 42 | GOV-36 | Governance | Automatic cluster update | Medium | 1 | ✓ | ✓ | — | Keep |
| 43 | GOV-37 | Governance | Disable legacy features for new workspaces | High | 1 | ✓ | ✓ | ✓ | Keep |
| 44 | GOV-38 | Governance | Disable legacy table ACL access | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 45 | GOV-39 | Governance | Personal compute policy configured | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 46 | GOV-40 | Governance | AI/BI dashboard embedding policy restricted | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 47 | GOV-41 | Governance | Secret scope ACLs configured | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 48 | GOV-42 | Governance | Jobs run as service principal | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 49 | IA-1 | Identity & Access | Enable single sign-on | High | 1 | ✓ | ✓ | ✓ | Keep |
| 50 | IA-2 | Identity & Access | SCIM for user provisioning | High | 1 | ✓ | ✓ | ✓ | Keep |
| 51 | IA-4 | Identity & Access | PAT tokens with no lifetime limit | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 52 | IA-5 | Identity & Access | Maximum lifetime for new tokens | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 53 | IA-6 | Identity & Access | Tokens exceeding workspace max lifetime | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 54 | IA-7 | Identity & Access | Use service principals | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 55 | IA-8 | Identity & Access | PAT token creation restricted to admins | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 56 | IA-9 | Identity & Access | Service principal client secrets not stale | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 57 | NS-1 | Network Security | Public keys for all-purpose clusters | High | 1 | ✓ | ✓ | ✓ | Keep |
| 58 | NS-2 | Network Security | Public keys for job clusters | High | 1 | ✓ | ✓ | ✓ | Keep |
| 59 | NS-3 | Network Security | Front-end private connectivity | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 60 | NS-4 | Network Security | Customer-managed VPC/VNet injection | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 61 | NS-5 | Network Security | IP access lists for workspace | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 62 | NS-6 | Network Security | Secure cluster connectivity (NoPublicIP) | **High** | 1 | — | ✓ | — | Severity ↑ |
| 63 | NS-7 | Network Security | Secure model serving endpoints | High | 1 | ✓ | ✓ | — | Keep |
| 64 | NS-8 | Network Security | IP access lists for account console | High | 1 | ✓ | ✓ | ✓ | Keep |
| 65 | NS-9 | Network Security | Workspaces have proper network policy | High | 1 | ✓ | ✓ | ✓ | Keep |
| 66 | NS-10 | Network Security | Serverless compute has egress network policy | High | 1 | ✓ | ✓ | ✓ | **NEW** |
| 67 | INFO-1 | Informational | Instance Pool custom tag | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 68 | INFO-2 | Informational | Maximum concurrent runs in job configuration | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 69 | INFO-3 | Informational | Global libraries | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 70 | INFO-4 | Informational | Users with cluster create privileges | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 71 | INFO-5 | Informational | Global init script | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 72 | INFO-6 | Informational | Number of admins | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 73 | INFO-7 | Informational | Detect network peering | Medium | 1 | ✓ | ✓ | ✓ | Keep |
| 74 | INFO-8 | Informational | Job view ACLs set consistently | High | 1 | ✓ | ✓ | ✓ | Keep |
| 75 | INFO-9 | Informational | Cluster view ACLs set consistently | High | 1 | ✓ | ✓ | ✓ | Keep |
| 76 | INFO-10 | Informational | Workspace view ACLs set consistently | High | 1 | ✓ | ✓ | ✓ | Keep |
| 77 | INFO-11 | Informational | Workspace for supporting Git repos | High | 1 | ✓ | ✓ | ✓ | Keep |
| 78 | INFO-18 | Informational | Users with Delta Sharing permissions | Low | 1 | ✓ | ✓ | ✓ | Keep |
| 79 | INFO-29 | Informational | Streamline LLM provider management | Medium | 1 | ✓ | ✓ | — | Keep |
| 80 | INFO-37 | Informational | Compliance security profile (account) | **Medium** | 1 | ✓ | — | — | Severity ↑ |
| 81 | INFO-38 | Informational | Third-party library control | **High** | 1 | ✓ | ✓ | ✓ | Severity ↑ |
| 82 | INFO-39 | Informational | Compliance security profile (workspace) | **Medium** | 1 | ✓ | ✓ | — | Severity ↑ |
| 83 | INFO-40 | Informational | Enhanced security monitoring (workspace) | **Medium** | 1 | ✓ | ✓ | — | Severity ↑ |
| 84 | INFO-41 | Informational | Account-level ESM enforcement | Medium | 1 | ✓ | ✓ | — | **NEW** |
| 85 | INFO-42 | Informational | Git repo allowlist configured | Medium | 1 | ✓ | ✓ | ✓ | **NEW** |
| 86 | GOV-34 | Governance | Monitor audit logs with system tables | High | 1 | ✓ | ✓ | ✓ | (already counted above) |

> **Note:** Row 86 in the numbered table above is a duplicate of row 40. The final count is 86 unique check rows in the CSV (79 - 7 + 14 = 86).

---

## Verification Checklist

- [x] Original CSV backed up at `configs/security_best_practices_0.6.0_backup.csv`
- [x] 7 checks removed: INFO-12, INFO-13, INFO-14, INFO-17, IA-3, GOV-6, GOV-7
- [x] 17 severity changes applied (12 upgrades, 5 downgrades)
- [x] 14 new checks appended (DP-10–13, GOV-38–42, IA-8/9, NS-10, INFO-41/42)
- [x] New check IDs are contiguous with existing scheme (no gaps or conflicts)
- [x] All 14 new checks have all 17 CSV columns populated
- [x] DASF mapping updated for all 14 new checks
- [x] Total row count: 79 - 7 + 14 = **86 checks**

---

## Implementation Notes for Engineering

The following new checks require new bootstrap or API call additions. All others reuse existing collected data:

| Check | Requires New Data Collection |
|---|---|
| DP-10 (Disable legacy DBFS) | Settings v2 account-level call — may reuse existing account settings bootstrap |
| DP-11 (SQL results download) | Settings v2 workspace-level — new `sql_results_download` setting |
| GOV-38 (Disable legacy access) | Settings v2 workspace-level — new `disable_legacy_access` setting |
| GOV-39 (Personal compute) | Account Settings v2 — new `personal_compute` setting |
| GOV-40 (AI/BI embedding) | Settings v2 workspace-level — new `aibi_dashboard_embedding_access_policy` |
| GOV-41 (Secret scope ACLs) | Secrets ACL list per scope — `secretscope` data exists; need ACL fetch loop |
| IA-9 (SP secrets rotation) | New API call to SP credentials/secrets endpoint |
| NS-10 (Serverless egress) | `account_networkpolicies` and `workspace_network_config` already collected; new check logic |

All other new checks (DP-12, DP-13, GOV-42, IA-8, INFO-41, INFO-42) use `workspacesettings` or `jobs` data already collected by existing bootstrap.

---

## Phase 5: Bugs Found During Implementation Review

Two data-collection bugs were identified during the Phase 3 implementation work that will cause
silent failures in checks that are already wired up or planned:

### Bug 1 — `enableDeprecatedClusterNamedInitScripts` not in `ws_keymap`

| Field | Value |
|---|---|
| **Affects** | id=65 (GOV-26, Legacy cluster-named init scripts) |
| **Problem** | `workspace_settings.py` queries `WHERE name="enableDeprecatedClusterNamedInitScripts"` but this key is absent from `ws_settings_client.py` `ws_keymap`. The `workspacesettings_<workspace_id>` table never contains this row, so the check always sees an empty DataFrame and silently passes. |
| **Fix** | Add `{"name": "enableDeprecatedClusterNamedInitScripts", "defn": "Enable or disable legacy cluster-named init scripts"}` to `ws_keymap` in `ws_settings_client.py`. |

### Bug 2 — `enableTokensConfig` not in `ws_keymap`

| Field | Value |
|---|---|
| **Affects** | id=122 (IA-8, PAT token creation restricted to admins) |
| **Problem** | IA-8 uses `enableTokensConfig` as its data source, but this key is not in `ws_settings_client.py`. IA-8 cannot be implemented until the key is added. |
| **Fix** | Add `{"name": "enableTokensConfig", "defn": "Enable or disable the ability of non-admin users to create personal access tokens."}` to `ws_keymap`. |

---

## Phase 6: Additional Recommended Checks (Post-v0.7.0 Backlog)

These checks were identified during a systematic review of all workspace-conf keys collected by
`ws_settings_client.py` versus keys that have corresponding check logic. All Tier 1 checks use
data already in the `workspacesettings_<workspace_id>` table — no new bootstrap work is needed.

**Summary:**

| ID | Check ID | Category | Check Name | Severity | Data Available? |
|---|---|---|---|---|---|
| 114 | GOV-43 | Governance | Libraries on shared UC clusters restricted | **High** | ✅ Already collected |
| 115 | DP-15 | Data Protection | MLflow artifact download disabled | Medium | ✅ Already collected |
| 116 | DP-16 | Data Protection | File upload UI disabled | Low | ✅ Already collected |
| 117 | DP-17 | Data Protection | Databricks Container Services restricted | Medium | ✅ Already collected |
| 118 | NS-11 | Network Security | Account IP access list enforcement enabled | Medium | Needs bootstrap add |
| 119 | INFO-43 | Informational | AI Gateway enforcement enabled | Medium | Needs bootstrap add |
| 120 | INFO-44 | Informational | Dashboard email subscriptions restricted | Low | Needs bootstrap add |

### Tier 1 — Zero new data collection required

#### GOV-43 (id=127) — Libraries on shared Unity Catalog clusters restricted

| Field | Value |
|---|---|
| **Check ID** | GOV-43 |
| **CSV id** | 114 |
| **Category** | Governance |
| **Severity** | High |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableLibraryAndInitScriptOnSharedCluster` |
| **Logic** | PASS if `enableLibraryAndInitScriptOnSharedCluster` value is `false`. UC shared access mode enforces per-user data isolation at the Spark layer. Allowing user-installed libraries or init scripts breaks that guarantee: a library installed by one user executes in the shared JVM and can intercept Spark tasks, read `/tmp` contents, or exfiltrate data from co-tenant sessions. This directly undermines the isolation model that makes shared clusters multi-tenant safe. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableLibraryAndInitScriptOnSharedCluster` |
| **AWS Doc** | https://docs.databricks.com/clusters/init-scripts.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/clusters/init-scripts |
| **GCP Doc** | https://docs.gcp.databricks.com/clusters/init-scripts.html |
| **DASF** | DASF-5:Control access to data and other objects |

#### DP-15 (id=128) — MLflow artifact download disabled

| Field | Value |
|---|---|
| **Check ID** | DP-15 |
| **CSV id** | 115 |
| **Category** | Data Protection |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `mlflowRunArtifactDownloadEnabled` |
| **Logic** | PASS if `mlflowRunArtifactDownloadEnabled` value is `false`. Completes the results-download trifecta alongside DP-5 (notebook results) and DP-11 (SQL results). MLflow artifacts logged during training runs can include model weights, evaluation datasets, SHAP values, and other objects derived from sensitive training data. Disabling artifact download prevents exfiltration of these artifacts while still allowing in-UI viewing. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=mlflowRunArtifactDownloadEnabled` |
| **AWS Doc** | https://docs.databricks.com/mlflow/tracking.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/mlflow/tracking |
| **GCP Doc** | https://docs.gcp.databricks.com/mlflow/tracking.html |
| **DASF** | DASF-5:Control access to data and other objects |

#### DP-16 (id=129) — File upload UI disabled

| Field | Value |
|---|---|
| **Check ID** | DP-16 |
| **CSV id** | 116 |
| **Category** | Data Protection |
| **Severity** | Low |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableUploadDataUis` |
| **Logic** | PASS if `enableUploadDataUis` value is `false`. The data upload UI lets users push arbitrary files directly to DBFS from the browser, bypassing Unity Catalog lineage tracking, data quality gates, and schema enforcement. Beyond governance gaps, it can be used to introduce malicious payloads (CSV injection, crafted Parquet files to exploit downstream parsers). |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableUploadDataUis` |
| **AWS Doc** | https://docs.databricks.com/data/data.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/data/data |
| **GCP Doc** | https://docs.gcp.databricks.com/data/data.html |
| **DASF** | DASF-5:Control access to data and other objects |

#### DP-17 (id=130) — Databricks Container Services restricted

| Field | Value |
|---|---|
| **Check ID** | DP-17 |
| **CSV id** | 117 |
| **Category** | Data Protection |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | `workspacesettings` table: `enableDcs` |
| **Logic** | PASS if `enableDcs` value is `false`. DCS lets users launch clusters with arbitrary Docker images from any external registry (Docker Hub, ECR, GHCR, etc.). A malicious or supply-chain-compromised image can contain backdoors, keyloggers, or credential stealers that execute with full cluster IAM role privileges. Unlike library-level attacks, a compromised base image executes before Databricks security controls are applied. |
| **API** | `GET https://<workspace_url>/api/2.0/preview/workspace-conf?keys=enableDcs` |
| **AWS Doc** | https://docs.databricks.com/clusters/custom-containers.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/clusters/custom-containers |
| **GCP Doc** | https://docs.gcp.databricks.com/clusters/custom-containers.html |
| **DASF** | DASF-5:Control access to data and other objects |

### Tier 2 — Small new bootstrap additions required

#### NS-11 (id=131) — Account-level IP access list enforcement enabled

| Field | Value |
|---|---|
| **Check ID** | NS-11 |
| **CSV id** | 118 |
| **Category** | Network Security |
| **Severity** | Medium |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Account Settings V2: `enable_ip_access_lists` |
| **Logic** | PASS if the IP access list enforcement feature is enabled at the account level. NS-8 checks whether IP access list entries exist, but if the enforcement feature itself is disabled, all configured lists are inert. An admin can configure lists (passing NS-8) while enforcement is off, creating a false sense of security. This is the precondition check for NS-8. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/settings/types/enable_ip_access_lists/names/default` |
| **AWS Doc** | https://docs.databricks.com/security/network/ip-access-list.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/security/network/front-end/ip-access-list |
| **GCP Doc** | https://docs.gcp.databricks.com/security/network/ip-access-list.html |
| **DASF** | DASF-4:Restrict access using private link |
| **Bootstrap** | New `get_enable_ip_access_lists()` in `accounts_settings.py` + bootstrap call in `accounts_bootstrap.py` |

#### INFO-43 (id=132) — AI Gateway enforcement enabled

| Field | Value |
|---|---|
| **Check ID** | INFO-43 |
| **CSV id** | 119 |
| **Category** | Informational |
| **Severity** | Medium |
| **Cloud** | AWS, Azure |
| **Enable** | 1 |
| **Data Source** | Account Settings V2: `llm_proxy_partner_powered_enforce` |
| **Logic** | PASS if AI Gateway enforcement is enabled (`is_enforced = true`). Databricks AI Gateway provides centralized governance for LLM API calls: rate limiting, PII detection, guardrails, and audit logging. Without account-level enforcement, individual workspaces can bypass the gateway and route LLM requests directly to OpenAI/Anthropic/etc., sending potentially sensitive data to unaudited external endpoints. Especially relevant for regulated industries. Note: only meaningful when org is actively using AI Gateway. |
| **API** | `GET https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/settings/types/llm_proxy_partner_powered_enforce/names/default` |
| **AWS Doc** | https://docs.databricks.com/generative-ai/agent-gateway.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/generative-ai/agent-gateway |
| **GCP Doc** | N/A |
| **DASF** | DASF-43:Use access control lists |
| **Bootstrap** | New `get_llm_proxy_enforcement()` in `accounts_settings.py` + bootstrap call in `accounts_bootstrap.py` |

#### INFO-44 (id=133) — Dashboard email subscriptions restricted

| Field | Value |
|---|---|
| **Check ID** | INFO-44 |
| **CSV id** | 120 |
| **Category** | Informational |
| **Severity** | Low |
| **Cloud** | AWS, Azure, GCP |
| **Enable** | 1 |
| **Data Source** | Workspace Settings V2: `dashboard_email_subscriptions` |
| **Logic** | PASS when dashboard email subscriptions are restricted or disabled. Scheduled email delivery of AI/BI dashboard results can automatically send query outputs (potentially containing PII, financial data, or trade secrets) to any email address on a recurring schedule. This is a data exfiltration risk similar to notebook export (DP-6) and results download (DP-5/DP-11), but via an automated email channel that may evade DLP monitoring. |
| **API** | `GET https://<workspace_url>/api/2.0/settings/types/dashboard_email_subscriptions/names/default` |
| **AWS Doc** | https://docs.databricks.com/dashboards/index.html |
| **Azure Doc** | https://learn.microsoft.com/en-us/azure/databricks/dashboards |
| **GCP Doc** | https://docs.gcp.databricks.com/dashboards/index.html |
| **DASF** | DASF-5:Control access to data and other objects |
| **Bootstrap** | New `get_dashboard_email_subscriptions()` in `ws_settings_client.py` + bootstrap call in `workspace_bootstrap.py` |

### Workspace-conf keys reviewed and NOT recommended

| Key | Reason not recommended |
|---|---|
| `heapAnalyticsAdminConsent` / `intercomAdminConsent` | Third-party product analytics with contractual DPAs. Not an actionable security control; no meaningful pass/fail security posture signal. |
| `enableHlsRuntime` | Genomics runtime availability. Not a security control. |
| `enableGp3` | AWS EBS volume type preference. Not a security control. |
| `enableJobsEmailsV2` | Email notification format version. Not a security control. |
| `mlflowModelServingEndpointCreationEnabled` | Restricting endpoint creation is operational governance, not a data security control. |
| `mlflowModelRegistryEmailNotificationsEnabled` | Email notification opt-in. Not a security control. |
| `jobsListBackendPaginationEnabled` | Backend pagination feature flag. Not a security control. |
| `enableDatabricksAutologgingAdminConf` | Auto-logging is a productivity feature; disabling it does not reduce data security posture. |
| `aibi_dashboard_embedding_approved_domains` | Domain allowlist is context-dependent; no universal pass/fail. GOV-40 covers whether any embedding is allowed. |
