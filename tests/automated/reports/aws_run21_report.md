# SAT Validation Report - AWS

**Generated:** 2026-04-01 09:57:40  
**SAT Run ID:** 21  
**Cloud:** aws  
**Total checks validated:** 63

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| AGREE | 0 | API ground truth matches SAT result |
| DISAGREE | 0 | API and SAT disagree on pass/fail |
| SAT_MISSING | 55 | Check not found in SAT output for this run |
| API_ERROR | 8 | Could not call the API to verify |
| **Total** | **63** | |

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

These checks have validators but no corresponding result was found in the SAT `security_checks` table for run_id=21.

- **DP-1**: Secrets management
- **DP-10**: Disable legacy DBFS root and mounts
- **DP-11**: SQL warehouse results download disabled
- **DP-13**: DBFS file browser disabled
- **DP-14**: Store and retrieve embeddings securely
- **DP-2**: Cluster instance disk encryption
- **DP-5**: Downloading results is disabled
- **DP-6**: Notebook export
- **DP-7**: Notebook table clipboard features
- **DP-8**: Enable storing interactive notebook results only in the customer account
- **DP-9**: FileStore endpoint for HTTPS file serving
- **GOV-10**: Managed tables in DBFS root
- **GOV-11**: DBFS mounts
- **GOV-12**: Unity Catalog enabled clusters
- **GOV-14**: Enforce AWS Instance Metadata Service v2
- **GOV-15**: Enable verbose audit logs (on Azure, diagnostic logs)
- **GOV-16**: Workspace Unity Catalog metastore assignment
- **GOV-17**: Limit the lifetime (expiration) of metastore Delta Sharing recipient token
- **GOV-18**: Delta Sharing IP access lists
- **GOV-19**: Delta Sharing token expiration
- **GOV-20**: Existence of Unity Catalog metastores
- **GOV-21**: Delegation of the Unity Catalog metastore admin to a group
- **GOV-25**: Init scripts stored in DBFS
- **GOV-28**: Govern model assets
- **GOV-3**: Log delivery configurations
- **GOV-34**: Monitor audit logs with system tables (or see GOV-3)
- **GOV-35**: Restrict workspace admins
- **GOV-36**: Automatic cluster update
- **GOV-37**: Disable legacy features for new workspaces
- **GOV-4**: Long-running clusters
- **GOV-42**: Jobs run as service principal
- **GOV-45**: Jobs not granting CAN_MANAGE to non-admin principals
- **GOV-5**: Deprecated versions of Databricks runtimes
- **IA-5**: Maximum lifetime of new tokens to something other than unlimited
- **IA-8**: PAT token creation restricted to admins
- **IA-9**: Service principal client secrets not stale
- **INFO-10**: Workspace View ACLs are set consistently
- **INFO-11**: Workspace for supporting Git repos
- **INFO-18**: Users with Delta Sharing permissions to create a recipient or create a share
- **INFO-29**: Streamline the usage and management of various large language model(LLM) providers
- **INFO-3**: Global libraries
- **INFO-37**: Compliance security profile for new workspaces
- **INFO-38**: Third-party library control
- **INFO-39**: Compliance security profile for the workspace
- **INFO-40**: Enhanced security monitoring for the workspace
- **INFO-42**: Git repository allowlist configured
- **INFO-5**: Global init script
- **INFO-6**: Number of admins
- **INFO-8**: Job view ACLs are set consistently
- **INFO-9**: Cluster view ACLs are set consistently
- **NS-11**: Workspace IP access list enforcement enabled
- **NS-12**: Context-Based Ingress (CBI) policy configured
- **NS-5**: IP access lists for workspace access
- **NS-7**: Secure model serving endpoints
- **NS-9**: Workspaces have proper network policy configuration

## Full Results

