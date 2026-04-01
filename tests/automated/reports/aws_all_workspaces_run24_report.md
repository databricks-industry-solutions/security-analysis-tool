# SAT Validation Report — All AWS Workspaces, Run 24

**Generated:** 2026-04-01  
**SAT Run ID:** 24 (with SDK v0.1.49)  
**Cloud:** AWS  
**Workspaces:** 4 (plain, csp, sfe, foghorn)  
**Total checks validated:** 63 per workspace x 4 = 252

---

## Grand Summary

| Workspace | AGREE | DISAGREE | API_ERROR | SAT_MISSING | Accuracy |
|-----------|-------|----------|-----------|-------------|----------|
| plain | 57 | 3 | 0 | 3 | 95.0% |
| csp | 60 | 2 | 0 | 1 | 96.8% |
| sfe | 55 | 5 | 0 | 3 | 91.7% |
| foghorn | 57 | 5 | 0 | 1 | 91.9% |
| **TOTAL** | **229** | **15** | **0** | **8** | **93.8%** |

**Zero API errors** across all 252 check validations.

---

## All Discrepancies (15 total, 7 unique checks)

### NS-9: Network policy configuration — 4 workspaces DISAGREE

| Workspace | API | SAT |
|-----------|-----|-----|
| plain | FAIL | PASS |
| csp | FAIL | PASS |
| sfe | FAIL | PASS |
| foghorn | FAIL | PASS |

**Pattern:** API says FAIL on all 4, SAT says PASS on all 4. This is systematic.

**Root cause:** The test framework's NS-9 validator queries the account network policies API and workspace network config API, but the logic for matching a workspace to its network policy may differ from SAT's approach. SAT uses a complex SQL join across `acctworkspaces`, `workspace_network_config_{ws_id}`, and `account_networkpolicies` tables. The validator may be failing to find the policy assignment via the REST API path it uses. Needs investigation of the exact API endpoints and response shapes for workspace-to-policy mapping.

**Classification:** Likely a **test framework validator bug** — the validator's policy lookup logic doesn't match SAT's SQL join approach. SAT's result (PASS) is probably correct given it consistently passes across all 4 workspaces.

---

### INFO-38: Third-party library control — 4 workspaces DISAGREE

| Workspace | API | SAT |
|-----------|-----|-----|
| plain | PASS | FAIL |
| csp | PASS | FAIL |
| sfe | PASS | FAIL |
| foghorn | PASS | FAIL |

**Pattern:** API finds artifact allowlists on all 4, SAT reports "No artifact allowlist configured" on all 4. Systematic.

**Root cause:** The API (`GET /api/2.1/unity-catalog/artifact-allowlists/LIBRARY_JAR`) returns allowlist entries, but SAT's bootstrap for `artifacts_allowlists_library_jars_{workspace_id}` either fails to collect the data or the response key doesn't match what `bootstrap()` expects. Since this is consistent across all workspaces, it's a **SAT collection/bootstrap bug** — the intermediate table is likely always empty.

**Classification:** **SAT bug** — data collection issue in the artifact allowlists bootstrap.

---

### INFO-29: External model serving endpoints — 2 workspaces DISAGREE

| Workspace | API | SAT |
|-----------|-----|-----|
| sfe | PASS | FAIL |
| foghorn | PASS | FAIL |

**Pattern:** API finds external model endpoints, SAT says none found.

**Root cause:** The validator calls `GET /api/2.0/serving-endpoints` and filters for `endpoint_type == 'EXTERNAL_MODEL'`. The check logic in SAT (`workspace_analysis.py` check 90) also looks for `endpoint_type = 'EXTERNAL_MODEL'` but requires `df.count() > 1` (more than 1 endpoint). If sfe/foghorn have exactly 1 external model endpoint, SAT would report FAIL while the API confirms PASS. This is a **SAT logic issue** — the threshold should be `>= 1`, not `> 1`.

**Classification:** Possible **SAT bug** — off-by-one in the count threshold. Or possible **test framework validator bug** if the validator doesn't apply the same `> 1` threshold.

---

### GOV-28: Govern model assets — 1 workspace DISAGREE (plain)

| Workspace | API | SAT |
|-----------|-----|-----|
| plain | PASS | FAIL |

**Root cause:** The validator found registered models via the UC models API, but SAT reported no models. This was previously a rate-limit issue (429) that caused the validator to fail. With the throttling fix, the validator now correctly finds models. The DISAGREE here means SAT's `registered_models_{workspace_id}` table may have been empty during collection for the plain workspace — possibly a transient bootstrap failure.

**Classification:** Likely **transient SAT collection issue** — the models API may have been rate-limited during SAT's bootstrap.

---

### GOV-11: DBFS mounts — 1 workspace DISAGREE (sfe)

