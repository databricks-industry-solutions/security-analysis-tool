# AGENTS.md

Guidance for AI coding agents (and new human contributors) working in this
repository. This is the tool-agnostic entry point. Claude Code users also have
[`CLAUDE.md`](CLAUDE.md), which is the **source of truth** for the detailed
rules summarized here; when the two ever disagree, `CLAUDE.md` wins.

Read this file before making changes.

---

## What this project is

The **Security Analysis Tool (SAT)** analyzes Databricks account and workspace
configurations against Databricks security best practices. It ships as
Databricks notebooks orchestrated over a Python SDK, deployed via Databricks
Asset Bundles (DABS) or Terraform, and run on a schedule in the customer's own
workspace.

**Customers install this code and run it in their own environment.** Treat the
notebooks and SDK as a shipped product: a change that alters runtime behavior,
breaks a notebook, or changes what an operator sees in output is a regression,
not a cleanup.

## Repository map

| Path | What lives here |
|------|-----------------|
| `src/securityanalysistoolproject/` | The SAT Python SDK — `core/` (REST client, auth, parsing), `clientpkgs/` (one client class per Databricks API), and its own `tests/` (SDK pytest suite) |
| `src/brickhound/` | BrickHound permissions-analysis SDK (kept separate to avoid dependency conflicts) |
| `notebooks/` | Databricks notebooks: `Setup/`, `Includes/` (shared logic + `scan_secrets/`), `Utils/` (bootstrap/common), driver notebooks, `brickhound/` |
| `configs/` | `security_best_practices.csv` (master check list), check toggles, TruffleHog + DASF configs |
| `dabs/` | Interactive DABS installer (`main.py`, `sat/`) and bundle templates |
| `terraform/` | Cloud-specific (`aws/`, `azure/`, `gcp/`) and `common/` deployment modules |
| `app/` | BrickHound Gradio web app (`app/brickhound/`) deployed via Databricks Apps |
| `tests/` | Automated check-validation framework (`tests/automated/`) — independently re-derives each check from the live API and compares against SAT's output. See `tests/README.md`. Distinct from the SDK pytest suite above. |
| `dashboards/`, `docs/` | Lakeview dashboards and the Docusaurus documentation site source |
| `.claude/`, `skills/` | Agent tooling: `.claude/commands/` (project slash commands, e.g. `add-sat-check`) and `skills/` (customer-facing Agent Skills such as `dependency-audit`) |

## Common commands

```bash
# Build the SDK and refresh the workspace-installable wheel
cd src/securityanalysistoolproject && python setup.py sdist bdist_wheel
cp dist/dbl_sat_sdk-<version>-py3-none-any.whl ../../lib/

# Run SDK tests
cd src/securityanalysistoolproject && pytest tests/
pytest tests/test_clusters.py -v          # single test file

# Validate checks against a real workspace (automated framework; see tests/README.md)
python -m tests.automated.run_validation --cloud aws --list-runs
python -m tests.automated.run_validation --cloud aws --run-id <id> --check-id NS-12
pytest tests/automated/test_csv_health.py -m 'not online'   # offline CSV lint

# Deploy SAT (interactive installer)
./install.sh
```

Python 3.9+ is required. Runtime dependencies are version-pinned; keep them pinned.

---

## Conventions every agent must follow

### 1. Notebooks are Databricks *source-format* files — do not "clean up" their structure

Lines beginning with `# Databricks notebook source`, `# COMMAND ----------`,
`# MAGIC`, and `# DBTITLE` are **required syntax**, not comments. `# MAGIC %sh`,
`# MAGIC %md`, and `# MAGIC` continuation lines *are the executable content* of a
cell. Never strip, reflow, or "de-duplicate" them — doing so breaks the notebook
on import. Any comment tooling you run must be notebook-aware.

`print()` output in notebooks is intentional operator-facing UX. Don't blanket-
replace it with logging; only remove genuine debug noise.

### 2. Preserve behavior

Favor changes that are provably behavior-neutral. When you edit a file, be able
to show that executable code is unchanged (e.g. only comments/strings differ,
and the file still compiles/imports). Reserve behavior changes for deliberate,
clearly-scoped work — not incidental cleanup.

### 3. Branching

Create feature branches **from a `release/*` branch**, never from `main` and
never from another feature branch. Name them descriptively
(`SFE-XXXX_feature_name`, `bugfix/...`, `chore/...`). `main` is protected.

### 4. Pre-commit gates (all must pass before committing)

- **Typos:** `git diff --cached --name-only | xargs codespell`. Add intentional
  words to `.codespell-ignore`.
- **`security_best_practices.csv` uniqueness:** `id` and `check_id` must each be
  unique across all rows. Validate on every edit to that file.
- **Doc URLs:** any `*_doc_url` added to the CSV must return HTTP 200.
- **Schema comment sync:** if you add/remove/rename a table or column, update
  `notebooks/Utils/common.py → apply_schema_comments()` to match.

See `CLAUDE.md` for the exact validation scripts.

### 5. SDK version sync

The wheel in `lib/` and `SDK_VERSION` in `notebooks/Includes/install_sat_sdk.py`
must match `src/securityanalysistoolproject/setup.py`. A mismatch makes every
notebook fail at install time.

### 6. Adding a security check

Follow the pre-flight checklist in `CLAUDE.md`: call the live Databricks API
first and inspect the real JSON shape (Settings v2 keys vary per setting — never
guess column names), add the row to `configs/security_best_practices.csv`,
implement the rule in `notebooks/Includes/workspace_analysis.py`, then run the
uniqueness, URL, and typo checks.

## Code patterns

- **API clients** extend `SatDBClient` and expose one method per endpoint, using
  the inherited `self.get()/self.post()` helpers (see `clientpkgs/`).
- **Data collection** goes through `bootstrap(viewname, func, ...)` in
  `notebooks/Utils/common.py`, which JSON-serializes results into a Delta table.
- **Checks** return `(check_id, score, details)` where `score = 0` passes and
  `1+` counts violations; wire them up with `sqlctrl(workspace_id, sql, rule)`.
- **Auth** is multi-cloud and handled centrally in
  `SatDBClient._update_token_master()` (AWS/GCP OAuth, Azure MSAL + Databricks).
- Use the centralized logger (`LoggingUtils`) in SDK code; escape single quotes
  in any JSON before building SQL `INSERT` statements.

## When you finish

State clearly whether changes are committed / pushed, the branch and commit
hash, and the files touched. If tests were run, report the result; if a step was
skipped, say so.

## Further reading

- [`CLAUDE.md`](CLAUDE.md) — detailed conventions, check-authoring checklist, and mandatory workflows
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution process, project structure, and PR expectations
- [`tests/README.md`](tests/README.md) — check-validation framework methodology and the triage loop for debugging a check
- [`VERSIONING.md`](VERSIONING.md) — semantic versioning and branching strategy
- [`SECURITY.md`](SECURITY.md) — reporting security issues
- [SAT documentation site](https://databricks-industry-solutions.github.io/security-analysis-tool/)
