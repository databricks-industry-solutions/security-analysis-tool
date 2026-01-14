# Databricks MCP Tools Reference

This document lists all available Databricks MCP (Model Context Protocol) tools for testing and building SAT features.

## Overview

The Databricks MCP server provides **51 tools** organized into 11 categories for interacting with Databricks workspaces and accounts.

**Important:** These tools are **development and testing utilities** used during SAT feature development. They are NOT integrated into the SAT codebase or used at runtime. Instead, they enable rapid prototyping, exploration, and validation during the planning and development phases.

### Tool Breakdown
- **35 Read Operations** - Query and retrieve data from Databricks resources (includes SQL query execution)
- **16 Write Operations** - Manage compute resources (clusters, jobs, SQL warehouses) with preview/execute safety pattern

### Test Status
✅ **51 tools available** (January 2026)

**Read Operations:** 33/35 tools fully functional
- ⚠️ 2 tools unavailable: `list_network_policies`, `get_workspace_network_config` (network_policy API not in SDK)
- ✨ **New:** 3 job debugging tools added (get_job_run_output, get_job_run_details, get_cluster_events)
- ✨ **New:** SQL query execution tool added (query_table) - Query Unity Catalog tables and SAT results

**Write Operations:** 16/16 tools fully functional
- All write operations use preview/execute safety pattern with 5-minute confirmation tokens

### Development Workflow

These MCP tools are used via Claude Code to:
1. **Plan** - Explore APIs and data structures before implementing
2. **Develop** - Test queries and logic rapidly without running full SAT
3. **Validate** - Verify implementations against live workspace data
4. **Debug** - Investigate issues and inspect configurations

Once validated, the logic is implemented in SAT using the standard SDK client packages (`src/securityanalysistoolproject/clientpkgs/`).

## Tool Categories

### 1. Account & Workspace Management (5 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_workspaces` | List all workspaces in the Databricks account | None |
| `get_workspace_details` | Get detailed information about a specific workspace | `workspace_id` |
| `list_workspace_users` | List all users in a workspace | `workspace_host` (optional) |
| `list_service_principals` | List all service principals in the account | None |
| `get_account_info` | Get account details and metadata | None |

### 2. Unity Catalog (4 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_metastores` | List all Unity Catalog metastores | None |
| `list_catalogs` | List all catalogs in Unity Catalog | `workspace_host` (optional) |
| `list_schemas` | List schemas in a specific catalog | `catalog_name` |
| `list_tables` | List tables in a schema | `catalog_name`, `schema_name` |

### 3. Compute Resources (4 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_clusters` | List all clusters in a workspace | `workspace_host` (optional) |
| `get_cluster_details` | Get detailed configuration for a specific cluster | `cluster_id` |
| `list_cluster_policies` | List all cluster policies in a workspace | `workspace_host` (optional) |
| `list_instance_pools` | List all instance pools in a workspace | `workspace_host` (optional) |

### 4. Jobs & Workflows (6 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_jobs` | List all jobs in a workspace | `workspace_host` (optional) |
| `get_job_details` | Get detailed configuration for a specific job | `job_id` |
| `get_job_runs` | Get job run history | `job_id`, `limit` (optional) |
| `get_job_run_output` | ✨ Get job run output including notebook results, errors, and logs | `run_id` |
| `get_job_run_details` | ✨ Get comprehensive run details with tasks, cluster info, and timeline | `run_id` |
| `get_cluster_events` | ✨ Get cluster event logs for debugging | `cluster_id`, `limit` (optional) |

**New Debugging Tools:** The three tools marked with ✨ are specifically designed for debugging failed job runs and investigating issues with SAT analyses.

### 5. SQL Warehouses (3 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_sql_warehouses` | List all SQL warehouses in a workspace | `workspace_host` (optional) |
| `get_warehouse_details` | Get SQL warehouse configuration | `warehouse_id` |
| `query_table` | Execute read-only SQL queries (SELECT only) and return formatted results | `warehouse_id`, `sql_query`, `max_rows` (optional, default 100, max 1000) |

**Note:** The `query_table` tool enables querying Unity Catalog tables, Delta tables, and any SQL-accessible data. Write operations (INSERT, UPDATE, DELETE, etc.) are blocked for safety.

