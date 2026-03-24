---
name: dependency-audit
description: Audit npm and Python dependencies across all Databricks Apps in a workspace. Use when checking for malicious packages, generating dependency inventories, or investigating supply chain risks. Triggers on dependency audit, npm audit, package audit, supply chain, malicious package, dependency inventory.
---

# Auditing Databricks App Dependencies

Systematic dependency audit of all Databricks Apps deployed in a workspace. Produces a unified inventory of direct and transitive dependencies, checks for flagged/malicious packages, and identifies coverage gaps.

## Prerequisites

- Databricks CLI configured with a profile for the target workspace
- Working directory for source code downloads and reports
- Sufficient workspace permissions to `databricks apps list` and `databricks workspace export-dir`

## Before You Start

### Environment check

Check the Python version. The system Python may be old (e.g., 3.6). Avoid features added after 3.6:
- No `capture_output=True` in `subprocess.run` — use `stdout=subprocess.PIPE, stderr=subprocess.PIPE`
- No f-strings if targeting 3.5 — use `.format()`
- No walrus operator `:=`

```bash
python3 --version
```

If you need modern Python, use `uv run` with inline dependencies.

## Workflow

### Phase 1: Enumerate Apps

List all apps in the workspace with:

```bash
databricks apps list --profile <PROFILE> -o json
```

Parse the JSON output. Extract:
- `name`
- `active_deployment.source_code_path`
- `active_deployment.status.state`
- `creator`

Save the apps list to `apps.json` for reference.

### Phase 2: Download Source Code

Download all apps in parallel, for each app run:

```bash
databricks workspace export-dir <SOURCE_PATH> apps/<APP_NAME>/ --profile <PROFILE> --overwrite
```

**Timeout handling:**
- Set a 120-second timeout per app
- Log failures with the error message
- After the batch completes, **retry failed downloads once** with a longer timeout (300s)
- Record which apps permanently failed

**Post-download validation:**
- Count downloaded apps vs expected
- Print summary: succeeded, failed, timed out

### Phase 3: Find All Dependency Files

Search for ALL dependency manifest and lock file types. **Do not only search for package.json or requirements.txt.**

```
# Required searches — run ALL of these:
**/package.json          # npm direct dependencies
**/package-lock.json     # npm transitive (lockfileVersion 1, 2, or 3)
**/yarn.lock             # Yarn transitive dependencies
**/bun.lock              # Bun transitive dependencies
**/bun.lockb             # Bun binary lock file (note: binary, not parseable as text)
**/requirements*.txt     # Python direct dependencies (no lock file, may include dev dependencies)
**/pyproject.toml        # Python direct dependencies (PEP 518)
**/uv.lock               # uv.lock for Python dependencies (if relevant)
```

For each file found, record:
- App name (first path segment under apps/)
- Relative path within the app
- Lock file type

**Coverage tracking:** For each app with a `package.json` or `pyproject.toml`, note whether it also has a corresponding lock file. Apps with `package.json` or `pyproject.toml`, but NO lock file are **coverage gaps** — their transitive dependencies cannot be confirmed. Python apps using only a `requirements.txt` do not have lock files, so they should be flagged as gaps as well.

### Phase 4: Extract Dependencies

#### 4a: Direct dependencies

Parse each `package.json`, `requirements.txt`, or `pyproject.toml` and extract direct and development dependencies. For `package.json`, look in `dependencies` and `devDependencies`. For Python, parse the respective formats.

For each dependency: package name, version specifier, dep type, which app, which file.

#### 4b: Transitive dependencies from lock files

Lock files have different formats. Handle each:

**package-lock.json (lockfileVersion 2 or 3):**
- Parse the `packages` field
- Each key is a `node_modules/...` path — extract the package name from the last `node_modules/` segment
- Extract: version, resolved URL, integrity hash

**package-lock.json (lockfileVersion 1):**
- Parse the `dependencies` field (recursive — dependencies can be nested)
- Walk the tree recursively to find all transitive deps
- Extract: version, resolved URL, integrity hash

**yarn.lock:**
- Text format, not JSON
- Each entry starts with a package specifier line (e.g., `"react@^18.2.0":`)
- Followed by indented fields: `version`, `resolved`, `integrity`
- Parse with line-by-line text processing

**bun.lock:**
- JSON-like format (Bun v1.2+ uses JSON lockfile by default)
- **CRITICAL:** bun.lock uses trailing commas which `json.load()` rejects. You MUST strip trailing commas before parsing. Use regex: `re.sub(r',(\s*[}\]])', r'\1', content)` to remove them.
- The `packages` field uses array format: each entry is `"pkg-path": ["name@version", "registry-url", {metadata}, "integrity"]`
- Extract package name from index 0 (strip the `@version` suffix), version from index 0 (after `@`), integrity from index 3
- Earlier versions used `bun.lockb` (binary) — note these as unparseable coverage gaps

