# SAT test framework — methodology

This directory holds the automated validation framework for SAT. It was
hardened during 0.8.0 release testing — the notes below capture **the
process that surfaced 8 real bugs in the 11 new 0.8.0 checks** so future
releases can repeat it.

## What the framework does

For every SAT check, independently call the same REST API that SAT's
notebook/SDK code calls, derive an expected `(score, details)` from the
raw response, and compare against the row SAT wrote to
`<catalog>.<schema>.security_checks` for a specific `run_id`. The
agreement verdict is one of:

| Verdict | Meaning |
|---|---|
| `AGREE` | Live API and SAT agree on pass vs violation |
| `DISAGREE` | Live API and SAT disagree — almost always a SAT bug |
| `API_ERROR` | Validator could not reach the API (auth, permissions, network) |
| `SAT_MISSING` | SAT did not write a row for this check/workspace in this run |

`SAT_MISSING` is a finding too — it means the workspace was silently
skipped. We shipped a fix for exactly this case on GOV-45 during 0.8.0
after noticing foghorn (0-jobs workspace) was absent from results.

## Running

### Credentials

The runner reads credentials from `terraform/<cloud>/terraform.tfvars`
(which is `.gitignored`, so credentials never enter git). If you run the
framework from a fresh checkout, point it at a tfvars that contains
`client_id`, `client_secret`, `workspace_id`, `account_console_id`,
`databricks_url`, `sqlw_id`, `analysis_schema_name`. No env vars, no
secrets files — the existing tfvars is the single source of truth.

### Common invocations

```bash
# List SAT runs you can validate against
python -m tests.automated.run_validation --cloud aws --list-runs

# Validate every applicable check against a specific SAT run
python -m tests.automated.run_validation --cloud aws --run-id 15

# Validate across every workspace in the account, not just the tfvars one
python -m tests.automated.run_validation --cloud aws --run-id 15 --all-workspaces

# Validate a single check
python -m tests.automated.run_validation --cloud aws --run-id 15 --check-id NS-12

# Pure API mode (no SAT comparison) — useful when SAT hasn't run yet
python -m tests.automated.run_validation --cloud aws --api-only

# CSV health (independent of SAT)
pytest tests/automated/test_csv_health.py
pytest tests/automated/test_csv_health.py -m 'not online'  # skip URL reachability
```

## Methodology — the loop that found 8 bugs in 0.8.0

1. **Read the CSV row** for the check. Note `evaluation_value`, cloud
   applicability, and the `api` column — that's the ground-truth endpoint.
2. **Read the notebook rule and bootstrap.** Note (a) which intermediate
   table SAT joins, (b) which JSON path the SQL reads, (c) how the rule
   maps data to `(score, additional_details)`.
3. **Call the API live** with the SAT service principal's credentials.
   Use `curl` or the framework's `DatabricksRestClient`. Compare the
   JSON shape against what SAT's explicit schema or SQL expects. *Almost
   every bug we found came from this step — SAT's assumptions about JSON
   path drifted from API reality.*
4. **Query `security_checks`** for that check's row(s) in the latest
   `run_id`. Compare to your computed expectation. Flag disagreements.
5. **Fleet diversity.** Some checks can only exercise pass OR violation
   in a single account. Walk every workspace in the account; a mixed
   fleet usually exercises both paths for per-workspace checks.
6. **Inverse toggles only when fleet diversity fails.** Flipping
   settings (IP ACL, sql_results_download, etc.) to synthesize an
   inverse path is the last resort — it mutates live state.

## Bug-pattern library

Canonical classes of bug the triage methodology has found. If you're
writing a new check or reviewing one, scan for these first.

### Silent SAT failure modes (checks emit no row at all)

| Pattern | Signature | Example |
|---|---|---|
| Missing `F` import | Rule uses `F.col(...)`, `F.regexp_replace(...)`, etc.; top of file imports only `col, regexp_replace` (no `functions as F`) — every rule touching the F.* path raises `NameError`, sqlctrl swallows it silently | 7 rules broken back to run 1 (INFO-6, DP-2, IA-4, IA-6, token-3, UC-770, admin). `test_rule_files_import_functions_as_F` catches this |
| Typo referencing non-existent column | Rule calls `col('foo')` where the SQL's SELECT didn't project `foo` | GOV-5 `col('config_name')` → should be `col('cluster_name')` |
| UNION over a possibly-missing bootstrap table | `SELECT ... UNION SELECT ... FROM {tbl_name_2}` where `bootstrap()` skipped the second source (empty list → no table); AnalysisException substitutes an empty df and the rule falsely reports violation | INFO-38 across `_library_jars` + `_library_mavens`. `test_f_string_unions_over_intermediate_tables_are_guarded` catches this |
| Workspaces with zero source rows silently skipped | `bootstrap()` doesn't create empty Delta tables; rule guards with `if tbl in existing` and never writes a pass row | GOV-45 on foghorn (0 jobs); DP-2 on foghorn (0 clusters) |
| Rule crashes on runtime NULL | `col != NULL` returns NULL in SQL 3-value logic; row excluded | GOV-45 missed `derek.king@databricks.com` CAN_MANAGE on a job whose creator was NULL. Use `COALESCE` |