### 6. Network & Security (4 tools)

| Tool | Description | Required Parameters | Status |
|------|-------------|-------------------|--------|
| `list_ip_access_lists` | List IP access lists for a workspace | `workspace_host` (optional) | ✅ Working |
| `get_workspace_config` | Get workspace configuration settings (legacy workspace-conf API) | `keys` (optional) | ✅ Working |
| `list_settings_metadata` | List all available workspace settings with metadata (Settings v2 API) | `workspace_host` (optional) | ✅ Working |
| ~~`list_network_policies`~~ | ~~List account-level network policies~~ | None | ⚠️ Not available in SDK |
| ~~`get_workspace_network_config`~~ | ~~Get network configuration for workspace~~ | `workspace_id` | ⚠️ Not available in SDK |

**Note:** Network policy tools are not available in the current Databricks SDK version.

### 7. Secrets & Authentication (2 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_tokens` | List personal access tokens in a workspace | `workspace_host` (optional) |
| `list_secrets` | List secret scopes in a workspace | `workspace_host` (optional) |

### 8. Workspace Settings v2 API (1 tool)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `get_setting` | Get a specific workspace setting value by name | `setting_name` |

#### Available Settings

The following 16 settings are available via `get_setting`:

1. `aibi_dashboard_embedding_access_policy` - AI/BI dashboard embedding access control
2. `aibi_dashboard_embedding_approved_domains` - Approved domains for dashboard embedding
3. `automatic_cluster_update` - Automatic cluster update configuration
4. `compliance_security_profile` - Compliance security profile enablement
5. `dashboard_email_subscriptions` - Dashboard email subscription settings
6. `default_namespace` - Default namespace for the workspace
7. `default_warehouse_id` - Default SQL warehouse ID
8. `disable_legacy_access` - Disable legacy access controls
9. `disable_legacy_dbfs` - Disable legacy DBFS root access
10. `enable_export_notebook` - Enable notebook export functionality
11. `enable_notebook_table_clipboard` - Enable notebook table clipboard
12. `enable_results_downloading` - Enable results downloading
13. `enhanced_security_monitoring` - Enhanced Security Monitoring (ESM) enablement
14. `llm_proxy_partner_powered_workspace` - LLM proxy partner powered workspace
15. `restrict_workspace_admins` - Restrict workspace admin capabilities
16. `sql_results_download` - SQL results download configuration

### 9. Git & Repos (2 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_repos` | List all Git repos in a workspace | `workspace_host` (optional) |
| `get_repo_details` | Get Git repo configuration | `repo_id` |

### 10. Notebooks & Files (2 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_notebooks` | List notebooks in a workspace path | `path` (e.g., `/Users/user@example.com`) |
| `export_notebook` | Export notebook content | `path`, `format` (optional: SOURCE/HTML/JUPYTER/DBC) |

### 11. MLflow & Model Serving (3 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `list_experiments` | List all MLflow experiments in a workspace | `workspace_host` (optional) |
| `list_models` | List all registered models in a workspace | `workspace_host` (optional) |
| `list_model_serving_endpoints` | List all model serving endpoints in a workspace | `workspace_host` (optional) |

---

## Write Operations (16 tools)

All write operations use a **preview/execute safety pattern** to prevent accidental changes to production resources.

### Safety Pattern

1. **Preview** - Shows what will happen without making changes
2. **Confirmation Token** - Generated token valid for 5 minutes
3. **Execute** - Performs the operation using the token

This two-step process ensures you always review the impact before executing changes.

### 12. Cluster Management (6 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `preview_start_cluster` | Preview starting a cluster | `cluster_id` |
| `execute_start_cluster` | Execute starting a cluster | `confirmation_token` |
| `preview_stop_cluster` | Preview stopping a cluster | `cluster_id` |
| `execute_stop_cluster` | Execute stopping a cluster | `confirmation_token` |
| `preview_restart_cluster` | Preview restarting a cluster | `cluster_id` |
| `execute_restart_cluster` | Execute restarting a cluster | `confirmation_token` |

