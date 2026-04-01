# SAT Validation Report - AWS

**Generated:** 2026-04-01 10:01:31  
**SAT Run ID:** 17  
**Cloud:** aws  
**Total checks validated:** 63

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| AGREE | 47 | API ground truth matches SAT result |
| DISAGREE | 4 | API and SAT disagree on pass/fail |
| SAT_MISSING | 4 | Check not found in SAT output for this run |
| API_ERROR | 8 | Could not call the API to verify |
| **Total** | **63** | |

## Discrepancies

These checks have different results between the API ground truth and what SAT reported. Each entry includes the raw API evidence and SAT's stored result.

### GOV-3: Log delivery configurations

- **Category:** Governance
- **Severity:** High
- **API says:** score=1 (FAIL)
- **API details:** `{'error': '403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/log-delivery'}`
- **SAT says:** score=0 (PASS)
- **SAT details:** `{"audit_logs":"[[\"audit log config\",\"17528064-2abe-11ed-be26-063fa5ec6fe1\"]]"}`

**Possible issue:** 
SAT reports a pass but the API shows a violation. This could indicate the check logic is not evaluating the correct field, missing a condition, or the API response schema has changed.

### IA-9: Service principal client secrets not stale

- **Category:** Identity & Access
- **Severity:** Medium
- **API says:** score=0 (PASS)
- **API details:** `{'note': 'Could not list service principals'}`
- **SAT says:** score=1 (FAIL)
- **SAT details:** `{"19e398044a5a3123714634f5b8d5085de92ad4e751b77c1c44e4e66833630643":"[\"app-tjh6ct questionnaire-analysis\",\"b720b0b1-7b52-4271-ae5f-826a414f33d7\",\"539\"]","f8629833a2c644dfe3a107c93193e3adbd29e04ba8b12888a6e39e765bbf844a":"[\"jira-notification-uploader\",\"44d031cd-a98b-4534-85c8-724be5362340\",\"615\"]","2b85b39ea0f2941c46561ffdabcd23c44532567366efb3e62244f80750cfe77e":"[\"sqrc\",\"1437c210-cecd-4b20-a653-8e525fae4746\",\"649\"]","4e9960d538af59902fd9b23834d53124bd2472b13aaa4928511deefda26fa5fd":"[\"test\",\"b1f530c7-6bd3-4b41-a8a5-c49f310b0330\",\"645\"]","db173638c6802eb1cd1be684afc84c911799f26c1b3f116e2d3473e081cc5f67":"[\"app-tjh6ct databricks-dspm\",\"66cdd48e-73bf-4d6f-bc56-b016d0f61dac\",\"377\"]","2748f0ef5e445677970255e2c0ef22e35baf2ce3f26273853e258dff1f287fc3":"[\"test2\",\"262adfff-78df-44e1-8426-a54d243c4ee1\",\"670\"]","83adc98ff35f0c5a20c2c8c406a51a9964e7071b77eb4b1d7336d67c9d34ecd7":"[\"xx\",\"48302c40-48d0-41dc-8ebd-478d145c4a4f\",\"624\"]","8c60d7ef7d6a15c37eba6aec7c595833962bb839b5211ff770048163af41c73c":"[\"okta-scim\",\"0f5eaf66-dd08-4c4c-95bf-c599e8b845cd\",\"698\"]","7b5f5d6b01dbd4c589f19f4633b764d7cec3288c2d6bc5ec00bf84fe6f48be5a":"[\"dw-product-comparison-sp\",\"293991a3-1e5f-4bfc-9b4f-7bc40ba0b864\",\"431\"]","2fe3e9e9d0f452412b587da429deed3942ab7ac2be385a3a96241608669d9cf4":"[\"app-65kx87 egresstest\",\"9c3fe65b-dc8b-4fe1-b911-c7e502182f36\",\"481\"]"}`

**Possible issue:** 
SAT reports a violation but the API shows the configuration is correct. This could indicate stale intermediate data, a timing issue between data collection and analysis, or a bug in the SAT check logic.

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
- **Error:** `HTTPError: 403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/workspaces`

### GOV-2: PAT tokens are about to expire
- **Error:** `HTTPError: 404 Client Error: Not Found for url: https://sfe-plain.cloud.databricks.com/api/2.0/token/list`

### IA-4: PAT tokens with no lifetime (expiration) limit
- **Error:** `HTTPError: 404 Client Error: Not Found for url: https://sfe-plain.cloud.databricks.com/api/2.0/token/list`

### IA-6:  Tokens with a lifetime (expiration) that exceeds the workspace maximum lifetime for new tokens
- **Error:** `HTTPError: 404 Client Error: Not Found for url: https://sfe-plain.cloud.databricks.com/api/2.0/token/list`

