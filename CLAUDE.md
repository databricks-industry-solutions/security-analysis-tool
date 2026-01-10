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

**SDK version:** The SDK version is maintained in `src/securityanalysistoolproject/setup.py` (currently `__version__ = "0.0.124"`)

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
   - Each contains provider configs, secrets management, and variable definitions
   - See `terraform/aws/TERRAFORM_AWS.md` for AWS-specific guidance

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

### Error Handling

- HTTP errors 401/403 raise exceptions immediately (defined in `SatDBClient.http_error_codes`)
- All clients use centralized logger from `LoggingUtils`
- Verbosity controlled via `json_['verbosity']` configuration

## Security Checks

SAT implements 116 security checks across multiple categories. Checks are defined in `configs/security_best_practices.csv` and implemented in `notebooks/Includes/workspace_analysis.py` and `notebooks/Includes/workspace_settings.py`.

### Check Categories

- **Data Protection (DP)**: Encryption, secrets management, data exfiltration prevention
- **Governance (GOV)**: Audit logs, cluster policies, runtime versions, Unity Catalog
- **Identity & Access (IA)**: SSO, SCIM, tokens, service principals
- **Network Security (NS)**: IP access lists, private connectivity, serverless egress controls
- **Informational (INFO)**: Configuration recommendations and visibility checks

### Serverless Egress Control Checks (SFE-3862)

Six new checks (NS-9 through INFO-18) added to assess serverless compute network security:

**NS-9: Serverless Workspaces Have Network Policies**
- **Check ID**: 111 | **Severity**: High
- **Description**: Validates that workspaces with serverless compute have network policies configured
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Configure network policies to control outbound connections and prevent data exfiltration

**NS-10: Network Policies Use Restricted Access Mode**
- **Check ID**: 112 | **Severity**: High
- **Description**: Ensures policies use restricted access mode instead of full access
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Use restricted mode with explicit allow-lists for required destinations

**NS-11: Network Policies Are Enforced**
- **Check ID**: 113 | **Severity**: Medium
- **Description**: Validates policies are in enforced mode, not dry-run
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Move from dry-run to enforced mode after validation

**NS-12: Network Policies Have Allow-Lists**
- **Check ID**: 114 | **Severity**: Medium
- **Description**: Checks that restricted policies have explicit destination allow-lists
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Define allow-lists for cloud storage, external APIs, and required services

**NS-13: Serverless SQL Warehouses Have Policy Coverage**
- **Check ID**: 115 | **Severity**: High
- **Description**: Ensures serverless SQL warehouses are in workspaces with network policies
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Apply network policies to workspaces running serverless SQL warehouses

**INFO-18: Network Policy Assignment Tracking**
- **Check ID**: 116 | **Severity**: Low (Informational)
- **Description**: Identifies workspaces using default vs custom network policies
- **Cloud Support**: AWS Enterprise, Azure Premium, GCP Enterprise (Public Preview)
- **Recommendation**: Consider custom policies for workspaces with specific security requirements

### Implementation Pattern

Serverless egress control checks leverage existing data collection:
- **API**: `GET /accounts/{account_id}/network-policies` (already implemented in `accounts_settings.py`)
- **Data**: `account_networkpolicies` table (collected during account bootstrap)
- **Analysis**: SQL queries in `workspace_analysis.py` evaluate policy configuration
- **Results**: Violations written to `security_checks` table for dashboard visualization

## Testing

Tests are in `src/securityanalysistoolproject/tests/`. The test framework uses pytest with a shared conftest fixture.

**Note:** `conftest.py` has hardcoded paths that need updating for local development:
```python
configFilePath = '/Users/ramdas.murali/_dev_stuff/config.txt'
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

1. **Always branch from release branches**: Feature branches must be created from `release/X.X.X` branches (e.g., `release/0.0.6`)
2. **Never branch from main**: Main branch is protected and should never be used as a source
3. **Never branch from other feature branches**: Feature branches should not be created from other feature branches
4. **Branch naming**: Use descriptive names like `SFE-XXXX_feature_name` or `bugfix/description`

### Example Workflow

```bash
# First, check out the target release branch
git checkout release/0.0.6

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

- **Release branches** (like `release/0.0.6`) are the source for all feature work
- Feature branches eventually merge back into their source release branch
- This keeps release branches clean and ensures proper version control
- Main branch remains protected from direct changes

## Communicating Changes

When summarizing changes made during a session, Claude must always include:

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
