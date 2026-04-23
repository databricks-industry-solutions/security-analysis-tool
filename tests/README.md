# SAT test framework — methodology

This directory holds the automated validation framework for SAT. It was
hardened during 0.8.0 release testing — the notes below capture the
methodology so future releases can repeat it.

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

## Methodology — the triage loop

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

## Common patterns to check during review

Scan for these before writing or reviewing a new check. Each describes a
signature and what to look for; the static lint under
`tests/automated/test_rule_hygiene.py` catches the first two
automatically.

### Import and reference hygiene

- **Missing `functions as F` import** — if a rule references `F.col(...)`,
  `F.regexp_replace(...)`, etc., the file must have
  `from pyspark.sql import functions as F`. The static lint enforces this.
- **Column reference matches SQL projection** — every `col('foo')` in a
  rule should correspond to a column in the rule's SQL `SELECT`.

### Intermediate-table handling

- **UNION across bootstrap tables** — `bootstrap()` only writes a table
  when the source list is non-empty. Any `UNION` over
  `{prefix}_{workspace_id}` tables must be preceded by a
  `spark.catalog.listTables(json_['intermediate_schema'])` check and
  only include tables that exist. The static lint enforces this.
- **Empty-df handling** — when `df is None` or `isEmpty(df)`, the rule
  should return a pass if the semantic is "none present" (e.g., zero
  clusters means zero unencrypted clusters).
- **NULL in SQL comparisons** — `col != NULL` returns NULL in SQL
  3-value logic and excludes rows. Use `COALESCE(col, '')` or an
  explicit `IS NULL` branch.

### Dashboard compatibility

- **Binary score** — `security_checks.score` is read binarily: `0` is pass,
  anything else is violation. Returning counts (e.g. `total`) doesn't
  change dashboard behavior and obscures aggregations.
- **`additional_details` shape** — typed `MAP<STRING, STRING>`. Dicts with
  nested list values get coerced to stringified JSON (values work but
  lose per-key addressability). Prefer one entry per item with a
  `_summary` key for overflow.

### API / endpoint drift

- **JSON path** — always call the live API and inspect the real response
  shape before writing the SQL / bootstrap schema. Paths have changed
  (sometimes the API uses parallel top-level keys rather than
  enforcement-mode sub-fields).
- **HTTP method quirks** — some endpoints respond `405 Method Not
  Allowed` to `HEAD` while serving `GET`. Prefer `GET` with
  `stream=True` for simple reachability probes.
- **Pagination defaults** — some APIs default to small page sizes
  (e.g., 20). Specify an explicit limit and loop `next_page_token`.
- **Endpoint existence** — if a framework validator returns
  `RESOURCE_DOES_NOT_EXIST` or `ENDPOINT_NOT_FOUND`, the path is wrong
  (or the API has moved).

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
