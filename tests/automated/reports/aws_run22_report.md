# SAT Validation Report - AWS

**Generated:** 2026-04-01 12:01:39  
**SAT Run ID:** 22  
**Cloud:** aws  
**Total checks validated:** 63

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| AGREE | 43 | API ground truth matches SAT result |
| DISAGREE | 3 | API and SAT disagree on pass/fail |
| SAT_MISSING | 12 | Check not found in SAT output for this run |
| API_ERROR | 5 | Could not call the API to verify |
| **Total** | **63** | |

## Discrepancies

These checks have different results between the API ground truth and what SAT reported. Each entry includes the raw API evidence and SAT's stored result.

### GOV-3: Log delivery configurations

- **Category:** Governance
- **Severity:** High
- **API says:** score=1 (FAIL)
- **API details:** `{'error': '403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: 751d9d37-e346-4c1a-aeff-7ba036550ee5]'}`
- **SAT says:** score=0 (PASS)
- **SAT details:** `{"audit_logs":"[[\"audit log config\",\"17528064-2abe-11ed-be26-063fa5ec6fe1\"]]"}`

**Possible issue:** 
SAT reports a pass but the API shows a violation. This could indicate the check logic is not evaluating the correct field, missing a condition, or the API response schema has changed.

### INFO-38: Third-party library control

- **Category:** Informational
- **Severity:** Low
- **API says:** score=0 (PASS)
- **API details:** `{'has_allowlist': True}`
- **SAT says:** score=1 (FAIL)
- **SAT details:** `{"third_party_library_control":"No artifact allowlist configured"}`

**Possible issue:** 
SAT reports a violation but the API shows the configuration is correct. This could indicate stale intermediate data, a timing issue between data collection and analysis, or a bug in the SAT check logic.

### NS-9: Workspaces have proper network policy configuration

- **Category:** Network Security
- **Severity:** High
- **API says:** score=1 (FAIL)
- **API details:** `{'reason': 'CANNOT_FETCH_POLICIES'}`
- **SAT says:** score=0 (PASS)
- **SAT details:** `{"message":"No deviations from the security best practices found for this check"}`

**Possible issue:** 
SAT reports a pass but the API shows a violation. This could indicate the check logic is not evaluating the correct field, missing a condition, or the API response schema has changed.

## API Errors

These checks could not be validated because the API call failed.

### DP-3: Customer-managed keys for managed services and workspace storage
- **Error:** `ACCOUNT_API_FORBIDDEN: 403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: cceb84b3-c6f5-4d70-abad-edd89d55fbd9]`

### NS-13: Account console IP access list enforcement enabled
- **Error:** `ACCOUNT_API_FORBIDDEN: 403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: 7cabe454-8860-4425-9bc5-45c0a6e1cf03]`

### NS-3: Front-end private connectivity
- **Error:** `ACCOUNT_API_FORBIDDEN: 403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: ad8b1e96-ab4c-4cd8-a9b4-3763c4ea3580]`

### NS-4: Workspace uses a customer-managed VPC (AWS, GCP) or enables VNet injection (Azure)
- **Error:** `ACCOUNT_API_FORBIDDEN: 403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: 0b116f38-e24e-4f0c-af43-e0709450a907]`

### NS-8: IP access lists for account console access
- **Error:** `ACCOUNT_API_FORBIDDEN: 403 Forbidden: Password login disabled for security-field-engineering@databricks.com in the account dcdbb945-e659-4e8c-b108-db6b3ac3d0eb. Please see https://docs.databricks.com/en/dev-tools/auth/index.html for other accepted authentication methods. [ReqId: 2f7cf3bd-d031-4a90-a426-ecf17c5900d6]`

## Missing from SAT Output

These checks have validators but no corresponding result was found in the SAT `security_checks` table for run_id=22.

- **DP-10**: Disable legacy DBFS root and mounts
- **DP-11**: SQL warehouse results download disabled
- **DP-13**: DBFS file browser disabled
- **DP-2**: Cluster instance disk encryption
- **GOV-42**: Jobs run as service principal
- **GOV-45**: Jobs not granting CAN_MANAGE to non-admin principals
- **GOV-5**: Deprecated versions of Databricks runtimes
- **IA-8**: PAT token creation restricted to admins
- **IA-9**: Service principal client secrets not stale
- **INFO-6**: Number of admins
- **NS-11**: Workspace IP access list enforcement enabled
- **NS-12**: Context-Based Ingress (CBI) policy configured

## Full Results

