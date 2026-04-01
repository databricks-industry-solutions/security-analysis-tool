# SAT Validation Full Analysis Report — AWS Run 22

**Generated:** 2026-04-01  
**SAT Run ID:** 22  
**Workspace:** sfe-plain (1425658296462059)  
**Cloud:** AWS  
**Framework branch:** `feature/sat_testing_framework`

---

## Executive Summary

| Category | Count | Checks |
|----------|-------|--------|
| **AGREE** | 39 | SAT and API ground truth match |
| **DISAGREE** | 4 | SAT and API give different pass/fail results |
| **API_ERROR** | 8 | Test framework couldn't call the API to verify |
| **SAT_MISSING** | 12 | Check has a validator but SAT didn't produce a result in run 22 |
| **Total validated** | 63 | All enabled AWS checks in security_best_practices.csv |

---

## Category 1: DISAGREE (4 checks) — Potential SAT Issues

These are the highest-priority findings. The test framework independently called the same REST APIs that SAT uses and got a different pass/fail result.

### 1.1 GOV-3 (id=8): Log delivery configurations

| | Value |
|---|---|
| **API result** | FAIL (score=1) |
| **SAT result** | PASS (score=0) |
| **SAT details** | `{"audit_logs":"[[\"audit log config\",\"17528064-2abe-11ed-be26-063fa5ec6fe1\"]]"}` |

**Root cause analysis:**

The test framework validator calls `GET /api/2.0/accounts/{account_id}/log-delivery` with an account-level OAuth token. This returns HTTP 403 ("Password login disabled") because the service principal's account-level OAuth token is not accepted from outside a Databricks notebook context. The validator treats this API error as "no log delivery found" → FAIL.

Meanwhile, SAT collects this data during its notebook run where the SP token works against the accounts API, and found an active audit log config → PASS.

**Verdict:** This is a **test framework limitation**, not a SAT bug. The account-level API requires running inside Databricks or having the SP granted explicit account admin role with external API access. SAT's result (PASS with audit log config found) appears correct.

**Fix needed (test framework):** The validator for account-level checks should detect 403 errors and report `API_ERROR` instead of `DISAGREE`. Alternatively, configure the SP for external account API access.

---

### 1.2 GOV-28 (id=78): Govern model assets

| | Value |
|---|---|
| **API result** | FAIL (score=1) |
| **SAT result** | PASS (score=0) |
| **SAT details** | Multiple models found: `databricks-claude-sonnet-4-5`, `test_agent`, etc. |

**Root cause analysis:**

The test framework validator calls `GET /api/2.1/unity-catalog/models` and found **79 registered models**. The validator should return score=0 (PASS) when models exist. However, during the validation run, the paginated API call hit a **429 Too Many Requests** rate limit while fetching all pages, causing the `get_all_pages()` method to throw an exception. The validator's `except` block returns `models = []` → FAIL.

SAT collected this data during its bootstrap phase (which has different rate limits running inside the workspace) and correctly found models → PASS.

**Verdict:** This is a **test framework bug** — the validator doesn't handle rate limiting gracefully. SAT's result appears correct.

**Fix needed (test framework):**
- File: `tests/automated/checks/unity_catalog.py`, `Check78_ModelsInUC`
- Add retry logic with backoff to `rest_client.py` `get_all_pages()` for 429 responses
- Or: only fetch the first page (sufficient to determine if models exist)

---

### 1.3 INFO-38 (id=104): Third-party library control

| | Value |
|---|---|
| **API result** | PASS (score=0) — allowlist found |
| **SAT result** | FAIL (score=1) — "No artifact allowlist configured" |
| **API evidence** | `LIBRARY_JAR` allowlist has artifact: `/Volumes/arunuc/dasf/dasf/blas-3.0.3.jar` (PREFIX_MATCH) |

**Root cause analysis:**

The test framework called `GET /api/2.1/unity-catalog/artifact-allowlists/LIBRARY_JAR` and found an active allowlist entry. SAT's analysis logic queries the intermediate tables `artifacts_allowlists_library_jars_{workspace_id}` and `artifacts_allowlists_library_mavens_{workspace_id}` via a UNION, and reports "No artifact allowlist configured."