**Example:**
```python
# Step 1: Preview the operation
preview_start_cluster(cluster_id="1120-194905-42pkflsy")

# Output shows cluster details and generates token:
# 🔐 Confirmation Token: start_cluster:1120-194905-42pkflsy:1768231321:d6de8b6b

# Step 2: Execute with confirmation token
execute_start_cluster(
    confirmation_token="start_cluster:1120-194905-42pkflsy:1768231321:d6de8b6b"
)
```

### 13. Job Management (6 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `preview_run_job` | Preview running a job | `job_id`, `notebook_params` (optional), `jar_params` (optional), `python_params` (optional) |
| `execute_run_job` | Execute running a job | `confirmation_token` |
| `preview_trigger_job` | Alias for `preview_run_job` | Same as `preview_run_job` |
| `execute_trigger_job` | Alias for `execute_run_job` | `confirmation_token` |
| `preview_cancel_job_run` | Preview canceling a job run | `run_id` |
| `execute_cancel_job_run` | Execute canceling a job run | `confirmation_token` |

**Example:**
```python
# Trigger a job run with parameters
preview_run_job(
    job_id="438463735912275",
    notebook_params={"param1": "value1"}
)

# Execute using the generated token
execute_run_job(confirmation_token="run_job:438463735912275:...")

# Cancel a running job
preview_cancel_job_run(run_id="589585806190425")
execute_cancel_job_run(confirmation_token="cancel_job_run:589585806190425:...")
```

### 14. SQL Warehouse Management (4 tools)

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `preview_start_warehouse` | Preview starting a SQL warehouse | `warehouse_id` |
| `execute_start_warehouse` | Execute starting a SQL warehouse | `confirmation_token` |
| `preview_stop_warehouse` | Preview stopping a SQL warehouse | `warehouse_id` |
| `execute_stop_warehouse` | Execute stopping a SQL warehouse | `confirmation_token` |

**Example:**
```python
# Start a SQL warehouse
preview_start_warehouse(warehouse_id="782228d75bf63e5c")

# Output shows warehouse config and costs
# 🔐 Confirmation Token: start_warehouse:782228d75bf63e5c:...

execute_start_warehouse(confirmation_token="start_warehouse:782228d75bf63e5c:...")
```

### Write Operation Safety Features

- **State Validation** - Prevents invalid operations (e.g., starting a running cluster)
- **Time-Limited Tokens** - Confirmation tokens expire after 5 minutes
- **Resource Verification** - Validates resource exists before execution
- **Clear Preview** - Shows exactly what will happen before changes
- **Cost Awareness** - Preview displays compute cost implications

---

## Common Parameters

### `workspace_host`
- **Format:** `workspace-name.cloud.databricks.com` (without `https://`)
- **Example:** `sfe-plain.cloud.databricks.com`
- **Usage:** Most workspace-scoped tools accept this optional parameter
- **Note:** Account-level tools (like `list_workspaces`, `get_account_info`) don't require this parameter

## Usage Examples

### Account Management
```python
# List all workspaces in the account
list_workspaces()

# Get details for a specific workspace
get_workspace_details(workspace_id="1425658296462059")

# List users in a workspace
list_workspace_users(workspace_host="sfe-plain.cloud.databricks.com")
```

### Workspace Settings
```python
# List all available settings
list_settings_metadata(workspace_host="sfe-plain.cloud.databricks.com")

# Get a specific setting value
get_setting(
    workspace_host="sfe-plain.cloud.databricks.com",
    setting_name="automatic_cluster_update"
)

# Get compliance security profile status
get_setting(
    workspace_host="sfe-plain.cloud.databricks.com",
    setting_name="compliance_security_profile"
)
```

### Unity Catalog
```python
# List all catalogs
list_catalogs(workspace_host="sfe-plain.cloud.databricks.com")

# List schemas in a catalog
list_schemas(
    workspace_host="sfe-plain.cloud.databricks.com",
    catalog_name="main"
)

# List tables in a schema
list_tables(
    workspace_host="sfe-plain.cloud.databricks.com",
    catalog_name="main",
    schema_name="default"
)
```

