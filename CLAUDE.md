# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Security Analysis Tool (SAT)** is a Databricks solution that analyzes Databricks account and workspace configurations to provide security recommendations based on Databricks best practices. SAT runs as Databricks notebooks that orchestrate multi-cloud (AWS, Azure, GCP) security analysis and secret scanning.

## Development Commands

### SDK Development

The Python SDK is located in `src/securityanalysistoolproject/`.

**Build and install the SDK:**
```bash
cd src/securityanalysistoolproject
python setup.py sdist bdist_wheel
pip install dist/dbl-sat-sdk-<version>-py3-none-any.whl
```

**Run tests:**
```bash
cd src/securityanalysistoolproject
pytest tests/
```

**Run specific test:**
```bash
cd src/securityanalysistoolproject
pytest tests/test_clusters.py -v
```

**SDK version:** The SDK version is maintained in `src/securityanalysistoolproject/setup.py` (currently `__version__ = "0.1.40"`)

### SDK Distribution

The SAT SDK is distributed as a wheel file stored in a centralized location for easy notebook installation.

**Wheel location:** `lib/dbl_sat_sdk-{version}-py3-none-any.whl`

**After building the SDK, copy to lib directory:**
```bash
cp src/securityanalysistoolproject/dist/dbl_sat_sdk-{version}-py3-none-any.whl lib/
```

**Installation in notebooks:** Notebooks automatically install the SDK from the workspace file path using dynamic path resolution in `notebooks/Includes/install_sat_sdk.py`. The installation approach:
- Uses Databricks workspace file syntax: `/Workspace/.../lib/dbl_sat_sdk-{version}.whl`
- Dynamically constructs the path based on the notebook's location
- Works from any notebook depth (root, subdirectories, nested subdirectories)
- No changes needed to the 23+ notebooks that call `%run ./Includes/install_sat_sdk`

**CRITICAL: After copying a new wheel to `lib/`, update `SDK_VERSION` in `notebooks/Includes/install_sat_sdk.py` to match. A mismatch causes all notebooks to fail at install time.**

### DABS Deployment

DABS (Databricks Asset Bundles) is the deployment mechanism for SAT. Located in `dabs/`.

**Install and deploy:**
```bash
./install.sh
# OR
cd dabs
pip install -r requirements.txt
python main.py
```

This interactive installer configures the Databricks workspace, creates secrets, and deploys SAT assets.

## Architecture

### Core Components

1. **SDK Layer** (`src/securityanalysistoolproject/`)
   - **`core/`**: Foundation classes
     - `dbclient.py`: `SatDBClient` - Main REST API wrapper for Databricks APIs. Handles multi-cloud authentication (AWS OAuth, Azure MSAL tokens, GCP OAuth)
     - `logging_utils.py`: Centralized logging configuration
     - `parser.py`: Configuration parsing and input handling
     - `wmconstants.py`: Workspace management constants

   - **`clientpkgs/`**: 30+ specialized API client classes, one per Databricks API surface area
     - Examples: `clusters_client.py`, `workspace_client.py`, `unity_catalog_client.py`, `scim_client.py`
     - Each client extends `SatDBClient` and implements specific API logic
     - Clients handle pagination, error handling, and data transformation

2. **Notebooks Layer** (`notebooks/`)
   - **Driver notebooks:** Main orchestration
     - `security_analysis_driver.py`: Orchestrates workspace security analysis across all configured workspaces
     - `security_analysis_secrets_scanner.py`: Scans for hardcoded secrets using TruffleHog
     - `security_analysis_initializer.py`: Initial workspace setup

   - **`Includes/`**: Shared notebook utilities
     - `install_sat_sdk.py`: Installs the SDK wheel in notebook environment
     - `workspace_analysis.py`: Core security analysis logic
     - `workspace_settings.py`: Workspace settings retrieval
     - `scan_secrets/`: Secret scanning implementation

   - **`Utils/`**: Bootstrap and common utilities
     - `common.py`: Shared functions used across notebooks
     - `initialize.py`: Initialization routines
     - `accounts_bootstrap.py`: Account-level configuration bootstrap
     - `workspace_bootstrap.py`: Workspace-level configuration bootstrap

   - **`Setup/`**: Setup notebooks for initial configuration
     - `4. enable_workspaces_for_sat.py`: Configures workspaces for analysis
     - `5. import_dashboard_template_lakeview.py`: Imports Lakeview dashboards
     - `7. update_sat_check_configuration.py`: Updates security check configurations

