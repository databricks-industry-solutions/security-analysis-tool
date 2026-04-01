# SAT Validation Full Analysis Report — AWS Run 23

**Generated:** 2026-04-01  
**SAT Run ID:** 23  
**Workspace:** sfe-plain (1425658296462059)  
**Cloud:** AWS  
**Framework branch:** `feature/sat_testing_framework`

---

## Executive Summary

| Category | Count | Description |
|----------|-------|-------------|
| **AGREE** | 50 | SAT and API ground truth match |
| **DISAGREE** | 4 | SAT and API give different pass/fail results |
| **API_ERROR** | 5 | Test framework can't call the API (account-level 403) |
| **SAT_MISSING** | 4 | Check has a validator but SAT didn't produce a result |
| **Total validated** | 63 | All enabled AWS checks in security_best_practices.csv |

**Accuracy on comparable checks: 50/54 = 92.6%**  
Of the 4 DISAGREE, 2 are test framework limitations (account API 403), leaving **2 genuine SAT issues** to investigate.

---

## DISAGREE: 4 Checks Need Investigation

### 1. GOV-3 (id=8): Log delivery configurations — TEST FRAMEWORK LIMITATION

| | Value |
|---|---|
| **API result** | FAIL (score=1) |
| **SAT result** | PASS (score=0) |
| **SAT details** | `{"audit_logs":"[[\"audit log config\",\"17528064-2abe-11ed-be26-063fa5ec6fe1\"]]"}` |

**Root cause:** The test framework calls `GET /api/2.0/accounts/{account_id}/log-delivery` with an account-level OAuth token. This returns HTTP 403 ("Password login disabled") because the service principal's token is not accepted from outside a Databricks notebook. The validator treats this API failure as "no log delivery found" → FAIL.

SAT runs inside a Databricks notebook where the SP token works, found an active audit log config → PASS.

**Verdict:** NOT a SAT bug. Test framework limitation — account-level APIs inaccessible externally.

**Fix:** Either grant the SP explicit account admin permissions for external access, or exclude account-level checks from external validation. No SAT code change needed.

---

### 2. NS-9 (id=111): Network policy configuration — TEST FRAMEWORK LIMITATION

| | Value |
|---|---|
| **API result** | FAIL (score=1) |
| **SAT result** | PASS (score=0) — "No deviations from security best practices" |

**Root cause:** Same as GOV-3. The validator calls `GET /api/2.0/accounts/{account_id}/network-policies` which returns 403 externally. The validator defaults to FAIL. SAT successfully retrieves network policy data inside the notebook and finds the policy is properly configured → PASS.

**Verdict:** NOT a SAT bug. Test framework limitation.

---

### 3. INFO-38 (id=104): Third-party library control — POTENTIAL SAT BUG

| | Value |
|---|---|
| **API result** | PASS (score=0) — allowlist found |
| **SAT result** | FAIL (score=1) — "No artifact allowlist configured" |
| **API evidence** | `GET /api/2.1/unity-catalog/artifact-allowlists/LIBRARY_JAR` returns `{"artifact_matchers": [{"artifact": "/Volumes/arunuc/dasf/dasf/blas-3.0.3.jar", "match_type": "PREFIX_MATCH"}]}` |

**Root cause:** The API confirms a LIBRARY_JAR allowlist entry exists, but SAT's analysis reports "No artifact allowlist configured." This means SAT's data collection (bootstrap) for the `artifacts_allowlists_library_jars_{workspace_id}` intermediate table either:
1. Failed silently during collection, leaving the table empty
2. Used a different API path or response key that didn't match
3. The allowlist was added between SAT's collection and this validation (unlikely — consistent across runs 22 and 23)

**Investigation steps for bugfix branch:**
1. Find the bootstrap call in `notebooks/Utils/workspace_bootstrap.py` that populates `artifacts_allowlists_library_jars_{workspace_id}`
2. Check which SDK client method is called and what API endpoint it uses
3. Verify the response key name matches what `bootstrap()` expects (the API returns `artifact_matchers`, SAT may expect a different key)
4. Query the intermediate table directly: `SELECT * FROM {intermediate_schema}.artifacts_allowlists_library_jars_{workspace_id}` to see if it's empty
5. Check SAT logs for errors during this bootstrap step