### Compute Resources
```python
# List all clusters
list_clusters(workspace_host="sfe-plain.cloud.databricks.com")

# Get cluster details
get_cluster_details(
    workspace_host="sfe-plain.cloud.databricks.com",
    cluster_id="1234-567890-abc123"
)

# List cluster policies
list_cluster_policies(workspace_host="sfe-plain.cloud.databricks.com")
```

### Jobs & Workflows
```python
# List all jobs
list_jobs(workspace_host="sfe-plain.cloud.databricks.com")

# Get job details
get_job_details(
    workspace_host="sfe-plain.cloud.databricks.com",
    job_id="123456"
)

# Get job run history (last 10 runs)
get_job_runs(
    workspace_host="sfe-plain.cloud.databricks.com",
    job_id="123456",
    limit=10
)

# ✨ NEW: Get complete output from a job run (including errors)
get_job_run_output(run_id="589585806190425")
# Returns: notebook output, errors, stack traces, logs

# ✨ NEW: Get comprehensive run details
get_job_run_details(run_id="589585806190425")
# Returns: timing breakdown, task details, cluster info, duration

# ✨ NEW: Get cluster event logs for debugging
get_cluster_events(
    cluster_id="1120-194905-42pkflsy",
    limit=50  # optional, default 50
)
# Returns: cluster lifecycle events, errors, state transitions
```

### SQL Queries & Unity Catalog Tables
```python
# Query SAT security checks table
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="SELECT id, COUNT(*) as total_checks, SUM(score) as violations FROM arunuc.security_analysis.security_checks GROUP BY id ORDER BY id",
    max_rows=200
)

# Query specific security check results
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="SELECT * FROM arunuc.security_analysis.security_checks WHERE id = '18' AND score = 1",
    max_rows=100
)

# Query workspace-level violations
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="SELECT workspaceid, COUNT(DISTINCT id) as total_checks, SUM(score) as total_violations FROM arunuc.security_analysis.security_checks GROUP BY workspaceid ORDER BY total_violations DESC"
)

# Query any Unity Catalog table
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="SELECT * FROM catalog.schema.table WHERE condition LIMIT 100",
    max_rows=100
)
```

**Note:** The `query_table` tool is read-only (SELECT statements only). It's perfect for:
- Validating SAT security check results
- Testing SQL queries before implementing in SAT
- Exploring Unity Catalog table structures
- Debugging data quality issues
- Generating ad-hoc security reports

### Network & Security
```python
# List IP access lists
list_ip_access_lists(workspace_host="sfe-plain.cloud.databricks.com")

# Get workspace network configuration
get_workspace_network_config(workspace_id="1425658296462059")

# List secret scopes
list_secrets(workspace_host="sfe-plain.cloud.databricks.com")

# List personal access tokens
list_tokens(workspace_host="sfe-plain.cloud.databricks.com")
```

## Using MCP Tools for SAT Development

### Development-Time Usage Model

**Important:** These tools are for **local development and testing only**. They help you explore APIs and validate logic before implementing in SAT. The actual SAT implementation uses the SDK client packages in `src/securityanalysistoolproject/clientpkgs/`.

### Workflow: Building New Security Checks

**Phase 1: Planning & Exploration (Use MCP Tools)**

```python
# Via Claude Code, explore the API structure
list_settings_metadata(workspace_host="your-workspace.cloud.databricks.com")

# Retrieve and inspect specific values
result = get_setting(
    workspace_host="your-workspace.cloud.databricks.com",
    setting_name="enhanced_security_monitoring"
)

# Expected response format:
# {
#   "enhanced_security_monitoring_workspace": {
#     "is_enabled": false
#   },
#   "etag": "...",
#   "setting_name": "default"
# }
```

**Phase 2: Implementation (SAT Codebase)**

```python
# In notebooks/Includes/workspace_analysis.py
# Implement using SAT SDK client packages

check_id = '150'
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def rule_esm_enabled(df):
    # Use workspace settings client from SAT SDK
    from clientpkgs.workspace_settings_client import WorkspaceSettingsClient

    ws_client = WorkspaceSettingsClient(json_)
    setting = ws_client.get_workspace_setting("enhanced_security_monitoring")

    if setting.get("enhanced_security_monitoring_workspace", {}).get("is_enabled", False):
        return (check_id, 0, {})  # Pass
    else:
        return (check_id, 1, {"workspace_id": workspace_id})  # Fail

if enabled:
    sql = "SELECT * FROM workspace_settings_table WHERE setting_name = 'enhanced_security_monitoring'"
    sqlctrl(workspace_id, sql, rule_esm_enabled)
```