3. **DABS Installer** (`dabs/`)
   - `main.py`: Interactive installation wizard using `inquirer` and `rich` libraries
   - `sat/config.py`: Configuration form and secret generation logic
   - `sat/utils.py`: Utility functions for cloud detection and validation
   - `dabs_template/`: Databricks Asset Bundle templates for job deployment

4. **Configuration** (`configs/`)
   - `security_best_practices.csv`: Master list of security checks and recommendations
   - `self_assessment_checks.yaml`: Enabled/disabled flags for security checks
   - `trufflehog_detectors.yaml`: TruffleHog detector configuration for secret scanning
   - `sat_dasf_mapping.csv`: Mapping between SAT checks and DASF (Databricks Account Security Framework)

5. **Infrastructure** (`terraform/`)
   - `aws/`, `azure/`, `gcp/`: Cloud-specific Terraform modules
   - `common/`: Shared Terraform resources (jobs, SQL warehouses, secrets)
   - Each contains provider configs, secrets management, and variable definitions

### Authentication Architecture

**Multi-cloud OAuth flow:**
- AWS/GCP: Service principal OAuth via Databricks Accounts API
- Azure: MSAL (Microsoft Authentication Library) for Azure AD tokens + Databricks OAuth
- Authentication handled in `SatDBClient._update_token_master()` method
- Tokens refresh automatically per API call based on endpoint type (workspace vs accounts vs Azure management)

### Data Flow

1. **Initialization:** Driver notebook loads configuration from `workspace_configs.csv` and Unity Catalog tables
2. **Workspace discovery:** Queries enabled workspaces (`analysis_enabled=True`)
3. **Parallel execution:** Each workspace analyzed in parallel (optional via `use_parallel_runs` flag)
4. **Client invocation:** Specialized client packages called to fetch API data
5. **Analysis:** Security checks evaluated against fetched data using rules from `security_best_practices.csv`
6. **Storage:** Results written to Unity Catalog schema (default: `security_analysis`)
7. **Visualization:** Lakeview dashboards display findings

### Serverless vs Classic Compute

- **Serverless:** Limited to analyzing current workspace only
- **Classic cluster:** Can analyze all configured workspaces across the account
- Notebooks automatically detect compute type via `is_serverless` flag

## Code Patterns

### Client Package Pattern

All client packages follow this structure:
```python
from core.dbclient import SatDBClient

class ExampleClient(SatDBClient):
    def __init__(self, configs):
        super().__init__(configs)

    def get_example_list(self):
        # Uses inherited methods: self.get(), self.post(), etc.
        endpoint = "/api/2.0/example/list"
        return self.get(endpoint)
```

### Notebook Integration Pattern

Notebooks use magic commands to import shared code:
```python
# %run ./Includes/install_sat_sdk
# %run ./Utils/initialize
# %run ./Utils/common
```

### Bootstrap Pattern

The `bootstrap()` function in `common.py` is the core data collection pattern:
```python
bootstrap(viewname, func, **kwargs)
```

- Executes a client function (e.g., `acct_client.get_workspace_list`)
- Converts results to JSON
- Creates DataFrame from JSON
- Saves as Delta table with column mapping enabled
- Used in `accounts_bootstrap.py` and `workspace_bootstrap.py`

### Security Check Pattern