| Check ID | Name | Category | Severity | API | SAT | Verdict |
|----------|------|----------|----------|-----|-----|---------|
| DP-1 | Secrets management | Data Protection | Low | PASS | PASS | AGREE |
| DP-10 | Disable legacy DBFS root and mounts | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| DP-11 | SQL warehouse results download disabled | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| DP-13 | DBFS file browser disabled | Data Protection | Medium | PASS | N/A | SAT_MISSING |
| DP-14 | Store and retrieve embeddings securely | Data Protection | Low | FAIL | FAIL | AGREE |
| DP-2 | Cluster instance disk encryption | Data Protection | Low | FAIL | N/A | SAT_MISSING |
| DP-3 | Customer-managed keys for managed services and workspace storage | Data Protection | Low | ERR | PASS | API_ERROR |
| DP-5 | Downloading results is disabled | Data Protection | Medium | FAIL | FAIL | AGREE |
| DP-6 | Notebook export | Data Protection | Low | FAIL | FAIL | AGREE |
| DP-7 | Notebook table clipboard features | Data Protection | Low | FAIL | FAIL | AGREE |
| DP-8 | Enable storing interactive notebook results only in the customer account | Data Protection | Medium | PASS | PASS | AGREE |
| DP-9 | FileStore endpoint for HTTPS file serving | Data Protection | Medium | FAIL | FAIL | AGREE |
| GOV-10 | Managed tables in DBFS root | Governance | Low | FAIL | FAIL | AGREE |
| GOV-11 | DBFS mounts | Governance | Low | PASS | PASS | AGREE |
| GOV-12 | Unity Catalog enabled clusters | Governance | High | PASS | PASS | AGREE |
| GOV-14 | Enforce AWS Instance Metadata Service v2 | Governance | Low | PASS | PASS | AGREE |
| GOV-15 | Enable verbose audit logs (on Azure, diagnostic logs) | Governance | Medium | FAIL | FAIL | AGREE |
| GOV-16 | Workspace Unity Catalog metastore assignment | Governance | Medium | PASS | PASS | AGREE |
| GOV-17 | Limit the lifetime (expiration) of metastore Delta Sharing recipient token | Governance | High | FAIL | FAIL | AGREE |
| GOV-18 | Delta Sharing IP access lists | Governance | Medium | FAIL | FAIL | AGREE |
| GOV-19 | Delta Sharing token expiration | Governance | Medium | PASS | PASS | AGREE |
| GOV-2 | PAT tokens are about to expire | Governance | High | PASS | PASS | AGREE |
| GOV-20 | Existence of Unity Catalog metastores | Governance | Low | PASS | PASS | AGREE |
| GOV-21 | Delegation of the Unity Catalog metastore admin to a group | Governance | High | PASS | PASS | AGREE |
| GOV-25 | Init scripts stored in DBFS | Governance | High | PASS | PASS | AGREE |
| GOV-28 | Govern model assets | Governance | Medium | PASS | PASS | AGREE |
| GOV-3 | Log delivery configurations | Governance | High | FAIL | PASS | DISAGREE |
| GOV-34 | Monitor audit logs with system tables (or see GOV-3) | Governance | High | PASS | PASS | AGREE |
| GOV-35 | Restrict workspace admins | Governance | Medium | FAIL | FAIL | AGREE |
| GOV-36 | Automatic cluster update | Governance | Medium | PASS | PASS | AGREE |
| GOV-37 | Disable legacy features for new workspaces | Governance | High | FAIL | FAIL | AGREE |
| GOV-4 | Long-running clusters | Governance | Medium | PASS | PASS | AGREE |
| GOV-42 | Jobs run as service principal | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-45 | Jobs not granting CAN_MANAGE to non-admin principals | Governance | High | FAIL | N/A | SAT_MISSING |
| GOV-5 | Deprecated versions of Databricks runtimes | Governance | High | PASS | N/A | SAT_MISSING |
| IA-4 | PAT tokens with no lifetime (expiration) limit | Identity & Access | Medium | PASS | PASS | AGREE |
| IA-5 | Maximum lifetime of new tokens to something other than unlimited | Identity & Access | Medium | PASS | PASS | AGREE |
| IA-6 |  Tokens with a lifetime (expiration) that exceeds the workspace maximum lifetime for new tokens | Identity & Access | Medium | PASS | PASS | AGREE |
| IA-8 | PAT token creation restricted to admins | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| IA-9 | Service principal client secrets not stale | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| INFO-10 | Workspace View ACLs are set consistently | Informational | High | PASS | PASS | AGREE |
| INFO-11 | Workspace for supporting Git repos | Informational | High | PASS | PASS | AGREE |
| INFO-18 | Users with Delta Sharing permissions to create a recipient or create a share | Informational | Low | PASS | PASS | AGREE |
| INFO-29 | Streamline the usage and management of various large language model(LLM) providers | Informational | Medium | PASS | PASS | AGREE |
| INFO-3 | Global libraries | Informational | Low | PASS | PASS | AGREE |
| INFO-37 | Compliance security profile for new workspaces | Informational | Low | FAIL | FAIL | AGREE |
| INFO-38 | Third-party library control | Informational | Low | PASS | FAIL | DISAGREE |
| INFO-39 | Compliance security profile for the workspace | Informational | Low | FAIL | FAIL | AGREE |
| INFO-40 | Enhanced security monitoring for the workspace | Informational | Low | FAIL | FAIL | AGREE |
| INFO-42 | Git repository allowlist configured | Informational | Medium | FAIL | FAIL | AGREE |
| INFO-5 | Global init script | Informational | Medium | PASS | PASS | AGREE |
| INFO-6 | Number of admins | Informational | Low | FAIL | N/A | SAT_MISSING |
| INFO-8 | Job view ACLs are set consistently | Informational | High | PASS | PASS | AGREE |
| INFO-9 | Cluster view ACLs are set consistently | Informational | High | PASS | PASS | AGREE |
| NS-11 | Workspace IP access list enforcement enabled | Network Security | High | PASS | N/A | SAT_MISSING |
| NS-12 | Context-Based Ingress (CBI) policy configured | Network Security | High | FAIL | N/A | SAT_MISSING |
| NS-13 | Account console IP access list enforcement enabled | Network Security | High | ERR | N/A | API_ERROR |
| NS-3 | Front-end private connectivity | Network Security | Medium | ERR | FAIL | API_ERROR |
| NS-4 | Workspace uses a customer-managed VPC (AWS, GCP) or enables VNet injection (Azure) | Network Security | Medium | ERR | PASS | API_ERROR |
| NS-5 | IP access lists for workspace access | Network Security | Medium | PASS | PASS | AGREE |
| NS-7 | Secure model serving endpoints | Network Security | High | PASS | PASS | AGREE |
| NS-8 | IP access lists for account console access | Network Security | High | ERR | PASS | API_ERROR |
| NS-9 | Workspaces have proper network policy configuration | Network Security | High | FAIL | PASS | DISAGREE |