### False positives (SAT over-flags)

| Pattern | Signature | Example |
|---|---|---|
| Empty-df branch misinterpreted | `if df.columns == 0 → violation` when "no source table" actually means "workspace has none of this resource" | DP-2 on foghorn (0 clusters) falsely flagged as "all_interactive_clusters" violation |
| Off-by-one threshold vs CSV intent | Rule uses `> N` where the CSV's "alert when none" intent means `>= 1` | INFO-29 `df.count() > 1` — a workspace with exactly 1 EXTERNAL_MODEL was flagged |
| Wrong JSON path in SQL | Reading a path that never exists → NULL → else-branch fires | NS-12 `ingress.restriction_mode` (real path is `ingress.public_access.restriction_mode`) |
| Bootstrap schema shape mismatch | Explicit StructType declared for `from_json` doesn't match actual API shape — all fields arrive as NULL | NS-12's flat `{create_time, restriction_mode, update_time}` schema vs nested `public_access.restriction_mode` in the API |

### Score semantics

| Pattern | Signature | Example |
|---|---|---|
| Count-as-score | Rule returns `(check_id, total, ...)` — dashboards treat score as binary, so magnitude just pollutes aggregations | GOV-42 (score=48), GOV-45 |
| List-value in MAP<STRING, STRING> | Dashboard shows an opaque stringified JSON instead of addressable keys — works but operator-unfriendly | INFO-6, DP-2, GOV-11 (pre-fix) |

### HTTP / API quirks

| Pattern | Signature | Example |
|---|---|---|
| HEAD method + `status<400` heuristic | Some servers return 405 Method Not Allowed for HEAD while serving GET (ifconfig.me); misread as "blocked" | NS-14 — the old `HEAD` probe falsely passed on workspaces with open egress |
| Alternative top-level keys for state | API uses distinct top-level key names instead of an enforcement-mode sub-field | NS-12 DRY_RUN lives under `ingress_dry_run` (not `ingress.policy_enforcement.enforcement_mode`) |
| Pagination default is small | Endpoint defaults to 20 items/page when no limit is specified | `/jobs/list` default page size; need explicit `limit=100` + page loop |
| Framework wrong endpoint | Validator hits a path that returns `ENDPOINT_NOT_FOUND` / `RESOURCE_DOES_NOT_EXIST` | NS-9 `/network-connectivity-config`, GOV-25 `/databricks/scripts` — framework failed silently, SAT was correct |

## Adding a validator for a new check

1. Decide which category file it belongs to — `checks/network.py`,
   `checks/identity.py`, `checks/governance.py`, etc.
2. Subclass `BaseValidator`, decorate with `@register("<db_id>")`.
3. Implement `evaluate_from_api(self) -> tuple[int, dict]` — use
   `self.rest` for workspace endpoints and `self.account_rest` for
   account endpoints. Tokens come from `self.token_provider`.
4. Register by importing the module in
   `tests/automated/run_validation.py` (it already imports every check
   category module). If you add a new category file, add the import
   there.
5. Run the single-check invocation above to verify. `DISAGREE` means
   either SAT is wrong or your validator is wrong — go back and read
   the API response.

## Known gaps

- **NS-14 runs from the test runner's host**, not from each target
  workspace's compute. Same limitation as SAT's current implementation;
  per-workspace egress introspection is post-0.8.0 work. This means
  a fleet that includes workspaces behind a NoEgress policy will still
  see "3 of 3 reachable" from every workspace.
- **IA-9 pass path** is unreachable without rotating every stale SP
  secret or using a clean test account. The validator is correct; the
  verdict is just stuck on violation until someone cleans the account.
- **NS-13 violation path** is technically untestable on any live account
  without removing all ALLOW-type IP access lists — too disruptive to
  exercise in verification runs.

## Secrets hygiene

- `terraform/<cloud>/terraform.tfvars` is in `.gitignore`. Do not commit
  it. The framework reads it only at runtime.
- No env vars are used for secrets. No `.env` files. No credential JSON.
- If you need a second set of credentials for a different account, copy
  a tfvars file to a location outside the repo and pass its path.