Security checks in `workspace_analysis.py` follow this pattern:
```python
check_id = '37'
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def rule_function(df):
    if df is not None and not isEmpty(df):
        return (check_id, 0, {})  # Pass
    else:
        return (check_id, 1, {'workspaceId': workspace_id})  # Violation

if enabled:
    sql = "SELECT * FROM table WHERE condition"
    sqlctrl(workspace_id, sql, rule_function)
```

Rule functions return: `(check_id, score, additional_details_dict)`
- Score: 0 = pass, 1+ = violation count
- Details: Dict with context (resource names, configurations, etc.)

### Error Handling

- HTTP errors 401/403 raise exceptions immediately (defined in `SatDBClient.http_error_codes`)
- All clients use centralized logger from `LoggingUtils`
- Verbosity controlled via `json_['verbosity']` configuration
- Bootstrap failures are logged but don't crash pipeline

## Security Checks

SAT implements 116+ security checks across multiple categories. Checks are defined in `configs/security_best_practices.csv` and implemented in `notebooks/Includes/workspace_analysis.py` and `notebooks/Includes/workspace_settings.py`.

### Check Categories

- **Data Protection (DP)**: Encryption, secrets management, data exfiltration prevention
- **Governance (GOV)**: Audit logs, cluster policies, runtime versions, Unity Catalog
- **Identity & Access (IA)**: SSO, SCIM, tokens, service principals
- **Network Security (NS)**: IP access lists, private connectivity, serverless egress controls
- **Informational (INFO)**: Configuration recommendations and visibility checks

### Adding New Security Checks

1. Add check definition to `configs/security_best_practices.csv`
2. Implement check logic in `notebooks/Includes/workspace_analysis.py`:
   - Create SQL query against intermediate tables
   - Define rule function that evaluates results
   - Call `sqlctrl(workspace_id, sql, rule_function)`
3. Test on sample workspace
4. Update documentation

---

## New Check Pre-Flight Checklist

**CRITICAL: Run ALL steps below before committing any new security check. Skipping any step has caused production bugs.**

### Step 1 — Test the live API first (MANDATORY)

Before writing any SQL or bootstrap code, use the Databricks MCP tools to call the actual API and inspect the real JSON shape:

```python
# For workspace settings (Settings v2 API)
mcp__databricks__get_setting(
    workspace_host="<workspace>.cloud.databricks.com",
    setting_name="<setting_name>"   # e.g. "sql_results_download", "disable_legacy_dbfs"
)

# For other APIs
mcp__databricks__get_workspace_config(workspace_host="...")
mcp__databricks__list_clusters(workspace_host="...")
# etc.
```

Write down the **exact top-level key names** in the response before proceeding.

### Step 2 — Settings v2 API column name rule (MANDATORY for Settings v2 checks)

**Always call the live API first (Step 1) and inspect the exact top-level key.**

Settings v2 APIs do NOT all use the same key name for their value. Each setting
uses its OWN key name as the top-level wrapper. Examples:

| Setting | Top-level key | SQL column |
|---------|--------------|------------|
| `sql_results_download` | `boolean_val` | `boolean_val.value` |
| `disable_legacy_dbfs` | `disable_legacy_dbfs` | `disable_legacy_dbfs.value` |
| `automatic_cluster_update` | `automatic_cluster_update_workspace` | `automatic_cluster_update_workspace.enabled` |
| `restrict_workspace_admins` | `restrict_workspace_admins` | `restrict_workspace_admins.status` |

The `bootstrap()` function preserves the top-level JSON key as the column name.
`sql_results_download` is the **only** known setting that uses `boolean_val` instead
of its own name.

```python
# CORRECT for sql_results_download (uniquely uses boolean_val)
WHERE boolean_val.value = false

# CORRECT for disable_legacy_dbfs (uses its own name)
WHERE disable_legacy_dbfs.value = true

# WRONG — never guess; always check the live API response
WHERE sql_results_download.value = true
```

### Step 3 — Validate doc URLs in the CSV (MANDATORY)

After adding a row to `configs/security_best_practices.csv`, verify that every URL in `aws_doc_url`, `azure_doc_url`, and `gcp_doc_url` returns HTTP 200. Broken URLs (404s) have been committed before and require follow-up fixes.

