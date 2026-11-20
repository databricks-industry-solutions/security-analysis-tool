# AGENTS.md

Guidance for AI coding agents (and new human contributors) working in this
repository. This is the tool-agnostic entry point. Claude Code users also have
[`CLAUDE.md`](CLAUDE.md), which is the **source of truth** for the detailed
rules summarized here; when the two ever disagree, `CLAUDE.md` wins.

Read this file before making changes.

---

## What this project is

The **Security Analysis Tool (SAT)** is a single **Databricks App** that analyzes
a Databricks account's security posture:

- **Permission Analysis** (BrickHound) — a graph of who can access what, with
  privilege-escalation paths, resources shared to the whole account, privileged
  non-IdP identities, and denylist candidates.
- **Credential Exposure** — secrets found hardcoded in notebook source, workspace
  files, and cluster configurations (scanned with TruffleHog).
- **Security Assistant** — natural-language questions over the findings, backed by
  a Databricks Genie space and a model-serving endpoint.

The app is the **sole supported delivery**. The classic notebook + Lakeview-
dashboard product (the security-best-practices checks, the driver job, the General
and Executive dashboards, the DASF mapping) has been **retired**; those checks now
live natively in the Databricks Governance Hub Security tab. The app serves its own
UI, provisions its own collection jobs, stores results in Unity Catalog, and reads
them back through a SQL warehouse.

**Customers install this code and run it in their own environment.** Treat the app,
notebooks, and SDK as a shipped product: a change that alters runtime behavior,
breaks a notebook, or changes what an operator sees in output or the UI is a
regression, not a cleanup.

## Repository map

| Path | What lives here |
|------|-----------------|
| `app/security-analysis-tool/` | The **Flask app**. `app.py` serves the UI + API, self-provisions the collection jobs, and manages credentials. `assets_data.py` holds `ASSETS_ZIP_B64` — a base64-zipped bundle of the `notebooks/`, `configs/`, and `lib/` files the app imports into its service principal's home and runs. See its `README.md`. |
| `notebooks/` | The collection notebooks the app provisions as jobs: `security_analysis_initializer.py` (schema/table setup), `permission_analysis_data_collection.py` (BrickHound graph collector), `security_analysis_secrets_scanner.py` + `Includes/scan_secrets/` (TruffleHog), `brickhound/` (`00_config` + analysis notebooks `05`–`07`), `Utils/{initialize,common}.py` (config resolution + tables/helpers), `diagnosis/pre_run_config_check.py` (scanner pre-flight) |
| `src/securityanalysistoolproject/` | Source of the `dbl-sat-sdk` wheel — `SatDBClient` (REST client, auth) and `clientpkgs/`; its own pytest suite in `tests/` |
| `src/brickhound/` | BrickHound permissions-graph SDK (kept separate to avoid dependency conflicts) |
| `lib/` | The prebuilt SDK wheel the notebooks install |
| `configs/` | TruffleHog detectors (`trufflehog_detectors.yaml`, `custom_*.sample`) and the Genie space template |
| `terraform/`, `dabs/` | The two installers (`aws/`, `azure/`, `gcp/`, `common/`); **both only deploy the app** |
| `docs/` | The Docusaurus documentation site. Do not remove or restructure it. |
| `.claude/`, `skills/` | Agent tooling: project slash commands and customer-facing Agent Skills |

## Common commands

```bash
# Rebuild the SDK wheel from source, then refresh lib/
cd src/securityanalysistoolproject && python setup.py sdist bdist_wheel
cp dist/dbl_sat_sdk-<version>-py3-none-any.whl ../../lib/
# then bump SDK_VERSION in notebooks/Includes/install_sat_sdk.py to match

# Run SDK tests
cd src/securityanalysistoolproject && pytest tests/

# Deploy SAT (interactive installer — deploys the app only)
./install.sh

# Build the docs site (strict link check; Node 24 required)
cd docs/sat && yarn build       # or: yarn start --port 3000   to preview
```

Python 3.9+ is required. Runtime dependencies are version-pinned; keep them pinned.

### Rebuild the app bundle after changing notebooks/configs/lib

The deployed app ships `notebooks/`, `configs/`, and `lib/` **inside**
`app/security-analysis-tool/assets_data.py` (`ASSETS_ZIP_B64`). After editing any of
those, rebuild the bundle so the app provisions the new files: decode the base64
zip, replace the changed entries from disk, re-zip (`ZIP_DEFLATED`, preserving the
archive paths), and write it back as `ASSETS_ZIP_B64 = "<base64>"`. A change left
out of the bundle will not reach the running jobs.

---

## Conventions every agent must follow

### 1. Notebooks are Databricks *source-format* files — do not "clean up" their structure

Lines beginning with `# Databricks notebook source`, `# COMMAND ----------`,
`# MAGIC`, and `# DBTITLE` are **required syntax**, not comments. `# MAGIC %sh`,
`# MAGIC %md`, and `# MAGIC` continuation lines *are the executable content* of a
cell. Never strip, reflow, or "de-duplicate" them. `print()` output in notebooks is
intentional operator-facing UX — don't blanket-replace it with logging.

### 2. The app UI is one large inline `<script>` — validate the rendered JS

`app/security-analysis-tool/app.py` returns the whole UI from `get_main_html()` as a
single plain (non-raw) triple-quoted Python string containing one big inline
`<script>`. Because Python processes escapes in that string, an apostrophe written
as `\'` (or a raw `'`) inside a **single-quoted JavaScript string** collapses to a
bare quote and breaks the entire script — every page then fails to render. `py_compile`
does **not** catch this (it only checks the Python). Before deploying an `app.py`
change, evaluate the template and syntax-check the real output, e.g.:

```python
import ast, re, subprocess, tempfile
src = open("app/security-analysis-tool/app.py").read()
s = src.index("return '''", src.index("def get_main_html")) + len("return ")
html = ast.literal_eval(src[s:src.index("'''", s + 3) + 3])
for js in re.findall(r"<script>(.*?)</script>", html, re.S):
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False); f.write(js); f.close()
    subprocess.run(["node", "--check", f.name], check=True)
```

Prefer double-quoted JS strings or template literals, and avoid apostrophes in
single-quoted JS strings, inside that template.

### 3. Preserve behavior

Favor changes that are provably behavior-neutral. When you edit a file, be able to
show that executable code is unchanged (only comments/strings differ, and the file
still compiles/imports). Reserve behavior changes for deliberate, clearly-scoped
work — not incidental cleanup.

### 4. Branching

Create feature branches **from a `release/*` branch**, never from `main` and never
from another feature branch. Name them descriptively (`SFE-XXXX_feature_name`,
`bugfix/...`, `chore/...`). `main` is protected.

### 5. Pre-commit gates (all must pass before committing)

- **Typos:** `git diff --cached --name-only | xargs codespell`. Add intentional
  words to `.codespell-ignore`.
- **Schema comment sync:** if you add/remove/rename a table or column, update the
  matching `_set_table_comment()` / `_set_column_comments()` call in
  `notebooks/Utils/common.py` so the comments stay in sync.
- **Docs build:** if you touched `docs/`, run `yarn build` — the strict link check
  fails on a broken internal link.
- **App JS:** if you touched `app.py`, run the inline-script check in §2.

### 6. SDK version sync

The wheel in `lib/` and `SDK_VERSION` in `notebooks/Includes/install_sat_sdk.py`
must match `src/securityanalysistoolproject/setup.py` (currently `0.1.54`). A
mismatch makes every notebook fail at install time.

## Code patterns

- **API clients** extend `SatDBClient` and expose one method per endpoint, using
  the inherited `self.get()/self.post()` helpers (see `clientpkgs/`).
- **Notebook integration** starts with `%run ./Includes/install_sat_sdk`,
  `./Utils/initialize`, `./Utils/common`. `initialize.py` resolves config from job
  parameters with a Unity Catalog secret fallback.
- **Authentication** is **Databricks OAuth (M2M) on every cloud, including Azure**
  — account token from `{accounts-host}/oidc/accounts/{id}/v1/token`, workspace
  token from `{host}/oidc/v1/token`. There is **no Microsoft Entra / MSAL path and
  no Azure tenant/subscription**; on Azure the service principal uses a **Databricks
  OAuth secret**, not an Azure AD client secret. SAT makes no cloud-provider (ARM)
  calls.
- **Credentials** are **Unity Catalog secrets** in the results schema
  (`{catalog}.{schema}.<key>`) — there is no `sat_scope` or any other secret scope.
  Notebooks read them via `_sat_cred` / `_bh_cred`. Jobs that read UC secrets run on
  serverless environment **client ≥ 4**.
- Escape single quotes in any JSON before building SQL `INSERT`/`MERGE` statements.

## Operational model (how the running app behaves)

- **Self-provisioned jobs.** The app creates its own serverless jobs from
  `PROVISION_SPECS` in `app.py` (initializer + permissions, secrets,
  shared-to-account, privileged-non-IdP, denylist). Config is passed as **job
  parameters** (notably `analysis_schema_name` and `scan_scope`).
- **Which workspaces get scanned** is `account_workspaces.analysis_enabled`,
  maintained by the app's **Data Collection → Manage → Sync workspaces** action: it
  lists the account's workspaces and enables the ones the SAT service principal is a
  **workspace admin** of. Add the SP as a workspace admin and Sync to include a
  workspace; remove it and Sync to drop it. (Switching collection scope to "Multiple
  workspaces" runs a Sync automatically.) Registration is **not** done by the
  collector jobs.
- **Collection scope governs both.** The "This workspace only" vs "Multiple
  workspaces" setting gates **both** permission-resource collection **and** secret
  scanning. "Multiple" scans every enabled (SP-administered) workspace; a workspace
  the serverless compute cannot reach (network policy / cross-workspace / region) is
  **soft-skipped and recorded**, not failed.
- **Changing the results schema** auto-migrates the account-credential UC secrets
  into the new schema and re-provisions the jobs (`_on_schema_change`).
- **Rotating credentials:** new OAuth secret in the console → **Settings → Account
  credentials → Update credentials** (verified, stored as UC secrets). Jobs read the
  secret at run time, so the next run picks it up — no redeploy or re-provision.
- **Secret-scanner temp files must use `tempfile.mkdtemp()`, never a fixed `/tmp`
  path** (and do not honor a config-supplied scratch path). Serverless reuses
  containers across runs under different OS users, so a fixed `/tmp` path fails with
  `Permission denied`. The TruffleHog **binary** stays at a fixed path (only read/
  executed, installer skips when present).

## When you finish

State clearly whether changes are committed / pushed, the branch and commit hash,
and the files touched. If tests or a docs build were run, report the result; if a
step was skipped, say so.

## Further reading

- [`CLAUDE.md`](CLAUDE.md) — detailed conventions and mandatory workflows (source of truth)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contribution process and PR expectations
- [`VERSIONING.md`](VERSIONING.md) — semantic versioning and branching strategy
- [`SECURITY.md`](SECURITY.md) — reporting security issues
- [SAT documentation site](https://databricks-industry-solutions.github.io/security-analysis-tool/)