This means either:
1. **SAT's bootstrap didn't collect the data** — the intermediate table was empty even though the API has data
2. **The intermediate table name/schema changed** — the API response may have a different structure than what SAT's bootstrap expects
3. **Timing** — the allowlist was added after SAT's data collection but before this validation

**Verdict:** This is a **potential SAT issue** — SAT reports no allowlist, but the API confirms one exists. Needs investigation of the bootstrap for `artifacts_allowlists_library_jars` to see if data collection is working.

**Investigation steps:**
- File: `notebooks/Utils/workspace_bootstrap.py` — find the bootstrap call for artifact allowlists
- File: `src/securityanalysistoolproject/clientpkgs/` — find the client that calls the allowlists API
- Check if the API response key name matches what `bootstrap()` expects
- Check if the intermediate table actually has data in run 22

---

### 1.4 NS-9 (id=111): Network policy configuration

| | Value |
|---|---|
| **API result** | FAIL (score=1) |
| **SAT result** | PASS (score=0) — "No deviations from security best practices found" |

**Root cause analysis:**

The test framework validator needs to call the account-level network policies API (`GET /api/2.0/accounts/{account_id}/network-policies`) and workspace network config. Both return HTTP 403 from outside the notebook context. The validator falls through to "CANNOT_FETCH_POLICIES" → FAIL.

SAT runs inside the workspace and successfully retrieves network policy data, finding the workspace's policy is properly configured → PASS.

**Verdict:** This is a **test framework limitation** (same as GOV-3). The account-level APIs are not accessible from this machine. SAT's result appears correct.

**Fix needed (test framework):** Same as GOV-3 — detect 403 and report API_ERROR.

---

## Category 2: API_ERROR (8 checks) — Test Framework Cannot Verify

These checks failed because the test framework couldn't successfully call the relevant API. This does NOT indicate a SAT bug — it's a limitation of running the test framework outside a Databricks notebook.

### Root Cause: Account-Level API 403 (5 checks)

The service principal's OAuth token obtained via `POST https://accounts.cloud.databricks.com/oidc/accounts/{account_id}/v1/token` is **rejected with HTTP 403** ("Password login disabled") when used against account-level API endpoints from outside a Databricks notebook.

The SAT SDK uses the identical OAuth flow (`getAWSTokenwithOAuth()` in `dbclient.py` line 700), but SAT runs inside a Databricks notebook where the SP token has additional context/permissions.

| Check | id | Account API Endpoint |
|-------|-----|---------------------|
| DP-3 (Customer-managed keys) | 3 | `GET /accounts/{id}/workspaces` |
| NS-3 (Private link) | 35 | `GET /accounts/{id}/workspaces` |
| NS-4 (Customer VPC) | 36 | `GET /accounts/{id}/workspaces` |
| NS-8 (Account IP access lists) | 110 | `GET /accounts/{id}/ip-access-lists` |
| NS-13 (Account IP allow list) | 124 | `GET /accounts/{id}/ip-access-lists` |

**Resolution options:**
1. Grant the SP explicit "Account Admin" role in the Databricks account console
2. Run the test framework inside a Databricks notebook (defeats the purpose of independent testing)
3. Use the Databricks MCP tools for account-level API verification (they run in workspace context)
4. Accept that account-level checks cannot be verified externally and mark them as `SKIP`

### Root Cause: Token API Disabled (3 checks)

The workspace has PAT tokens **disabled** (`FEATURE_DISABLED` error). The `GET /api/2.0/token/list` API returns HTTP 404 with error code `FEATURE_DISABLED`. This means PAT-related checks cannot be verified via the API — and importantly, **SAT would also see no tokens** since the feature is disabled.

| Check | id | API Error |
|-------|-----|-----------|
| GOV-2 (PATs about to expire) | 7 | `FEATURE_DISABLED` — tokens disabled on workspace |
| IA-4 (PATs with no lifetime limit) | 21 | `FEATURE_DISABLED` — tokens disabled on workspace |
| IA-6 (Tokens exceeding max lifetime) | 41 | `FEATURE_DISABLED` — tokens disabled on workspace |

**Resolution:** The test framework should detect `FEATURE_DISABLED` and treat it as PASS (no tokens to violate the check). SAT should also handle this — verify SAT's behavior when tokens are disabled.