**Files to check:**
- `notebooks/Utils/workspace_bootstrap.py` — look for `artifacts_allowlists` bootstrap call
- `src/securityanalysistoolproject/clientpkgs/` — find the client that calls `/unity-catalog/artifact-allowlists/`
- `notebooks/Includes/workspace_analysis.py` lines 1090-1109 — the SQL query uses `UNION` of two tables

---

### 4. IA-9 (id=119): Service principal client secrets not stale — POTENTIAL SAT BUG

| | Value |
|---|---|
| **API result** | PASS (score=0) — no stale secrets found |
| **SAT result** | FAIL (score=1) — stale secrets detected |

**Root cause:** The test framework calls the account-level SP secrets API (`GET /accounts/{account_id}/scim/v2/ServicePrincipals`) with an external OAuth token. The API returned data (no 403 for SCIM endpoint), but found no stale secrets. SAT found stale secrets during its notebook run.

Possible explanations:
1. The external SP token may have limited visibility into other SPs' secrets (permission scoping)
2. The `servicePrincipals/{id}/credentials/secrets` endpoint may return different results based on the caller's role
3. SAT may collect this data via a different code path that has broader access

**Investigation steps for bugfix branch:**
1. Check `notebooks/Utils/accounts_bootstrap.py` for the `acctserviceprincipalssecrets` bootstrap
2. Find the SDK client method in `src/securityanalysistoolproject/clientpkgs/` that collects SP secrets
3. Compare the API endpoint and parameters with what the test framework uses
4. Check if the SP used for testing has `account admin` role which would grant visibility into all SP secrets

**Files to check:**
- `notebooks/Utils/accounts_bootstrap.py` — look for `acctserviceprincipalssecrets` bootstrap
- `src/securityanalysistoolproject/clientpkgs/accounts_client.py` or `scim_client.py` — SP secrets collection
- `notebooks/Includes/workspace_analysis.py` lines 1476-1497 — the analysis SQL for check 119

---

## API_ERROR: 5 Checks — Account-Level API Inaccessible

All 5 errors are HTTP 403 on account-level APIs when called from outside a Databricks notebook. The SP's OAuth token works for workspace APIs but is rejected by the accounts console.

| Check | id | Account API Endpoint |
|-------|-----|---------------------|
| DP-3 (Customer-managed keys) | 3 | `GET /accounts/{id}/workspaces` |
| NS-3 (Private link) | 35 | `GET /accounts/{id}/workspaces` |
| NS-4 (Customer VPC) | 36 | `GET /accounts/{id}/workspaces` |
| NS-8 (Account IP access lists) | 110 | `GET /accounts/{id}/ip-access-lists` |
| NS-13 (Account IP allow list) | 124 | `GET /accounts/{id}/ip-access-lists` |

**Resolution:** Grant the SP explicit "Account Admin" role in the Databricks account console for external API access, or accept these checks as externally unverifiable and rely on SAT's in-notebook execution.

---

## SAT_MISSING: 4 Checks Not in Run 23

| Check | id | Notes |
|-------|-----|-------|
| DP-2 (Disk encryption) | 2 | `aws=1, azure=1, gcp=0`. Should run on AWS. May have a bootstrap failure for `clusters_{workspace_id}` table or the table has no rows matching `enable_local_disk_encryption=False AND cluster_source IN ('UI','API')`. |
| GOV-5 (Deprecated runtimes) | 10 | Requires both `clusters_{workspace_id}` and `spark_versions_{workspace_id}` tables. If `spark_versions` bootstrap fails, this check is silently skipped. |
| INFO-6 (Admin count) | 27 | Requires `groups_{workspace_id}` table. May fail if SCIM Groups API bootstrap encounters an error. |
| IA-8 (PAT restricted to admins) | 118 | Requires `token_permissions_{workspace_id}` table. Code checks `if tbl_name in existing` before running — if bootstrap didn't create the table, the check is silently skipped. |

**Common pattern:** All 4 missing checks depend on intermediate tables that may not have been created during the bootstrap phase. The SAT analysis code silently skips checks when the intermediate table doesn't exist rather than reporting an error.

---

## AGREE: 50 Checks Verified Correct

These 50 checks produce identical pass/fail results from both the direct API call and SAT's analysis.