**Phase 3: Testing (Use MCP Tools)**

```python
# Via Claude Code, validate against live workspace
result = get_setting(
    workspace_host="test-workspace.cloud.databricks.com",
    setting_name="enhanced_security_monitoring"
)

# Verify the check logic matches expected behavior
print(f"ESM Enabled: {result.get('enhanced_security_monitoring_workspace', {}).get('is_enabled')}")
```

**Phase 4: Deployment**

```bash
# Build and deploy SAT with new check
cd src/securityanalysistoolproject
python setup.py sdist bdist_wheel
pip install dist/dbl-sat-sdk-<version>-py3-none-any.whl

# Run full SAT analysis
# Deploy via DABS
```

### Debugging Failed SAT Runs

The new job debugging tools are specifically designed to help diagnose and fix SAT failures. Here's a complete debugging workflow:

#### Step 1: Identify the Failed Run

```python
# List recent runs of SAT Driver job
get_job_runs(job_id="438463735912275", limit=10)

# Output shows:
# - Run ID: 589585806190425
#   State: INTERNAL_ERROR  ← Failed run
#   Start Time: 1768219203867
```

#### Step 2: Get the Complete Error Output

```python
# Get full output including errors and stack traces
get_job_run_output(run_id="589585806190425")
```

**What you'll see:**
```
📋 Run Metadata:
  Job ID: 438463735912275
  Run ID: 589585806190425
  State: INTERNAL_ERROR
  Result: FAILED
  Duration: 45.23 seconds

📓 Notebook Output:
  Result: (notebook cell outputs if any completed)

❌ Error:
  ImportError: No module named 'databricks.sdk'

🔍 Error Trace:
  Traceback (most recent call last):
    File "/Workspace/notebooks/security_analysis_driver.py", line 15
    import databricks.sdk
  ImportError: No module named 'databricks.sdk'
```

#### Step 3: Get Detailed Run Information

```python
# Get comprehensive run details
get_job_run_details(run_id="589585806190425")
```

**What you'll see:**
```
📋 Basic Information:
  Job ID: 438463735912275
  Run Name: SAT Driver Notebook
  Creator: service_principal@databricks.com

📊 State:
  Lifecycle State: INTERNAL_ERROR
  Result State: FAILED
  Message: Notebook execution failed

⏱️  Timing:
  Start Time: 2026-01-11 19:40:03
  End Time: 2026-01-11 19:40:48
  Duration: 45.23 seconds
  Setup Duration: 12.5 seconds
  Execution Duration: 30.1 seconds
  Cleanup Duration: 2.6 seconds

🖥️  Cluster:
  Cluster ID: 0112-120006-ygvdfehe
  Spark Context ID: 7234567890123456

📝 Tasks (3 total):
  Task: install_dependencies
    State: TERMINATED
    Result: SUCCESS
    Duration: 15.2s

  Task: run_analysis
    State: INTERNAL_ERROR  ← Failed here
    Result: FAILED
    Duration: 25.8s

  Task: generate_report
    State: SKIPPED  ← Never ran
```

#### Step 4: Investigate Cluster Issues

```python
# Get cluster event logs
get_cluster_events(
    cluster_id="0112-120006-ygvdfehe",
    limit=50
)
```

**What you'll see:**
```
[2026-01-11 19:40:05] CREATING
  Details: Starting cluster...

[2026-01-11 19:40:18] RUNNING
  Details: Cluster ready, Spark version 16.4.x

[2026-01-11 19:40:45] DRIVER_UNAVAILABLE
  Details: Driver lost connection...

[2026-01-11 19:40:48] TERMINATING
  Details: Cluster terminating due to error
```

#### Complete Debugging Example