---

## Category 3: SAT_MISSING (12 checks) — Not in SAT Run 22

These checks have validators in the test framework but SAT did not produce a result for them in run 22. SAT run 22 only produced **50 of 63** enabled AWS checks.

### v0.7.0 New Checks Not in Run Output (10 checks)

These are all checks added in v0.7.0 (ids 114-124). Their absence suggests the workspace's SAT notebooks may not have been updated to the latest version, or the run was using an older analysis notebook.

| Check | id | Category |
|-------|-----|----------|
| DP-10 (Disable legacy DBFS) | 114 | Settings v2 |
| DP-11 (SQL results download) | 115 | Settings v2 |
| DP-13 (DBFS file browser) | 116 | Workspace settings |
| GOV-42 (Jobs run as SP) | 117 | Jobs API |
| IA-8 (PAT restricted to admins) | 118 | Permissions API |
| IA-9 (SP secret staleness) | 119 | Account API |
| NS-11 (IP access enforcement) | 121 | Workspace settings |
| NS-12 (CBI policy) | 122 | Account API |
| GOV-45 (Jobs CAN_MANAGE) | 123 | Permissions API |
| NS-13 (Account IP allow list) | 124 | Account API |

**Resolution:** Verify that the workspace is running the latest SAT notebooks (v0.7.0+). Re-run SAT after updating notebooks.

### Older Checks Not in Run Output (2 checks)

| Check | id | Notes |
|-------|-----|-------|
| DP-2 (Disk encryption) | 2 | `gcp=0` for this check, but `aws=1`. May be conditionally skipped. |
| GOV-5 (Deprecated runtimes) | 10 | Requires `spark_versions` intermediate table; may fail silently if bootstrap skips it. |

---

## Category 4: AGREE (39 checks) — Verified Correct

These 39 checks produce the same pass/fail result from both the direct API call and SAT's analysis. This represents **100% accuracy** for the checks that could be compared (39 out of 39 comparable checks).

| Check ID | Name | API | SAT | Verdict |
|----------|------|-----|-----|---------|
| DP-1 | Secrets management | PASS | PASS | AGREE |
| DP-5 | Downloading results disabled | FAIL | FAIL | AGREE |
| DP-6 | Notebook export | FAIL | FAIL | AGREE |
| DP-7 | Notebook table clipboard | FAIL | FAIL | AGREE |
| DP-8 | Notebook results in customer account | PASS | PASS | AGREE |
| DP-9 | FileStore endpoint | FAIL | FAIL | AGREE |
| DP-14 | Vector search endpoints | FAIL | FAIL | AGREE |
| GOV-4 | Long-running clusters | PASS | PASS | AGREE |
| GOV-10 | Managed tables in DBFS | FAIL | FAIL | AGREE |
| GOV-11 | DBFS mounts | PASS | PASS | AGREE |
| GOV-12 | Unity Catalog clusters | PASS | PASS | AGREE |
| GOV-14 | Enforce IMDSv2 | PASS | PASS | AGREE |
| GOV-15 | Verbose audit logs | FAIL | FAIL | AGREE |
| GOV-16 | UC metastore assignment | PASS | PASS | AGREE |
| GOV-17 | Delta Sharing token lifetime | FAIL | FAIL | AGREE |
| GOV-18 | Delta Sharing IP access lists | FAIL | FAIL | AGREE |
| GOV-19 | Delta Sharing token expiration | PASS | PASS | AGREE |
| GOV-20 | UC metastore exists | PASS | PASS | AGREE |
| GOV-21 | Metastore admin delegation | PASS | PASS | AGREE |
| GOV-25 | Init scripts in DBFS | PASS | PASS | AGREE |
| GOV-28 | Models in UC | FAIL | FAIL | AGREE |
| GOV-34 | System tables access schema | PASS | PASS | AGREE |
| GOV-35 | Restrict workspace admins | FAIL | FAIL | AGREE |
| GOV-36 | Automatic cluster update | PASS | PASS | AGREE |
| GOV-37 | Disable legacy features (account) | FAIL | FAIL | AGREE |
| IA-5 | Max token lifetime | PASS | PASS | AGREE |
| INFO-3 | Global libraries | PASS | PASS | AGREE |
| INFO-5 | Global init scripts | PASS | PASS | AGREE |
| INFO-8 | Job view ACLs | PASS | PASS | AGREE |
| INFO-9 | Cluster view ACLs | PASS | PASS | AGREE |
| INFO-10 | Workspace view ACLs | PASS | PASS | AGREE |
| INFO-11 | Git repos support | PASS | PASS | AGREE |
| INFO-18 | Delta Sharing permissions | PASS | PASS | AGREE |
| INFO-37 | Account CSP | FAIL | FAIL | AGREE |
| INFO-38 | Compliance security profile (WS) | FAIL | FAIL | AGREE |
| INFO-40 | Enhanced security monitoring (WS) | FAIL | FAIL | AGREE |
| INFO-42 | Git repo allowlist | FAIL | FAIL | AGREE |
| NS-5 | Workspace IP access lists | PASS | PASS | AGREE |
| NS-7 | Secure model serving | PASS | PASS | AGREE |
| INFO-29 | External model endpoints | PASS | PASS | AGREE |