| Check ID | Name | Result |
|----------|------|--------|
| DP-1 | Secrets management | PASS |
| DP-5 | Downloading results disabled | FAIL |
| DP-6 | Notebook export | FAIL |
| DP-7 | Notebook table clipboard | FAIL |
| DP-8 | Notebook results in customer account | PASS |
| DP-9 | FileStore endpoint | FAIL |
| DP-10 | Disable legacy DBFS | FAIL |
| DP-11 | SQL results download | FAIL |
| DP-13 | DBFS file browser disabled | PASS |
| DP-14 | Vector search endpoints | FAIL |
| GOV-2 | PATs about to expire | PASS |
| GOV-4 | Long-running clusters | PASS |
| GOV-10 | Managed tables in DBFS | FAIL |
| GOV-11 | DBFS mounts | PASS |
| GOV-12 | Unity Catalog clusters | PASS |
| GOV-14 | Enforce IMDSv2 | PASS |
| GOV-15 | Verbose audit logs | FAIL |
| GOV-16 | UC metastore assignment | PASS |
| GOV-17 | Delta Sharing token lifetime | FAIL |
| GOV-18 | Delta Sharing IP access lists | FAIL |
| GOV-19 | Delta Sharing token expiration | PASS |
| GOV-20 | UC metastore exists | PASS |
| GOV-21 | Metastore admin delegation | PASS |
| GOV-25 | Init scripts in DBFS | PASS |
| GOV-28 | Models in Unity Catalog | PASS |
| GOV-34 | System tables access schema | PASS |
| GOV-35 | Restrict workspace admins | FAIL |
| GOV-36 | Automatic cluster update | PASS |
| GOV-37 | Disable legacy features (account) | FAIL |
| GOV-42 | Jobs run as service principal | PASS |
| GOV-45 | Jobs CAN_MANAGE restricted | FAIL |
| IA-4 | PAT tokens no lifetime limit | PASS |
| IA-5 | Max token lifetime | PASS |
| IA-6 | Tokens exceeding max lifetime | PASS |
| INFO-3 | Global libraries | PASS |
| INFO-5 | Global init scripts | PASS |
| INFO-6 | Number of admins | FAIL |
| INFO-8 | Job view ACLs | PASS |
| INFO-9 | Cluster view ACLs | PASS |
| INFO-10 | Workspace view ACLs | PASS |
| INFO-11 | Git repos support | PASS |
| INFO-18 | Delta Sharing permissions | PASS |
| INFO-29 | External model endpoints | PASS |
| INFO-37 | Account CSP | FAIL |
| INFO-39 | Compliance security profile (WS) | FAIL |
| INFO-40 | Enhanced security monitoring (WS) | FAIL |
| INFO-42 | Git repo allowlist | FAIL |
| NS-5 | Workspace IP access lists | PASS |
| NS-7 | Secure model serving | PASS |
| NS-11 | IP access list enforcement | PASS |
| NS-12 | Context-Based Ingress policy | FAIL |

---

## Action Items Summary

### For the Bugfix Branch (SAT code changes)

| Priority | Check | Issue | Key Files to Investigate |
|----------|-------|-------|--------------------------|
| P1 | INFO-38 (id=104) | Allowlist exists in API but SAT reports "not configured" | `workspace_bootstrap.py` (artifacts_allowlists bootstrap), client in `clientpkgs/`, `workspace_analysis.py:1090-1109` |
| P1 | IA-9 (id=119) | SP secrets visibility may differ by caller permissions | `accounts_bootstrap.py` (acctserviceprincipalssecrets), `workspace_analysis.py:1476-1497` |
| P2 | DP-2 (id=2) | Check not produced in run output — silent bootstrap skip | `workspace_bootstrap.py` (clusters bootstrap), `workspace_analysis.py:456-481` |
| P2 | GOV-5 (id=10) | Check not produced — needs spark_versions table | `workspace_bootstrap.py` (spark_versions bootstrap), `workspace_analysis.py:717-738` |
| P2 | INFO-6 (id=27) | Check not produced — needs groups table | `workspace_bootstrap.py` (groups bootstrap), `workspace_analysis.py:396-418` |
| P2 | IA-8 (id=118) | Check not produced — needs token_permissions table | `workspace_bootstrap.py` (token_permissions bootstrap), `workspace_analysis.py:1452-1471` |

### Not SAT bugs (test framework or environment)

| Check | Issue | Resolution |
|-------|-------|------------|
| GOV-3, NS-9 | Account API 403 from external machine | Grant SP account admin for external access |
| DP-3, NS-3, NS-4, NS-8, NS-13 | Account API 403 | Same — SP permissions |
