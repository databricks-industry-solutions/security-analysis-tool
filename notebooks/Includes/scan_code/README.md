# Code Security Scanning

Scans the notebooks and files in a workspace for two unrelated classes of
problem, and writes both to Unity Catalog for the Code Security pages in the SAT
app.

| Scanner | Answers | Example finding |
|---|---|---|
| Semgrep | Is there a flaw in code written here? | A widget value is interpolated into `spark.sql()`, allowing SQL injection |
| Trivy | Does a package this code installs have a published vulnerability? | `pyyaml 5.1` is affected by CVE-2019-20477; fixed in 5.2 |

There is no overlap. Semgrep cannot know that `pyyaml 5.1` has a CVE, and Trivy
cannot see that your code calls `yaml.load` unsafely. A finding from either is
recorded under its own scanner name.

## What Semgrep checks

Community rule packs target web applications and produce mostly irrelevant
results against notebook code, so this scanner ships a deliberately small
ruleset in `rules/databricks-notebooks.yaml` covering patterns that are both
specific to Databricks and materially risky:

| Rule | Why it matters |
|---|---|
| `databricks-widget-sql-injection` | Widget and job-parameter values reaching `spark.sql()` unsanitised |
| `databricks-secret-written-to-output` | Secrets printed to cell output, which is readable with the notebook and persists in job run logs |
| `databricks-tls-verification-disabled` | `verify=False` silently accepts any certificate |
| `databricks-unsafe-deserialization-from-storage` | `pickle`, `yaml.load` or `torch.load` on a DBFS path that others can write |
| `databricks-credential-in-spark-conf` | Credentials in Spark config, visible to anyone attached to the cluster and in the Spark UI |
| `databricks-governed-data-to-unmanaged-path` | Table data written to `/dbfs` or `/tmp`, outside Unity Catalog's access controls |
| `databricks-external-token-in-source` | A Databricks personal access token hardcoded in source |

The injection rule uses Semgrep's taint mode rather than pattern matching. A
syntactic rule that flags every f-string passed to `spark.sql()` also flags
`spark.sql(f"OPTIMIZE {table}")`, which is safe and common; taint mode reports
only values that originate from a widget and reach the query without parameter
markers.

`tests/code_scanner/test_rules.py` enforces that every rule fires on a
vulnerable fixture and that none fires on a fixture of correct code. Run it
before changing the ruleset:

```bash
pip install semgrep
python tests/code_scanner/test_rules.py
```

An invalid rule file makes Semgrep report zero findings while writing the parse
error to stderr only, so a broken ruleset is indistinguishable from a clean
scan. The scanner validates rules before use and fails the run if they are
invalid.

## What Trivy checks

Trivy matches package names and exact versions against its vulnerability
database. Notebooks have no `requirements.txt`, so versions are recovered from
where they are actually declared:

- `%pip install` and `!pip install` magics in notebook source
- PyPI libraries on job tasks and `dependencies` on serverless environments
- `requirements.txt` files stored in the workspace

**Only exact pins are checked.** `pandas==2.0.3` is resolved to a specific
release and matched; `pandas` and `pandas>=2.0` describe no single version, and
Trivy reports nothing for them. Packages found without a pin are counted and
listed on the Code Overview page, so an empty dependency result is never mistaken
for a clean one.

Packages preinstalled by the Databricks Runtime are not covered. Those versions
come from the runtime rather than from workspace code, and are managed by
selecting a runtime version.

## Required egress

Trivy downloads its binary and a vulnerability database from the public internet.
If the workspace enforces serverless egress controls, allowlist these hosts or
dependency scanning will fail:

| Host | Purpose |
|---|---|
| `github.com` | Trivy release binary |
| `*.githubusercontent.com` | Redirect target for GitHub release downloads |
| `ghcr.io`, `pkg-containers.githubusercontent.com` | Vulnerability database (`trivy-db`) |

The database is roughly 600 MB. It is cached on the Unity Catalog volume
`scanner_cache` in the SAT schema, so it is downloaded about once a day rather
than on every run.

Semgrep needs no external egress: rules are read from the workspace, and the
scanner disables its version check and metrics upload.

If Trivy cannot be installed, the run records the reason, reports dependency
scanning as unavailable on the Code Overview page, and still completes the
Semgrep pass. A run where both scanners are unavailable fails rather than
reporting zero findings.

## Running a scan

The installer creates a **SAT Code Scanner** job that runs daily at 04:00 in the
configured timezone. It can also be started, cancelled, and rescheduled from
Data Collection in the app.

Findings are written to two tables in the SAT schema:

| Table | Contents |
|---|---|
| `code_scan_findings` | One row per finding, with severity, object path, and for dependency findings the package, installed version and fixed version |
| `code_scan_runs` | One row per run: objects scanned, packages checked, per-scanner status, and any note about unpinned packages |

Each finding carries a fingerprint derived from the scanner, rule, object path
and matched source text. It stays stable when a notebook is edited above the
finding, and stays distinct for separate occurrences of one rule in the same
file.

## Scan scope and duration

Discovery walks `/Users`, `/Shared` and `/Repos`, collecting notebooks and files
with a scannable extension (`.py`, `.sql`, `.r`, `.scala`, `.sh`, `.yaml`,
`.yml`, `.json`). Source is exported in batches of 200 with a 16-way thread pool,
scanned, then deleted.

Semgrep is significantly slower than secret scanning: it parses each file rather
than pattern-matching it. Expect a workspace of a few thousand notebooks to take
tens of minutes. The job allows six hours and fails rather than hanging
indefinitely.