Run this check:
```bash
python3 - <<'EOF'
import csv, urllib.request, urllib.error

errors = []
with open("configs/security_best_practices.csv") as f:
    for i, row in enumerate(csv.DictReader(f), start=2):
        for col in ("aws_doc_url", "azure_doc_url", "gcp_doc_url"):
            url = row.get(col, "").strip()
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as e:
                errors.append(f"  Row {i} [{row['check_id']}] {col}: HTTP {e.code} — {url}")
            except Exception as e:
                errors.append(f"  Row {i} [{row['check_id']}] {col}: {e} — {url}")

if errors:
    print("BROKEN URLs — fix before committing:")
    print("\n".join(errors))
else:
    print("OK — all URLs reachable")
EOF
```

**If any URL returns an error, fix it before committing.**

### Step 4 — Run the standard pre-commit checks

```bash
# Uniqueness check (id + check_id)
python3 - <<'EOF'
import csv, sys
ids, check_ids = {}, {}
errors = []
with open("configs/security_best_practices.csv") as f:
    for i, row in enumerate(csv.DictReader(f), start=2):
        if row["id"] in ids:
            errors.append(f"  Duplicate id={row['id']} on rows {ids[row['id']]} and {i}")
        else:
            ids[row["id"]] = i
        if row["check_id"] in check_ids:
            errors.append(f"  Duplicate check_id={row['check_id']} on rows {check_ids[row['check_id']]} and {i}")
        else:
            check_ids[row["check_id"]] = i
if errors:
    print("UNIQUENESS VIOLATIONS:"); print("\n".join(errors)); sys.exit(1)
else:
    print(f"OK — {len(ids)} rows, all unique")
EOF

# Typo check
git diff --cached --name-only | xargs codespell
```

### Lessons Learned (from DP-10 / DP-11 bugs)

| Bug | Root cause | Fix |
|-----|-----------|-----|
| DP-11 runtime SQL error: `cannot find field sql_results_download.value` | Assumed column name mirrors setting name; `sql_results_download` API uniquely uses `boolean_val` as the top-level key | Always inspect live API response before writing SQL; use the exact top-level key from the response, never guess |
| DP-10/11 broken doc URLs | URLs added without verification | Run URL check script (Step 3) before every commit |

---

## Testing

Tests are in `src/securityanalysistoolproject/tests/`. The test framework uses pytest with a shared conftest fixture.

**Note:** `conftest.py` has hardcoded paths that need updating for local development:
```python
configFilePath = '/Users/ramdas.murali/_dev_stuff/config.txt'
```

### Databricks MCP Tools for Testing

For rapid iteration and testing when building new security checks, use the **Databricks MCP (Model Context Protocol) tools**. These tools provide direct access to Databricks APIs for exploring data structures, validating queries, and testing check logic without running full SAT analyses.

**See:** [`docs/databricks_mcp_tools.md`](docs/databricks_mcp_tools.md) for complete tool reference with 43 available tools across:
- Account & workspace management
- Unity Catalog operations
- Compute resources (clusters, policies, pools)
- Jobs & workflows
- SQL warehouses
- Network & security settings
- Workspace settings (Settings v2 API)
- Git repos & notebooks
- MLflow & model serving

**Quick example:**
```python
# Test a new security check by retrieving live workspace settings
get_setting(
    workspace_host="workspace.cloud.databricks.com",
    setting_name="enhanced_security_monitoring"
)
```

## Versioning

This project follows Semantic Versioning (MAJOR.MINOR.PATCH):
- **MAJOR:** Incompatible changes (deployment method, breaking API changes)
- **MINOR:** New features/checks (backward-compatible)
- **PATCH:** Bug fixes, documentation updates

See `VERSIONING.md` for detailed branching strategy.

## Git Workflow Rules

**CRITICAL: Feature branches must be created from release branches, NEVER from main or other feature branches**

### Correct Workflow