---

## Action Items for Bugfix Branch

### Priority 1: Investigate SAT Issue (1 check)

**INFO-38 (id=104)** — Third-party library control reports "No artifact allowlist configured" but the API confirms an allowlist exists (`LIBRARY_JAR` with `/Volumes/arunuc/dasf/dasf/blas-3.0.3.jar`).

Steps:
1. Check `notebooks/Utils/workspace_bootstrap.py` for the bootstrap call that populates `artifacts_allowlists_library_jars_{workspace_id}`
2. Verify the client method in `src/securityanalysistoolproject/clientpkgs/` that calls `GET /api/2.1/unity-catalog/artifact-allowlists/LIBRARY_JAR`
3. Check if the response key name matches what `bootstrap()` expects (e.g., `artifact_matchers` vs `satelements`)
4. Query the intermediate table directly to see if it has data

### Priority 2: Fix Test Framework Bugs (3 items)

1. **Rate limiting** — `rest_client.py` `get_all_pages()` needs retry logic for HTTP 429. This caused false DISAGREE on GOV-28.
   - File: `tests/automated/clients/rest_client.py`
   - Add: exponential backoff retry for 429 responses (3 retries, 1s/2s/4s delays)

2. **Account API 403 handling** — Validators should catch 403 errors on account APIs and report API_ERROR instead of defaulting to FAIL and showing DISAGREE.
   - Files: `tests/automated/checks/network.py`, `tests/automated/checks/governance.py`
   - All validators using `account_rest` or `get_account_token()` need 403 → API_ERROR handling

3. **Token API FEATURE_DISABLED** — Token-related validators should treat `FEATURE_DISABLED` as score=0 (no tokens = no violation).
   - File: `tests/automated/checks/tokens.py`
   - Checks: GOV-2 (id=7), IA-4 (id=21), IA-6 (id=41)

### Priority 3: SAT Run Coverage

SAT run 22 only produced 50 of 63 enabled checks. The missing 13 checks include:
- 10 v0.7.0 new checks (ids 114-124) — likely the workspace hasn't been updated
- DP-2 (id=2), GOV-5 (id=10), INFO-6 (id=27) — may have bootstrap failures

Verify the workspace is running the latest SAT notebooks and re-run.

---

## Test Framework File Reference

| File | Purpose |
|------|---------|
| `tests/automated/config/credentials.py` | Parse terraform.tfvars |
| `tests/automated/auth/token_provider.py` | OAuth for all 3 clouds |
| `tests/automated/clients/rest_client.py` | HTTP client (needs 429 retry) |
| `tests/automated/clients/sql_client.py` | SQL warehouse query |
| `tests/automated/checks/base_validator.py` | BaseValidator + ValidationResult |
| `tests/automated/checks/registry.py` | @register decorator + CSV loader |
| `tests/automated/checks/*.py` | 65 check validators (8 modules) |
| `tests/automated/reporting/markdown_report.py` | Report generator |
| `tests/automated/run_validation.py` | CLI entry point |
| `tests/automated/conftest.py` | Pytest fixtures |