**uv.lock:**
- Similar to bun.lock, but for Python dependencies
- Also uses trailing commas — same parsing approach as bun.lock

#### 4c: Error handling

- Wrap each file parse in try/except
- Log malformed files but continue processing
- Never let one bad file abort the entire scan

### Phase 5: Check for Flagged Packages

Search for flagged packages using **three independent methods**:

**Method 1: Structured search** — Check extracted dependency data (from Phase 4) against the flagged package list. Use case-insensitive comparison.

**Method 2: Raw text search** — Use Grep to search ALL files under `apps/` for each flagged package name as a substring. This catches packages in vendored `node_modules/`, inline scripts, or non-standard locations that structured parsing would miss.

**Method 3: Partial match** — Search for significant substrings of the flagged names (e.g., if searching for `@pypestream/floating-ui-dom`, also search for `pypestream` and `floating-ui-dom` separately). Typosquat packages often use partial name matches.

**Case sensitivity:** ALL searches MUST be case-insensitive. `EmilGroup` must match `emilgroup`, `EMILGROUP`, etc.

If ANY method finds a match, flag it as a **POSITIVE HIT** with full context (app name, file path, matched text, which method found it).

### Phase 6: Generate Reports

Produce a single unified report in both JSON and CSV formats.

**JSON report** (`dependency_audit_report.json`):
```json
{
  "audit_metadata": {
    "workspace_profile": "...",
    "audit_date": "YYYY-MM-DD",
    "total_apps": N,
    "apps_downloaded": N,
    "apps_with_npm": N,
    "unique_packages": N,
    "total_installations": N
  },
  "flagged_package_results": {
    "packages_searched": ["..."],
    "matches_found": [],
    "verdict": "CLEAN or POSITIVE"
  },
  "coverage_gaps": [
    {"app": "...", "reason": "no lock file / download failed / binary lockb only"}
  ],
  "per_app_summary": {
    "app-name": {
      "package_files": ["..."],
      "lock_files": ["..."],
      "direct_dep_count": N,
      "transitive_dep_count": N
    }
  },
  "all_dependencies": {
    "package-name": [
      {"app": "...", "version": "...", "source": "direct|transitive", "file": "...", "resolved": "..."}
    ]
  }
}
```

**CSV report** (`dependency_audit_report.csv`):
```
app,package,version,source,dep_type,file,resolved,integrity
```

One row per dependency installation. Include both direct and transitive.

### Phase 7: Summary Output

Print a human-readable summary:
1. Verdict on flagged packages (CLEAN or list of hits)
2. Coverage stats (apps scanned, gaps identified)
3. Top dependencies by usage count
4. Report file locations

## Rationalization Table

| Excuse | Reality |
|--------|---------|
| "package-lock.json covers everything" | Wrong. Some apps use yarn.lock or bun.lock instead. Check ALL lock file types. |
| "Direct deps are enough to check" | Wrong. Malicious packages are often transitive — hidden deep in the tree. |
| "JSON parsing is sufficient" | Wrong. Vendored node_modules or inline references won't appear in package.json. Always do a raw text search too. |
| "Case-sensitive search is fine" | Wrong. Package names can vary in casing. EmilGroup vs emilgroup. Always case-insensitive. |
| "I'll retry failed downloads later" | Wrong. Retry them NOW, in the same run. Gaps are unacceptable during a dependency audit. |
| "App has standard deps so it's fine" | Wrong. Without a lock file, transitive deps are unknown. Flag it as a gap. |
| "bun.lock is JSON so json.load() works" | Wrong. Bun emits trailing commas. json.load() will silently fail and you'll get 0 deps. Strip trailing commas first with regex. |
| "The bun.lock parsing errored so those deps are just missing" | Wrong. 0 transitive deps from a bun.lock with hundreds of entries means your parser broke. Check for trailing commas. |

## Red Flags — STOP

If you find yourself doing any of these, you are cutting corners:

- Only searching for `package-lock.json` without also checking `yarn.lock` and `bun.lock`
- Skipping the raw text search because "the JSON parsing already covered it"
- Not retrying failed/timed-out downloads
- Burying coverage gaps in prose instead of listing them explicitly in the report
- Using Python features that don't work in the system Python version
- Producing separate reports instead of one unified report
- Getting 0 transitive deps from a bun.lock file (your parser is broken — check trailing commas)
- Silently catching parse errors without logging them

## Examples

### Example: Full workspace npm audit
User says: "Audit all Databricks Apps for malicious npm packages"
Result: Enumerate all running apps, download source, scan all dependency file types, check flagged packages with 3 methods, produce unified JSON+CSV report with coverage gaps.

### Example: Targeted package search
User says: "Check if any Databricks Apps use lodash.template"
Result: Same workflow but with `lodash.template` as the flagged package. Still produce full inventory.

### Example: Dependency inventory only
User says: "Give me a list of all npm packages used across our Databricks Apps"
Result: Same workflow but skip Phase 5 (no flagged packages). Produce full inventory with coverage tracking.