1. **Always branch from release branches**: Feature branches must be created from `release/X.X.X` branches (e.g., `release/0.6.0`)
2. **Never branch from main**: Main branch is protected and should never be used as a source
3. **Never branch from other feature branches**: Feature branches should not be created from other feature branches
4. **Branch naming**: Use descriptive names like `SFE-XXXX_feature_name` or `bugfix/description`

### Example Workflow

```bash
# First, check out the target release branch
git checkout release/0.6.0

# Create your feature branch from the release branch
git checkout -b SFE-1234_new_feature

# Make changes, commit, push
git add .
git commit -m "feat: description"
git push -u origin SFE-1234_new_feature
```

### Wrong Workflows (DO NOT DO)

```bash
# ❌ WRONG: Branching from main
git checkout main
git checkout -b SFE-1234_new_feature  # Never do this!

# ❌ WRONG: Branching from another feature branch
git checkout SFE-4426_cluster_config_secrets
git checkout -b SFE-3862_SEG  # Never do this!
```

### Key Points

- **Release branches** (like `release/0.6.0`) are the source for all feature work
- Feature branches eventually merge back into their source release branch
- This keeps release branches clean and ensures proper version control
- Main branch remains protected from direct changes

## Schema Comment Sync Rule

**CRITICAL: Whenever a table or column is added, removed, or renamed, you MUST update `notebooks/Utils/common.py` → `apply_schema_comments()` to keep comments in sync.**

### What to check

| Change | Required action |
|--------|----------------|
| New table added to the schema | Add `_set_table_comment(schema, "<table>", "...")` block in `apply_schema_comments()` |
| Table removed | Remove the corresponding `_set_table_comment` and `_set_column_comments` block |
| New column added to a table | Add the column key + description to the relevant `_set_column_comments(schema, "<table>", {...})` dict |
| Column removed | Remove the column entry from the `_set_column_comments` dict |
| Column or table renamed | Update the name in both the schema definition and in `apply_schema_comments()` |

### How to verify

Before committing any schema change, check that every table and column touched has a matching entry in `apply_schema_comments()`:

```bash
# Quick check — search for the table/column name in apply_schema_comments
grep -n "<table_or_column_name>" notebooks/Utils/common.py
```

If a comment is missing, add it before committing. Do not leave undocumented tables or columns.

---

## security_best_practices.csv Uniqueness Validation

**CRITICAL: Before committing any change to `configs/security_best_practices.csv`, validate that `id` and `check_id` are both unique across all rows. Do NOT commit if duplicates are found.**

### Run this check every time the CSV is modified

```bash
python3 - <<'EOF'
import csv, sys
ids, check_ids = {}, {}
errors = []
with open("configs/security_best_practices.csv") as f:
    for i, row in enumerate(csv.DictReader(f), start=2):  # row 1 = header
        if row["id"] in ids:
            errors.append(f"  Duplicate id={row['id']} on rows {ids[row['id']]} and {i}")
        else:
            ids[row["id"]] = i
        if row["check_id"] in check_ids:
            errors.append(f"  Duplicate check_id={row['check_id']} on rows {check_ids[row['check_id']]} and {i}")
        else:
            check_ids[row["check_id"]] = i
if errors:
    print("UNIQUENESS VIOLATIONS — fix before committing:")
    print("\n".join(errors))
    sys.exit(1)
else:
    print(f"OK — {len(ids)} rows, id and check_id are both unique")
EOF
```

### Rules

1. **Run on every CSV edit** — adding, removing, or modifying any row.
2. **If duplicates are found, stop.** Report the conflicting rows to the user and do NOT commit.
3. **Fix the duplicates first**, then re-run the check before committing.
4. The `id` column is a unique integer; the `check_id` column is a unique human-readable code (e.g. `DP-1`, `GOV-5`). Both must be unique independently.

---

## Pre-Commit Typo Check

**CRITICAL: Always check for typos before committing. Do NOT commit if typos are found.**

Before every `git commit`, scan all staged files for typos using `codespell`:

```bash
git diff --cached --name-only | xargs codespell
```

If `codespell` is not installed: `pip install codespell`

### Rules

1. **Run the check on every commit** — no exceptions, even for small or "obvious" changes.
2. **If typos are found, stop.** Report the typos to the user and do NOT run `git commit`.
3. **Fix all reported typos first**, then re-stage and re-run the check before committing.
4. Only proceed with the commit once `codespell` exits cleanly with no findings.

### False positives

If `codespell` flags a word that is intentionally spelled that way (e.g. a proper noun, domain term, or code identifier), add it to `.codespell-ignore` at the repo root:

```
# .codespell-ignore
someword
anotherterm
```

Then re-run: `git diff --cached --name-only | xargs codespell --ignore-words=.codespell-ignore`

---

## Communicating Changes

When summarizing changes made during a session, always include:

1. **Git Status**: Explicitly state whether changes have been:
   - Committed and pushed to remote
   - Committed but not pushed
   - Modified but not committed

2. **Commit Information** (if changes were committed):
   - Commit hash (short form is acceptable, e.g., `77198e2`)
   - Branch name (e.g., `SFE-3862_SEG`)
   - Commit message summary

3. **Files Changed**: List the files that were modified with brief description of changes

### Example Summary Format

```
✅ Changes committed and pushed successfully.

Commit: 77198e2
Branch: SFE-3862_SEG
Message: fix: escape single quotes in JSON data for SQL INSERT statements

Files changed:
- notebooks/Utils/common.py (6 insertions, 2 deletions)
  - Added quote escaping in insertIntoControlTable()
  - Added quote escaping in insertIntoInfoTable()
```

This ensures users have complete visibility into what changes were made and whether they need to pull updates in their workspace.

## Cloud-Specific Notes

### AWS
- Uses service principal with client ID/secret from AWS accounts console
- Accounts URL: `https://accounts.cloud.databricks.{domain}`

### Azure
- Requires 4 credentials: `tenant_id`, `subscription_id`, `client_id`, `client_secret`
- Two token endpoints: Databricks Accounts API + Azure Management API
- Accounts URL: `https://accounts.azuredatabricks.{domain}`
- Management URL: `https://management.azure.com`

### GCP
- Uses service principal with client ID/secret
- Accounts URL: `https://accounts.gcp.databricks.{domain}`

## Important Implementation Details

1. **Secret Storage:** All credentials stored in Databricks secret scope `sat_scope` during DABS installation
2. **Workspace filtering:** Use `serverless_filter` SQL clause when running on serverless
3. **Pagination:** Controlled by `maxpages` and `timebetweencalls` config parameters
4. **Token refresh:** Tokens regenerated per API call in `_update_token_master()` based on endpoint routing
5. **Python version:** Requires Python 3.9+ (enforced in `install.sh`)
6. **Intermediate schema:** Ephemeral storage layer for raw API responses, dropped at end of driver run
7. **Run tracking:** Each execution gets unique `runID` from `run_number_table` for correlation across tables
8. **SQL escaping:** `insertIntoControlTable()` and `insertIntoInfoTable()` escape single quotes in JSON data before SQL INSERT

## BrickHound Integration

BrickHound provides graph-based permissions analysis within SAT, complementing SAT's configuration security checks.

### Location and Structure

**Notebooks**: `/notebooks/brickhound/`
- `00_config.py` - Configuration (reads from sat_scope)
- `00_analysis_common.py` - Shared utilities
- `01_data_collection.py` - Main collector (2694 lines)
- `02-05_*.py` - Interactive analysis notebooks
- `install_brickhound_sdk.py` - SDK installation

**Python SDK**: `/src/brickhound/` (separate from SAT SDK)
- `collector/` - Data collection engine
- `graph/` - Graph building and analysis
- `utils/` - Configuration and API client

**Web App**: `/app/brickhound/`
- `working_app.py` - Gradio UI (350KB)
- `app.yaml` - Databricks Apps config