| Workspace | API | SAT |
|-----------|-----|-----|
| sfe | FAIL | PASS |

**Root cause:** The validator calls `GET /api/2.0/dbfs/list?path=/mnt` and found files. SAT reported no mounts. The validator checks for any files under `/mnt`, while SAT's check queries the `dbfssettingsmounts_{workspace_id}` table which is populated differently (via `dbutils.fs.mounts()` equivalent). The data sources may differ.

**Classification:** Possible **test framework validator bug** — the validator uses DBFS list API while SAT uses a different collection method for mounts.

---

### GOV-25: Init scripts stored in DBFS — 1 workspace DISAGREE (sfe)

| Workspace | API | SAT |
|-----------|-----|-----|
| sfe | PASS | FAIL |

**Root cause:** The validator checks `/databricks/scripts` path via DBFS API and found nothing. SAT reported init scripts exist. SAT's check queries the `legacyinitscripts_{workspace_id}` table which may check a different path or use a different API endpoint for legacy init scripts.

**Classification:** Possible **test framework validator bug** — the validator may be checking the wrong DBFS path.

---

### DP-2: Cluster instance disk encryption — 1 workspace DISAGREE (foghorn)

| Workspace | API | SAT |
|-----------|-----|-----|
| foghorn | PASS | FAIL |

**Root cause:** The validator calls `GET /api/2.1/clusters/list` and found no clusters with `enable_local_disk_encryption=false` and `cluster_source IN ('UI', 'API')`. SAT reports a violation. Foghorn is a serverless workspace — it may have no interactive clusters visible via the API, but SAT's intermediate table may contain stale data from a previous collection.

**Classification:** Possible **stale SAT data** on a serverless workspace, or **test framework validator bug** if foghorn has clusters visible only through a different API.

---

### INFO-6: Number of admins — 1 workspace DISAGREE (foghorn)

| Workspace | API | SAT |
|-----------|-----|-----|
| foghorn | FAIL | PASS |

**Root cause:** The validator calls the SCIM Groups API and found admins (FAIL = too many admins). SAT reports PASS. The check uses `evaluation_value = -1` which means `len(admins) > -1` — any number of admins should fail. If SAT reports PASS, the `groups_{workspace_id}` table may have been empty during collection for foghorn.

**Classification:** Possible **SAT collection issue** on the serverless workspace — the SCIM groups bootstrap may have failed.

---

## SAT_MISSING (8 instances, 4 unique checks)

| Check | Workspaces Missing |
|-------|--------------------|
| DP-2 (id=2) | plain, sfe |
| GOV-5 (id=10) | plain, sfe |
| INFO-6 (id=27) | plain, csp, sfe |
| GOV-45 (id=123) | foghorn |

These checks have validators but SAT didn't produce a result. Root causes:
- **DP-2, GOV-5**: Bootstrap for `clusters_{workspace_id}` or `spark_versions_{workspace_id}` may have failed on these workspaces
- **INFO-6**: Bootstrap for `groups_{workspace_id}` consistently fails on 3 of 4 workspaces — likely a SCIM API issue during collection
- **GOV-45**: Foghorn is serverless — the `job_permissions` bootstrap may not run on serverless compute

---

## Summary of Issues by Priority

### P1: SAT Bugs (fix in SAT code)

| Issue | Workspaces | Check |
|-------|------------|-------|
| Artifact allowlists bootstrap always returns empty | All 4 | INFO-38 |
| External model endpoint count threshold `> 1` should be `>= 1` | sfe, foghorn | INFO-29 |

### P2: Test Framework Validator Bugs (fix in test framework)

| Issue | Workspaces | Check |
|-------|------------|-------|
| NS-9 validator policy lookup doesn't match SAT's SQL join | All 4 | NS-9 |
| GOV-11 validator uses DBFS list API instead of mounts collection | sfe | GOV-11 |
| GOV-25 validator checks wrong DBFS path for legacy init scripts | sfe | GOV-25 |

### P3: SAT Collection/Bootstrap Issues (investigate)

| Issue | Workspaces | Check |
|-------|------------|-------|
| INFO-6 groups bootstrap fails on 3 workspaces | plain, csp, sfe | INFO-6 |
| GOV-45 job_permissions not available on serverless | foghorn | GOV-45 |
| DP-2/GOV-5 clusters bootstrap missing on some workspaces | plain, sfe | DP-2, GOV-5 |
| DP-2 stale data on serverless workspace | foghorn | DP-2 |
| GOV-28 models collection transient failure | plain | GOV-28 |

---

## Per-Workspace Reports

- `tests/automated/reports/aws_plain_run24_report.md`
- `tests/automated/reports/aws_csp_run24_report.md`
- `tests/automated/reports/aws_sfe_run24_report.md`
- `tests/automated/reports/aws_foghorn_run24_report.md`