```python
# 1. Find the failed run
runs = get_job_runs(job_id="438463735912275", limit=5)
# Identify run_id: 589585806190425 with state INTERNAL_ERROR

# 2. Get the error details
output = get_job_run_output(run_id="589585806190425")
# Error: "ImportError: No module named 'databricks.sdk'"
# Root cause: SDK not installed

# 3. Get timing and task breakdown
details = get_job_run_details(run_id="589585806190425")
# Task 'run_analysis' failed at 25.8s
# Setup completed successfully (15.2s)

# 4. Check cluster events
events = get_cluster_events(cluster_id="0112-120006-ygvdfehe")
# Cluster was healthy, driver lost connection during execution

# Conclusion: Missing SDK dependency caused import error
# Fix: Add SDK installation to notebook or cluster init script
```

#### Common SAT Failure Patterns

**1. Missing Dependencies**
```python
get_job_run_output(run_id="...")
# Error: ImportError, ModuleNotFoundError
# Fix: Update install_sat_sdk.py or requirements
```

**2. Authentication Failures**
```python
get_job_run_output(run_id="...")
# Error: "401 Unauthorized" or "403 Forbidden"
# Fix: Check service principal permissions, secret scope access
```

**3. Timeout Issues**
```python
get_job_run_details(run_id="...")
# Execution Duration: 7200+ seconds (2+ hours)
# State: CANCELLED or TIMEOUT
# Fix: Increase job timeout or optimize queries
```

**4. Resource Limits**
```python
get_cluster_events(cluster_id="...")
# Events: OUT_OF_MEMORY, DRIVER_UNAVAILABLE
# Fix: Increase cluster size or optimize memory usage
```

**5. Configuration Errors**
```python
get_job_run_output(run_id="...")
# Error: "KeyError: 'workspace_configs'"
# Fix: Check CSV configuration files and table schemas
```

### Querying SAT Results with query_table

The `query_table` tool enables direct SQL queries against SAT results stored in Unity Catalog. This is extremely useful for validating security check results, debugging data quality issues, and generating ad-hoc reports.

**Example: Analyze Security Check Coverage**
```python
# Find SQL warehouse (preferably one that's already running)
warehouses = list_sql_warehouses()

# Query security check summary
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="""
        SELECT
            id as check_id,
            COUNT(*) as total_checks,
            SUM(score) as total_violations,
            AVG(score) as avg_violation_rate,
            MAX(score) as max_score
        FROM arunuc.security_analysis.security_checks
        GROUP BY id
        ORDER BY total_violations DESC
    """,
    max_rows=200
)
```

**Example: Identify Workspaces with Most Violations**
```python
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="""
        SELECT
            workspaceid,
            COUNT(DISTINCT id) as total_checks,
            SUM(score) as total_violations,
            AVG(score) as avg_violation_rate
        FROM arunuc.security_analysis.security_checks
        GROUP BY workspaceid
        ORDER BY total_violations DESC
    """
)
```

**Example: Investigate Specific Security Check Failures**
```python
# Get details on check 18 violations (e.g., SSO not enabled)
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="""
        SELECT
            workspaceid,
            id,
            score,
            additional_details,
            check_time,
            chk_date
        FROM arunuc.security_analysis.security_checks
        WHERE id = '18' AND score = 1
        ORDER BY check_time DESC
    """
)
```

**Example: Test SQL Queries Before Implementing in SAT**
```python
# Prototype a query for a new security check
query_table(
    warehouse_id="782228d75bf63e5c",
    sql_query="""
        SELECT
            cluster_id,
            cluster_name,
            spark_version,
            runtime_engine
        FROM arunuc.security_analysis_intermediate.clusters
        WHERE spark_version < '14.3'
    """,
    max_rows=50
)

# Once validated, implement this query in notebooks/Includes/workspace_analysis.py
```

### When to Use MCP Tools

✅ **Use MCP Tools For:**
- **Exploring** API response structures during planning
- **Prototyping** check logic rapidly
- **Validating** assumptions about data formats
- **Debugging** failed SAT runs and job errors
- **Investigating** issues with live workspace data
- **Testing** queries before implementing in SAT
- **Querying** SAT results tables to analyze security posture
- **Generating** ad-hoc security reports and dashboards
- **Manual remediation** of security issues during incident response
- **Diagnosing** cluster problems and resource issues