### NS-13: Account console IP access list enforcement enabled
- **Error:** `HTTPError: 403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/ip-access-lists`

### NS-3: Front-end private connectivity
- **Error:** `HTTPError: 403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/workspaces`

### NS-4: Workspace uses a customer-managed VPC (AWS, GCP) or enables VNet injection (Azure)
- **Error:** `HTTPError: 403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/workspaces`

### NS-8: IP access lists for account console access
- **Error:** `HTTPError: 403 Client Error: Forbidden for url: https://accounts.cloud.databricks.com/api/2.0/accounts/dcdbb945-e659-4e8c-b108-db6b3ac3d0eb/ip-access-lists`

## Missing from SAT Output

These checks have validators but no corresponding result was found in the SAT `security_checks` table for run_id=17.

- **DP-2**: Cluster instance disk encryption
- **GOV-5**: Deprecated versions of Databricks runtimes
- **IA-8**: PAT token creation restricted to admins
- **INFO-6**: Number of admins

## Full Results

| Check ID | Name | Category | Severity | API | SAT | Verdict |
|----------|------|----------|----------|-----|-----|---------|
| DP-1 | Secrets management | Data Protection | Low | PASS | PASS | AGREE |
| DP-10 | Disable legacy DBFS root and mounts | Data Protection | Medium | FAIL | FAIL | AGREE |
| DP-11 | SQL warehouse results download disabled | Data Protection | Medium | FAIL | FAIL | AGREE |
| DP-13 | DBFS file browser disabled | Data Protection | Medium | PASS | PASS | AGREE |
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
| GOV-2 | PAT tokens are about to expire | Governance | High | ERR | PASS | API_ERROR |
| GOV-20 | Existence of Unity Catalog metastores | Governance | Low | PASS | PASS | AGREE |
| GOV-21 | Delegation of the Unity Catalog metastore admin to a group | Governance | High | PASS | PASS | AGREE |
| GOV-25 | Init scripts stored in DBFS | Governance | High | PASS | PASS | AGREE |
| GOV-28 | Govern model assets | Governance | Medium | FAIL | FAIL | AGREE |
| GOV-3 | Log delivery configurations | Governance | High | FAIL | PASS | DISAGREE |
| GOV-34 | Monitor audit logs with system tables (or see GOV-3) | Governance | High | PASS | PASS | AGREE |
| GOV-35 | Restrict workspace admins | Governance | Medium | FAIL | FAIL | AGREE |
| GOV-36 | Automatic cluster update | Governance | Medium | PASS | PASS | AGREE |
| GOV-37 | Disable legacy features for new workspaces | Governance | High | FAIL | FAIL | AGREE |
| GOV-4 | Long-running clusters | Governance | Medium | PASS | PASS | AGREE |
| GOV-42 | Jobs run as service principal | Governance | Medium | PASS | PASS | AGREE |
| GOV-45 | Jobs not granting CAN_MANAGE to non-admin principals | Governance | High | FAIL | FAIL | AGREE |
| GOV-5 | Deprecated versions of Databricks runtimes | Governance | High | PASS | N/A | SAT_MISSING |
| IA-4 | PAT tokens with no lifetime (expiration) limit | Identity & Access | Medium | ERR | PASS | API_ERROR |
| IA-5 | Maximum lifetime of new tokens to something other than unlimited | Identity & Access | Medium | PASS | PASS | AGREE |
| IA-6 |  Tokens with a lifetime (expiration) that exceeds the workspace maximum lifetime for new tokens | Identity & Access | Medium | ERR | PASS | API_ERROR |
| IA-8 | PAT token creation restricted to admins | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| IA-9 | Service principal client secrets not stale | Identity & Access | Medium | PASS | FAIL | DISAGREE |
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
| NS-11 | Workspace IP access list enforcement enabled | Network Security | High | PASS | PASS | AGREE |
| NS-12 | Context-Based Ingress (CBI) policy configured | Network Security | High | FAIL | FAIL | AGREE |
| NS-13 | Account console IP access list enforcement enabled | Network Security | High | ERR | PASS | API_ERROR |
| NS-3 | Front-end private connectivity | Network Security | Medium | ERR | FAIL | API_ERROR |
| NS-4 | Workspace uses a customer-managed VPC (AWS, GCP) or enables VNet injection (Azure) | Network Security | Medium | ERR | PASS | API_ERROR |
| NS-5 | IP access lists for workspace access | Network Security | Medium | PASS | PASS | AGREE |
| NS-7 | Secure model serving endpoints | Network Security | High | PASS | PASS | AGREE |
| NS-8 | IP access lists for account console access | Network Security | High | ERR | PASS | API_ERROR |
| NS-9 | Workspaces have proper network policy configuration | Network Security | High | FAIL | PASS | DISAGREE |