**Terraform**: `/terraform/common/brickhound_job.tf`
- Job definition for weekly data collection

### Architecture

**Credentials**: Uses SAT's `sat_scope` secret scope
- `account-console-id` → Account UUID
- `client-id` → Service Principal Application ID  
- `client-secret` → Service Principal OAuth Secret
- `analysis_schema_name` → Unity Catalog schema (catalog.schema format)

**Storage**: Same Unity Catalog schema as SAT
- Tables: `brickhound_vertices`, `brickhound_edges`, `brickhound_collection_metadata`
- Namespaced with `brickhound_` prefix to avoid conflicts

**Job**: Separate weekly job (Sunday 2 AM)
- Independent from SAT driver (Mon/Wed/Fri)
- Longer runtime (up to 4 hours for large accounts)

### SDK Pattern

BrickHound SDK is kept separate from SAT SDK to avoid dependency conflicts:

```python
# Install SDK (in notebooks)
%run ./install_brickhound_sdk

# Import components
from brickhound.collector.core import DatabricksCollector
from brickhound.graph.analyzer import GraphAnalyzer
from brickhound.graph.permissions_resolver import PermissionsResolver
```

### Data Model

**Vertices Table** (50+ node types):
- Identity: User, Group, ServicePrincipal
- Data: Catalog, Schema, Table, Volume
- Compute: Cluster, SQLWarehouse
- Security: SecretScope, Token

**Edges Table** (60+ relationship types):
- Permissions: CanUse, CanRead, CanWrite, CanManage
- UC Grants: Select, Modify, AllPrivileges, Usage
- Membership: MemberOf, Contains
- Ownership: Owns, CreatedBy

### Testing with MCP Tools

Use Databricks MCP tools for rapid testing:

```python
# Verify tables exist
mcp__databricks__list_tables(
    catalog_name="main",
    schema_name="security_analysis"
)

# Check data
mcp__databricks__query_table(
    warehouse_id="...",
    sql_query="SELECT COUNT(*) FROM main.security_analysis.brickhound_vertices",
    max_rows=1
)

# Verify job configuration
mcp__databricks__get_job_details(
    workspace_host="...",
    job_id="<brickhound-job-id>"
)
```

### Key Design Decisions

1. **Namespaced Tables**: `brickhound_` prefix keeps everything in SAT's schema while avoiding conflicts
2. **Reuse sat_scope**: Simplifies credential management, no new secrets needed
3. **Separate Job**: Allows independent execution, different schedule (weekly vs. 3x/week)
4. **Keep SDK Separate**: Avoids dependency conflicts (databricks-sdk vs. requests/msal)
5. **Complementary Analysis**: BrickHound (permissions) + SAT (config) = comprehensive security

### Integration Points

1. **Configuration**: BrickHound reads `analysis_schema_name` from sat_scope in `00_config.py`
2. **Authentication**: Uses same service principal as SAT (client-id/client-secret)
3. **Storage**: Writes to SAT's Unity Catalog schema
4. **Deployment**: Included in SAT's Terraform deployment (brickhound_job.tf)
5. **Documentation**: Linked from main README.md

### Documentation Files

- `docs/BRICKHOUND_INTEGRATION.md` - Integration guide
- `docs/brickhound_README.md` - Original BrickHound documentation
- `docs/brickhound_PERMISSIONS.md` - Required permissions
- `notebooks/brickhound/README.md` - Quick start guide

### Comparison: SAT vs. BrickHound

| Feature | SAT | BrickHound |
|---------|-----|------------|
| **Focus** | Configuration security | Permissions analysis |
| **Checks** | 116+ security checks | Graph queries |
| **Data Model** | Flat tables | Graph (vertices/edges) |
| **Analysis** | Automated pass/fail | Interactive exploration |
| **Schedule** | Mon/Wed/Fri | Weekly (Sunday) |
| **Output** | Violations, scores | Permission paths, matrices |
| **Use Case** | "Is the config secure?" | "Who can access what?" |

Together they provide comprehensive Databricks security analysis.