| Check ID | Name | Category | Severity | API | SAT | Verdict |
|----------|------|----------|----------|-----|-----|---------|
| DP-1 | Secrets management | Data Protection | Low | PASS | N/A | SAT_MISSING |
| DP-10 | Disable legacy DBFS root and mounts | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| DP-11 | SQL warehouse results download disabled | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| DP-13 | DBFS file browser disabled | Data Protection | Medium | PASS | N/A | SAT_MISSING |
| DP-14 | Store and retrieve embeddings securely | Data Protection | Low | FAIL | N/A | SAT_MISSING |
| DP-2 | Cluster instance disk encryption | Data Protection | Low | FAIL | N/A | SAT_MISSING |
| DP-3 | Customer-managed keys for managed services and workspace storage | Data Protection | Low | ERR | N/A | API_ERROR |
| DP-5 | Downloading results is disabled | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| DP-6 | Notebook export | Data Protection | Low | FAIL | N/A | SAT_MISSING |
| DP-7 | Notebook table clipboard features | Data Protection | Low | FAIL | N/A | SAT_MISSING |
| DP-8 | Enable storing interactive notebook results only in the customer account | Data Protection | Medium | PASS | N/A | SAT_MISSING |
| DP-9 | FileStore endpoint for HTTPS file serving | Data Protection | Medium | FAIL | N/A | SAT_MISSING |
| GOV-10 | Managed tables in DBFS root | Governance | Low | FAIL | N/A | SAT_MISSING |
| GOV-11 | DBFS mounts | Governance | Low | PASS | N/A | SAT_MISSING |
| GOV-12 | Unity Catalog enabled clusters | Governance | High | PASS | N/A | SAT_MISSING |
| GOV-14 | Enforce AWS Instance Metadata Service v2 | Governance | Low | PASS | N/A | SAT_MISSING |
| GOV-15 | Enable verbose audit logs (on Azure, diagnostic logs) | Governance | Medium | FAIL | N/A | SAT_MISSING |
| GOV-16 | Workspace Unity Catalog metastore assignment | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-17 | Limit the lifetime (expiration) of metastore Delta Sharing recipient token | Governance | High | FAIL | N/A | SAT_MISSING |
| GOV-18 | Delta Sharing IP access lists | Governance | Medium | FAIL | N/A | SAT_MISSING |
| GOV-19 | Delta Sharing token expiration | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-2 | PAT tokens are about to expire | Governance | High | ERR | N/A | API_ERROR |
| GOV-20 | Existence of Unity Catalog metastores | Governance | Low | PASS | N/A | SAT_MISSING |
| GOV-21 | Delegation of the Unity Catalog metastore admin to a group | Governance | High | PASS | N/A | SAT_MISSING |
| GOV-25 | Init scripts stored in DBFS | Governance | High | PASS | N/A | SAT_MISSING |
| GOV-28 | Govern model assets | Governance | Medium | FAIL | N/A | SAT_MISSING |
| GOV-3 | Log delivery configurations | Governance | High | FAIL | N/A | SAT_MISSING |
| GOV-34 | Monitor audit logs with system tables (or see GOV-3) | Governance | High | PASS | N/A | SAT_MISSING |
| GOV-35 | Restrict workspace admins | Governance | Medium | FAIL | N/A | SAT_MISSING |
| GOV-36 | Automatic cluster update | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-37 | Disable legacy features for new workspaces | Governance | High | FAIL | N/A | SAT_MISSING |
| GOV-4 | Long-running clusters | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-42 | Jobs run as service principal | Governance | Medium | PASS | N/A | SAT_MISSING |
| GOV-45 | Jobs not granting CAN_MANAGE to non-admin principals | Governance | High | FAIL | N/A | SAT_MISSING |
| GOV-5 | Deprecated versions of Databricks runtimes | Governance | High | PASS | N/A | SAT_MISSING |
| IA-4 | PAT tokens with no lifetime (expiration) limit | Identity & Access | Medium | ERR | N/A | API_ERROR |
| IA-5 | Maximum lifetime of new tokens to something other than unlimited | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| IA-6 |  Tokens with a lifetime (expiration) that exceeds the workspace maximum lifetime for new tokens | Identity & Access | Medium | ERR | N/A | API_ERROR |
| IA-8 | PAT token creation restricted to admins | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| IA-9 | Service principal client secrets not stale | Identity & Access | Medium | PASS | N/A | SAT_MISSING |
| INFO-10 | Workspace View ACLs are set consistently | Informational | High | PASS | N/A | SAT_MISSING |
| INFO-11 | Workspace for supporting Git repos | Informational | High | PASS | N/A | SAT_MISSING |
| INFO-18 | Users with Delta Sharing permissions to create a recipient or create a share | Informational | Low | PASS | N/A | SAT_MISSING |
| INFO-29 | Streamline the usage and management of various large language model(LLM) providers | Informational | Medium | PASS | N/A | SAT_MISSING |
| INFO-3 | Global libraries | Informational | Low | PASS | N/A | SAT_MISSING |
| INFO-37 | Compliance security profile for new workspaces | Informational | Low | FAIL | N/A | SAT_MISSING |
| INFO-38 | Third-party library control | Informational | Low | PASS | N/A | SAT_MISSING |
| INFO-39 | Compliance security profile for the workspace | Informational | Low | FAIL | N/A | SAT_MISSING |
| INFO-40 | Enhanced security monitoring for the workspace | Informational | Low | FAIL | N/A | SAT_MISSING |
| INFO-42 | Git repository allowlist configured | Informational | Medium | FAIL | N/A | SAT_MISSING |
| INFO-5 | Global init script | Informational | Medium | PASS | N/A | SAT_MISSING |
| INFO-6 | Number of admins | Informational | Low | FAIL | N/A | SAT_MISSING |
| INFO-8 | Job view ACLs are set consistently | Informational | High | PASS | N/A | SAT_MISSING |
| INFO-9 | Cluster view ACLs are set consistently | Informational | High | PASS | N/A | SAT_MISSING |
| NS-11 | Workspace IP access list enforcement enabled | Network Security | High | PASS | N/A | SAT_MISSING |
| NS-12 | Context-Based Ingress (CBI) policy configured | Network Security | High | FAIL | N/A | SAT_MISSING |
| NS-13 | Account console IP access list enforcement enabled | Network Security | High | ERR | N/A | API_ERROR |
| NS-3 | Front-end private connectivity | Network Security | Medium | ERR | N/A | API_ERROR |
| NS-4 | Workspace uses a customer-managed VPC (AWS, GCP) or enables VNet injection (Azure) | Network Security | Medium | ERR | N/A | API_ERROR |
| NS-5 | IP access lists for workspace access | Network Security | Medium | PASS | N/A | SAT_MISSING |
| NS-7 | Secure model serving endpoints | Network Security | High | PASS | N/A | SAT_MISSING |
| NS-8 | IP access lists for account console access | Network Security | High | ERR | N/A | API_ERROR |
| NS-9 | Workspaces have proper network policy configuration | Network Security | High | FAIL | N/A | SAT_MISSING |