❌ **Don't Use MCP Tools For:**
- Runtime SAT execution
- Automated remediation in production
- Integration into SAT notebooks or SDK
- Scheduled security scans

### Example Development Session

```python
# 1. PLANNING: Explore what settings are available
list_settings_metadata()
# Returns 16 available settings...

# 2. TESTING: Check current state across workspaces
workspaces = list_workspaces()
for ws in workspaces:
    result = get_setting(
        workspace_host=ws.url,
        setting_name="disable_legacy_dbfs"
    )
    print(f"{ws.name}: {result}")

# 3. IMPLEMENTING: Write the check in SAT
# (Switch to notebooks/Includes/workspace_analysis.py)
# Implement using WorkspaceSettingsClient from SAT SDK

# 4. VALIDATING: Test the implementation
# Run SAT on test workspace
# Use MCP tools to verify results match expectations
```

## SAT Development Use Cases

These examples show how to use MCP tools during SAT development and operations. Remember: these are development/testing workflows, not production integrations.

### 1. Manual Security Remediation (Development/Incident Response)

Use write operations during incident response or manual cleanup:

**Example: Terminate Non-Compliant Clusters**
```python
# SAT detects clusters running deprecated Spark versions
non_compliant_clusters = list_clusters()

for cluster in non_compliant_clusters:
    if cluster.spark_version < "14.3":
        # Preview the stop operation
        preview_stop_cluster(cluster_id=cluster.id)

        # Execute if approved
        execute_stop_cluster(confirmation_token=token)
```

**Example: Auto-Start SQL Warehouses for Scheduled Reports**
```python
# Start warehouse before SAT analysis run
preview_start_warehouse(warehouse_id="782228d75bf63e5c")
execute_start_warehouse(confirmation_token=token)

# Run SAT analysis
# ...

# Stop warehouse after completion
preview_stop_warehouse(warehouse_id="782228d75bf63e5c")
execute_stop_warehouse(confirmation_token=token)
```

### 2. Planning Enhanced Security Checks

Use MCP tools to research and plan new SAT security checks:

**Workspace Settings Checks**
- Enhanced Security Monitoring (ESM) enablement
- Legacy DBFS access disabled
- Compliance security profile enabled
- Workspace admin restrictions

**Unity Catalog Governance**
- Catalog access patterns
- Schema-level permissions audit
- Table encryption verification

**Compute Security**
- Cluster policy compliance
- Instance pool configurations
- Spark version currency

### 3. Prototyping Security Validation Logic

Prototype and test validation logic before implementing in SAT:

```python
# Continuous compliance monitoring
def validate_workspace_security(workspace_id):
    # Check ESM
    esm = get_setting(setting_name="enhanced_security_monitoring")

    # Check IP access lists
    ip_lists = list_ip_access_lists()

    # Check cluster policies
    policies = list_cluster_policies()

    # Generate compliance report
    return build_compliance_report(esm, ip_lists, policies)
```

### 4. Testing SAT Driver Workflows

Test and validate SAT driver logic before deployment:

- **Pre-flight checks** - Validate environment before analysis
- **Resource provisioning** - Start required warehouses/clusters
- **Dynamic workspace discovery** - Detect new workspaces automatically
- **Post-analysis cleanup** - Stop resources to control costs

### 5. Prototyping Custom Reports

Prototype custom reporting logic and data collection:

```python
# Aggregate security metrics across all workspaces
workspaces = list_workspaces()

for workspace in workspaces:
    # Collect metrics
    settings = list_settings_metadata(workspace_host=workspace.url)
    clusters = list_clusters(workspace_host=workspace.url)
    jobs = list_jobs(workspace_host=workspace.url)

    # Build dashboard data
    dashboard_data[workspace.id] = {
        "settings_count": len(settings),
        "cluster_count": len(clusters),
        "job_count": len(jobs)
    }
```

### 6. Manual Incident Response

Use write operations for immediate incident response actions:

**Scenario: Compromised Cluster Detected**
```python
# Immediately stop compromised cluster
preview_stop_cluster(cluster_id="suspicious-cluster-id")
execute_stop_cluster(confirmation_token=token)

# Cancel running jobs on that cluster
running_jobs = get_job_runs(job_id="...")
for run in running_jobs:
    preview_cancel_job_run(run_id=run.id)
    execute_cancel_job_run(confirmation_token=token)
```

### 7. Manual Cost Management

Monitor and manually control compute costs during development:

```python
# Find idle SQL warehouses
warehouses = list_sql_warehouses()

for warehouse in warehouses:
    details = get_warehouse_details(warehouse_id=warehouse.id)

    # Stop warehouses idle > 2 hours
    if warehouse.state == "RUNNING" and idle_time > 7200:
        preview_stop_warehouse(warehouse_id=warehouse.id)
        execute_stop_warehouse(confirmation_token=token)
```

### 8. Security Check Development Workflow

**Step 1: Explore**
```python
# Discover available settings
list_settings_metadata()
```

**Step 2: Test Query**
```python
# Get specific setting value
get_setting(setting_name="disable_legacy_dbfs")
```

**Step 3: Implement SAT Check**
```python
# Add to notebooks/Includes/workspace_analysis.py
check_id = '150'
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def rule_disable_legacy_dbfs(df):
    # Check if legacy DBFS is disabled
    setting = get_setting(setting_name="disable_legacy_dbfs")
    if setting.get("disable_legacy_dbfs", {}).get("enabled", False):
        return (check_id, 0, {})
    else:
        return (check_id, 1, {"workspace_id": workspace_id})
```

**Step 4: Validate**
```python
# Test on sample workspace
result = rule_disable_legacy_dbfs(None)
print(f"Check {result[0]}: {'PASS' if result[1] == 0 else 'FAIL'}")
```

## MCP Server Configuration

The Databricks MCP server is located at:
```
/Users/arun.pamulapati/Projects/databricks-mcp-server/
```

**Key files:**
- `server.py` - Main MCP server implementation
- Authentication handled via Databricks SDK with profile-based auth

## Important Notes

### Development-Time Tools
- **These tools are NOT part of the SAT runtime** - They are development and testing utilities used via Claude Code
- Use these tools to explore, prototype, and validate before implementing in SAT
- SAT implementation uses the SDK client packages in `src/securityanalysistoolproject/clientpkgs/`

### Technical Details
- All tools use the Databricks SDK internally
- Authentication is handled automatically via configured Databricks profiles
- Responses are returned as formatted JSON
- Most tools support pagination (handled automatically)
- Error responses include helpful context for debugging
- Write operations require explicit confirmation for safety
- All operations respect Databricks RBAC and access controls

### Best Practices
1. **Plan** - Use MCP tools to explore APIs and understand data structures
2. **Implement** - Write SAT code using SDK client packages
3. **Test** - Validate implementation with MCP tools before deployment
4. **Deploy** - Build and deploy SAT using standard DABS workflow
5. **Debug** - Use MCP tools to investigate issues with live data

## Recent Enhancements

### January 2026 - Query Execution & Job Debugging Tools

✅ **Implemented:** SQL query execution capability
- `query_table` - Execute read-only SQL queries against Unity Catalog tables
  - Query SAT security check results for analysis and validation
  - Test SQL queries before implementing in SAT
  - Generate ad-hoc security reports and dashboards
  - Support for up to 1000 rows per query with configurable limits
  - Read-only (SELECT) enforcement for safety

✅ **Implemented:** Three new debugging tools for SAT troubleshooting
- `get_job_run_output` - Get notebook outputs, errors, and stack traces
- `get_job_run_details` - Get comprehensive run metadata and timing
- `get_cluster_events` - Get cluster lifecycle events and errors

## Future Enhancements

Potential additional tools for SAT development:
- **Task-level logs** - Get individual task stdout/stderr for multi-task jobs
- **Workspace configuration batch retrieval** - Get all settings in one call
- **Security check validation helpers** - Test check logic against mock data
- **Audit log analysis tools** - Search and filter account audit logs
- **Cost analysis** - Track compute costs per run/workspace
- **Performance profiling** - Identify slow queries and bottlenecks
- **Notebook diff** - Compare notebook versions across runs
- **Secret scanning** - Validate secrets and credentials access
