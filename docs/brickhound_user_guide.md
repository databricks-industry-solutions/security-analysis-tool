# BrickHound User Guide

## Overview

BrickHound is a graph-based permissions analysis tool integrated into SAT. It answers critical security questions:
- "Who can access this resource?"
- "What can this user access?"
- "Can this user escalate to admin privileges?"
- "Who can impersonate this service principal?"

## Architecture

### Data Collection
- **Job:** `BrickHound Permissions Analysis - Data Collection`
- **Schedule:** Daily (2 AM ET)
- **Runtime:** 10-30 minutes depending on account size
- **Output:** 3 Delta Lake tables

### Graph Structure
- **50+ node types:** Users, groups, service principals, clusters, jobs, tables, catalogs, schemas, warehouses, etc.
- **60+ relationship types:** MEMBER_OF, HAS_PERMISSION, OWNS, CAN_IMPERSONATE, INHERITS_FROM, etc.
- **3 tables:**
  - `brickhound_vertices`: All principals and resources
  - `brickhound_edges`: All relationships between nodes
  - `brickhound_collection_metadata`: Collection run metadata

### Analysis Tools
1. **Web App:** Interactive queries via Flask UI
2. **Notebooks:** 4 specialized analysis notebooks
3. **SQL Queries:** Direct table access for custom analysis

## Using the Web App

### Access
Navigate to: `https://<workspace>/apps/brickhound-sat`

Or find the URL in Terraform outputs:
```bash
terraform output brickhound_app_url
```

### Features
- **Dashboard:** View collection runs and statistics
- **Principal Search:** Find what a user/group/SP can access
- **Resource Search:** Find who can access a table/cluster/job
- **Path Analysis:** Discover privilege escalation paths
- **Reports:** Pre-built compliance and risk reports

### Example Queries
1. "What can john.doe@company.com access?"
   - Shows all tables, clusters, jobs, warehouses accessible by user
   - Includes permission sources (direct, group, ownership)

2. "Who can access production.sales.customers table?"
   - Lists all users, groups, SPs with access
   - Shows permission levels (READ, WRITE, ADMIN)

3. "Can contractor@external.com reach admin privileges?"
   - Discovers paths to Account Admin, Metastore Admin, Workspace Admin
   - Shows intermediate groups and permissions

### Web App Troubleshooting
If the app shows "App Not Available":
1. Check app status: Databricks Apps → `brickhound-sat`
2. Verify data collection has completed at least once
3. Check service principal permissions (see Troubleshooting section)

## Using the Notebooks

### Location
`/Repos/Applications/SAT/notebooks/brickhound/`

### Prerequisites
- Run the data collection job at least once
- Have access to the SQL warehouse configured for SAT
- Have READ access to the BrickHound tables

### Notebooks

#### 1. Principal/Resource Analysis (`01_principal_resource_analysis.py`)
**Use Case:** Access reviews, user offboarding, compliance audits

**How to Use:**
1. Run all cells to initialize the SDK
2. Select analysis type from dropdown:
   - **Principal Access:** What can a user/group/SP access?
   - **Resource Access:** Who can access a specific resource?
3. Enter identifier:
   - For principal: Email (user@company.com), group name, or SP application ID
   - For resource: Full path (catalog.schema.table, cluster name, job name)
4. Select data snapshot from dropdown (uses latest by default)
5. Run the analysis cell

**Output:**
- List of accessible resources (for principals)
- List of authorized principals (for resources)
- Permission levels and sources:
  - `DIRECT`: Permission directly assigned to principal
  - `GROUP`: Inherited via group membership
  - `OWNERSHIP`: Owner of the resource
  - `PARENT`: Inherited from parent resource (catalog → schema → table)

**Example Output:**
```
Principal: john.doe@company.com

Accessible Resources:
- production.sales.customers (READ via GROUP:data-analysts)
- production.sales.orders (WRITE via DIRECT)
- shared-cluster (CAN_ATTACH via GROUP:data-analysts)
- ETL-Job-123 (OWNER via DIRECT)
```

#### 2. Escalation Path Analysis (`02_escalation_paths.py`)
**Use Case:** Risk assessment, compromise scenarios, privilege escalation detection

**How to Use:**
1. Run initialization cells
2. Enter principal identifier (email, group name, SP ID)
3. Select target admin role (optional - searches all admin roles by default):
   - Account Admin
   - Metastore Admin
   - Workspace Admin
4. Select path type:
   - **Shortest Path:** Most direct route to admin
   - **All Paths:** All possible escalation routes
5. Run the analysis cell

**Output:**
- All paths connecting principal to admin roles
- Path length (number of hops)
- Relationship chains with details
- Risk assessment

**Example Output:**
```
Escalation Paths for contractor@external.com:

Path 1 (2 hops):
contractor@external.com
  → MEMBER_OF → external-contractors (group)
  → MEMBER_OF → workspace-admins (group)
  → HAS_ROLE → Workspace Admin

Risk: MODERATE (2 hops to admin access)
Recommendation: Review business justification for contractor admin path
```

**Risk Scoring:**
- **0 hops:** Direct admin access (expected for admins)
- **1 hop:** One step to admin (review justification)
- **2-3 hops:** Moderate risk (validate business need)
- **4+ hops:** Complex path (consider simplifying structure)

#### 3. Impersonation Analysis (`03_impersonation_analysis.py`)
**Use Case:** Service principal security, lateral movement detection, token theft scenarios

**How to Use:**
1. Run initialization cells
2. Enter source principal (starting point - usually a user or low-privilege SP)
3. Enter target principal (target to reach - usually a high-privilege SP)
4. Select path type:
   - **All Paths:** Show every possible route
   - **Shortest Path:** Most direct impersonation route
5. Run the analysis cell

**Output:**
- All paths connecting source to target
- Relationship types in path:
  - `CAN_IMPERSONATE`: Direct impersonation permission
  - `MEMBER_OF`: Group membership
  - `HAS_PERMISSION`: Permission grant
  - `OWNS`: Ownership relationship
- Risk assessment and mitigation recommendations

**Example Output:**
```
Impersonation Paths: user@company.com → prod-etl-service-principal

Path 1 (3 hops):
user@company.com
  → MEMBER_OF → etl-developers (group)
  → HAS_PERMISSION(MANAGE) → ETL-Job-789 (job)
  → RUNS_AS → prod-etl-service-principal

Risk: HIGH (User can modify job to impersonate production SP)
Mitigation: Use job-scoped service principals or restrict MANAGE permission
```

#### 4. Advanced Reports (`04_advanced_reports.py`)
**Use Case:** Executive reports, compliance documentation, security assessments

**Reports Available:**

1. **Over-Privileged Users**
   - Users with admin access
   - Users with excessive permissions across multiple resources
   - External users with elevated access

2. **Orphaned Resources**
   - Resources with no active owner
   - Resources with deleted/deactivated owner
   - Recommendation: Assign new owners

3. **High-Risk Service Principals**
   - Service principals with admin roles
   - Service principals with broad permissions
   - Service principals with impersonation chains

4. **Compliance Mappings**
   - DASF (Databricks Account Security Framework) mapping
   - HITRUST mapping
   - Shows which BrickHound findings map to compliance requirements

**How to Use:**
1. Run initialization cells
2. Select report type from dropdown
3. Configure filters (optional):
   - Workspace filter
   - Principal type filter
   - Resource type filter
4. Run the report cell
5. Export results (optional):
   - CSV export for executive reporting
   - JSON export for automation

**Example Output (Over-Privileged Users Report):**
```
Over-Privileged Users Report
Generated: 2026-01-15 14:30:00

HIGH RISK (10 users):
- admin@company.com: Account Admin + 5 workspace admin roles
- contractor@external.com: Path to Workspace Admin (2 hops)
...

MEDIUM RISK (25 users):
- user1@company.com: MODIFY access to 150+ tables
- user2@company.com: CAN_MANAGE permission on 20+ clusters
...

RECOMMENDATIONS:
1. Review necessity of admin access for 10 high-risk users
2. Implement just-in-time access for contractors
3. Apply principle of least privilege to medium-risk users
```

## Interpreting Results

### Permission Sources
Understanding how a principal gained access:

- **DIRECT:** Permission directly assigned to principal
  - Example: `GRANT SELECT ON TABLE prod.sales.customers TO user@company.com`

- **GROUP:** Inherited via group membership
  - Example: User is member of "data-analysts" group, group has SELECT permission

- **OWNERSHIP:** Owner of the resource
  - Example: User created the table and is the owner

- **PARENT:** Inherited from parent resource (Unity Catalog hierarchy)
  - Example: USAGE permission on catalog grants access to child schemas/tables

### Privilege Levels
Common permission levels in Databricks:

- **READ/SELECT:** View metadata and data
- **WRITE/MODIFY:** Modify data, update configurations
- **ADMIN/MANAGE:** Full control (manage permissions, delete resources)
- **OWNER:** Resource ownership (highest privilege)
- **USAGE:** Basic access permission (required for UC objects)
- **CAN_ATTACH:** Can attach to clusters
- **CAN_RESTART:** Can restart clusters/warehouses
- **CAN_MANAGE:** Can modify configurations
- **CAN_IMPERSONATE:** Can run jobs/queries as service principal

### Node Types
Key node types in the graph:

**Principals:**
- `User`: Individual user accounts
- `Group`: User groups (workspace or account-level)
- `ServicePrincipal`: Application identities

**Resources:**
- `Catalog`, `Schema`, `Table`: Unity Catalog objects
- `Cluster`, `ClusterPolicy`: Compute resources
- `Job`: Workflow automation
- `SQLWarehouse`: SQL compute endpoint
- `Workspace`: Databricks workspace
- `Secret`, `SecretScope`: Secrets management
- `Repo`: Git repositories
- `Notebook`: Analysis notebooks

### Relationship Types
Common relationship types:

**Identity Relationships:**
- `MEMBER_OF`: User/group/SP is member of group
- `OWNS`: Principal owns resource
- `CREATED_BY`: Principal created resource

**Permission Relationships:**
- `HAS_PERMISSION`: Direct permission grant (includes permission level)
- `CAN_IMPERSONATE`: Can assume identity of SP
- `CAN_ATTACH`: Can attach to cluster
- `CAN_MANAGE`: Can manage resource

**Hierarchy Relationships:**
- `INHERITS_FROM`: Permission inheritance (catalog → schema → table)
- `PARENT_OF`: Parent-child relationship in UC hierarchy
- `RUNS_AS`: Job runs as service principal

## Troubleshooting

### No Data in Tables
**Symptom:** App shows "0 runs", notebooks return empty results

**Diagnosis:**
```sql
SELECT COUNT(*) FROM {catalog}.{schema}.brickhound_vertices;
SELECT COUNT(*) FROM {catalog}.{schema}.brickhound_edges;
SELECT COUNT(*) FROM {catalog}.{schema}.brickhound_collection_metadata;
```

If all return 0 or tables don't exist:

**Solution:**
1. Check if data collection job exists:
   - Navigate to: Databricks Jobs
   - Search for: "BrickHound Permissions Analysis - Data Collection"
2. Check job run history:
   - If no runs: Manually trigger job ("Run Now")
   - If failed: Check job logs for errors
3. Wait for completion (10-30 minutes depending on account size)
4. Verify tables after job completes

**Common Job Failure Causes:**
- Insufficient permissions (need Account Admin or Workspace Admin)
- SQL Warehouse not running or misconfigured
- Network connectivity issues
- Secret scope missing or secrets incorrect

### App "Not Available"
**Symptom:** App shows "App Not Available" or 503 error

**Diagnosis Steps:**
1. Check app deployment status:
   ```bash
   databricks apps list --output json | jq '.apps[] | select(.name == "brickhound-sat")'
   ```

2. Check app logs:
   - Databricks Apps → brickhound-sat → Logs
   - Look for permission errors or connection failures

**Solutions:**

**Permission Issues:**
```sql
-- Verify grants exist
SHOW GRANTS ON SCHEMA {catalog}.{schema};

-- If missing, apply grants (replace <app-sp-id> with actual ID)
GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `<app-sp-id>`;
GRANT SELECT ON SCHEMA {catalog}.{schema} TO `<app-sp-id>`;
```

**App Service Principal ID:**
Find via Terraform output:
```bash
terraform output brickhound_app_id
```

Or via Databricks UI:
- Databricks Apps → brickhound-sat → Configuration → Service Principal ID

**Port Configuration Issues:**
Verify health check configuration in Terraform:
```hcl
health_check {
  path    = "/health"
  port    = 8000  # Must match app port
  timeout = 30
}
```

**Environment Variable Issues:**
Check that app has correct environment variables:
- `BRICKHOUND_CATALOG`
- `BRICKHOUND_SCHEMA`
- `WAREHOUSE_ID`
- `PORT` (should be 8000)

If variables are incorrect, update via Terraform and redeploy.

### SDK Import Errors in Notebooks
**Symptom:** `✗ SDK import failed - Using fallback functions`

**Why This Happens:**
Notebooks try to import the SecurityAnalyzer SDK from `/Workspace/Repos/.../src/brickhound/`. If the path is incorrect or SDK not deployed, fallback functions are used (limited functionality).

**Solutions:**

1. **Re-run initialization cell:**
   - Look for cell with: `%pip install -e ../../src/brickhound`
   - Run this cell
   - Restart Python kernel

2. **Verify repo path:**
   ```python
   import sys
   print(sys.path)
   # Should include: /Workspace/Repos/Applications/SAT/src
   ```

3. **Check if SDK exists:**
   ```bash
   %sh
   ls -la /Workspace/Repos/Applications/SAT/src/brickhound/
   # Should show setup.py and security_analyzer.py
   ```

4. **Restart Python kernel:**
   - Databricks notebook menu → Detach & Reattach
   - Or: Clear → Clear State

**Fallback Mode:**
If SDK cannot be loaded, notebooks fall back to basic SQL queries. Features still work but with reduced functionality:
- ✓ Basic queries work
- ✗ Advanced graph algorithms unavailable
- ✗ NetworkX-based path finding unavailable
- ✗ Caching and optimization disabled

### Empty Results for Valid Principals/Resources
**Symptom:** Search returns empty results for principals/resources that should exist

**Possible Causes:**

1. **Principal name mismatch:**
   - Try full email: `user@company.com` (not just `user`)
   - Try display name vs email
   - Check for case sensitivity

2. **Resource not in scope:**
   - Data collection may be scoped to specific workspaces
   - Check collection metadata:
     ```sql
     SELECT * FROM {catalog}.{schema}.brickhound_collection_metadata;
     ```

3. **Stale data:**
   - Results are based on last collection run
   - Trigger new collection job if recent changes expected
   - Check collection timestamp in metadata table

4. **Insufficient permissions during collection:**
   - Collection job may have failed to retrieve some data
   - Check job logs for permission warnings
   - Ensure service principal has Account Admin or sufficient permissions

### Performance Issues
**Symptom:** Queries take very long (>5 minutes) or timeout

**Solutions:**

1. **Optimize SQL queries:**
   - Add filters to narrow search scope
   - Use specific resource paths instead of wildcards
   - Limit path analysis depth

2. **Scale SQL Warehouse:**
   - Increase warehouse size (Small → Medium → Large)
   - Enable autoscaling
   - Increase cluster count

3. **Partition tables (for very large deployments):**
   ```sql
   -- Partition by run_id for historical analysis
   ALTER TABLE {catalog}.{schema}.brickhound_vertices
   SET TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');
   ```

4. **Use materialized views:**
   Create views for common queries to improve performance.

## Configuration

### Environment Variables (App)
Set in Terraform (`terraform/common/brickhound_app.tf`):

```hcl
env = [
  {
    name  = "BRICKHOUND_CATALOG"
    value = local.brickhound_catalog
  },
  {
    name  = "BRICKHOUND_SCHEMA"
    value = local.brickhound_schema
  },
  {
    name  = "WAREHOUSE_ID"
    value = local.brickhound_warehouse_id
  },
  {
    name  = "PORT"
    value = "8000"
  }
]
```

**To Update:**
1. Modify Terraform variables
2. Run `terraform apply`
3. App will automatically redeploy with new configuration

### Secrets (Data Collection)
Read from `sat_scope` secret scope:

**Required Secrets:**
- `account-console-id`: Databricks Account UUID
- `client-id`: Service principal client ID
- `client-secret`: Service principal client secret
- `analysis_schema_name`: Format: `catalog.schema` for table storage

**To Update Secrets:**
```bash
databricks secrets put --scope sat_scope --key account-console-id --string-value "<account-id>"
databricks secrets put --scope sat_scope --key client-id --string-value "<client-id>"
databricks secrets put --scope sat_scope --key client-secret --string-value "<client-secret>"
```

### Collection Configuration
Modify in data collection notebook (`notebooks/permission_analysis_data_collection.py`):

**Collection Scope:**
```python
# Collect from all workspaces in account
scope = "account"

# Collect from current workspace only
scope = "workspace"

# Collect Unity Catalog objects only
scope = "unity_catalog"
```

**Object Types to Collect:**
```python
# Enable/disable specific object types
collect_config = {
    "users": True,
    "groups": True,
    "service_principals": True,
    "clusters": True,
    "cluster_policies": True,
    "jobs": True,
    "catalogs": True,
    "schemas": True,
    "tables": True,
    "sql_warehouses": True,
    "secrets": True,
    "notebooks": True,
    "repos": True,
}
```

**Workspace Filtering:**
```python
# Include only specific workspaces
workspace_filter = ["workspace-id-1", "workspace-id-2"]

# Exclude specific workspaces
workspace_exclude = ["sandbox-workspace-id"]
```

### Schedule Configuration

**DABS Deployment:**
Configured during `./install.sh`:
- Default: Daily at 2 AM ET (`0 0 2 * * ?`)
- Custom: Enter custom cron expression when prompted

**Terraform Deployment:**
Set in `terraform.tfvars`:
```hcl
# Daily at 2 AM ET (default)
brickhound_schedule = "0 0 2 * * ?"

# Weekly on Sunday at 2 AM ET
brickhound_schedule = "0 0 2 ? * SUN"

# Every 6 hours
brickhound_schedule = "0 0 */6 * * ?"
```

**Cron Expression Format (Quartz):**
```
┌───────────── second (0 - 59)
│ ┌───────────── minute (0 - 59)
│ │ ┌───────────── hour (0 - 23)
│ │ │ ┌───────────── day of month (1 - 31)
│ │ │ │ ┌───────────── month (1 - 12)
│ │ │ │ │ ┌───────────── day of week (1 - 7) (1 = Monday)
│ │ │ │ │ │
│ │ │ │ │ │
* * * * * *
```

**Examples:**
- `0 0 2 * * ?` - Daily at 2 AM
- `0 0 2 ? * SUN` - Weekly on Sunday at 2 AM
- `0 0 */6 * * ?` - Every 6 hours
- `0 0 2 1 * ?` - Monthly on the 1st at 2 AM

## Best Practices

### 1. Run Collection Regularly
**Recommendation:** Daily schedule ensures fresh data

**Why:** Permissions change frequently:
- Users added/removed from groups
- New resources created
- Permissions granted/revoked
- Service principals rotated

**Action:** Keep default daily schedule unless specific business need for different frequency.

### 2. Review Before Offboarding
**Use Case:** User leaves organization or changes roles

**Process:**
1. Run Principal Access Analysis for departing user
2. Document all accessible resources
3. Transfer ownership of critical resources
4. Remove from groups
5. Disable/delete user account
6. Re-run analysis to verify access removed

**BrickHound Query:**
```
Principal: departing-user@company.com
Analysis Type: Principal Access
```

Document output for compliance/audit trail.

### 3. Audit Admin Access Monthly
**Use Case:** Compliance requirement, security posture assessment

**Process:**
1. Run Escalation Path Analysis for all external users
2. Review paths to admin roles (especially 1-2 hop paths)
3. Document business justification for each admin path
4. Remove unnecessary paths
5. Export report for compliance documentation

**BrickHound Notebooks:**
- Use `02_escalation_paths.py`
- Export results to CSV
- Include in monthly security reports

### 4. Monitor Service Principals Quarterly
**Use Case:** Prevent lateral movement, reduce impersonation risk

**Process:**
1. Run High-Risk Service Principals report
2. Review impersonation chains
3. Validate business need for each chain
4. Implement job-scoped SPs where possible
5. Rotate credentials for high-risk SPs

**BrickHound Reports:**
- Use `04_advanced_reports.py` → High-Risk Service Principals
- Use `03_impersonation_analysis.py` for specific SP chains

### 5. Document Findings for Compliance
**Use Case:** Audit preparation, compliance reporting (SOC 2, ISO 27001, HIPAA)

**Process:**
1. Run Advanced Reports monthly/quarterly
2. Export results (CSV/JSON)
3. Map findings to compliance controls:
   - Over-privileged users → Access Control (AC)
   - Orphaned resources → Configuration Management (CM)
   - Impersonation chains → Identification and Authentication (IA)
4. Document remediation actions
5. Re-run reports to verify remediation

**DASF Mapping:**
BrickHound findings map to DASF controls:
- Admin access review → DASF 1.1 (Identity and Access Management)
- Privilege escalation paths → DASF 1.2 (Privilege Management)
- Service principal impersonation → DASF 1.3 (Service Principal Management)
- Resource access audits → DASF 2.1 (Data Access Controls)

### 6. Investigate Anomalies
**Use Case:** Security incident response, threat hunting

**Indicators to Watch:**
- External users with admin paths
- Contractors with OWNER permissions
- Service principals with broad access
- Complex impersonation chains (4+ hops)
- Orphaned high-value resources (production tables)

**Response:**
1. Document finding in BrickHound
2. Investigate business justification
3. If suspicious: Revoke access immediately
4. If legitimate: Document exception and approval

### 7. Simplify Permission Structures
**Use Case:** Reduce complexity, minimize attack surface

**Anti-Patterns to Avoid:**
- Deep group nesting (5+ levels)
- Circular group memberships
- Redundant permissions (direct + group grant same permission)
- Over-use of direct grants (prefer groups)

**BrickHound Can Detect:**
- Complex escalation paths (4+ hops)
- Multiple paths to same admin role
- Redundant group memberships

**Action:** Simplify structure when 4+ hop paths are detected.

## Security Considerations

### 1. Data Sensitivity
**What BrickHound Stores:**
- Identity data: Usernames, emails, group names, SP IDs
- Access data: Who can access what resources
- Permission levels: READ, WRITE, ADMIN, etc.
- Relationship data: Group memberships, ownership

**Sensitivity Level:** HIGH - This is critical security data

**Access Control Recommendations:**
- Restrict table access to security team only
- Use Unity Catalog grants (not workspace ACLs)
- Monitor query logs for suspicious access
- Enable audit logging on BrickHound tables

**Example Grants:**
```sql
-- Grant to security team only
GRANT SELECT ON SCHEMA {catalog}.{schema} TO `security-team`;

-- Revoke public access
REVOKE SELECT ON SCHEMA {catalog}.{schema} FROM `users`;
```

### 2. Service Principal Security (App)
**App SP Permissions:**
- READ-ONLY access to BrickHound tables
- No WRITE, MODIFY, or ADMIN permissions
- Scoped to single schema (not entire catalog)

**Principle of Least Privilege Applied:**
```hcl
# Only grants needed for app functionality
privileges = ["USE_SCHEMA", "SELECT"]

# NOT granted: MODIFY, CREATE, DELETE, MANAGE
```

**Verification:**
```sql
SHOW GRANTS ON SCHEMA {catalog}.{schema};
-- Verify app SP has only USE_SCHEMA and SELECT
```

**If Compromised:**
- App SP cannot modify data
- App SP cannot drop tables
- App SP cannot grant additional permissions
- Impact limited to data disclosure (read-only)

**Mitigation:**
- Rotate SP credentials regularly (quarterly)
- Monitor app logs for suspicious queries
- Use IP access lists to restrict app access

### 3. Collection Job Permissions
**Required Permissions:**
- Account Admin OR Workspace Admin (per workspace)
- READ access to all APIs (users, groups, jobs, clusters, UC)
- WRITE access to BrickHound tables (for data storage)

**Why These Permissions:**
- Account Admin: Needed to query account-level resources (workspaces, metastores)
- Workspace Admin: Needed to query workspace-level resources (clusters, jobs)
- UC permissions: Needed to enumerate catalogs, schemas, tables

**Security Implications:**
- Collection SP has broad READ access
- Collection SP can see all identities and permissions
- Collection SP cannot modify configurations or grant permissions

**Best Practices:**
- Use dedicated SP for BrickHound (not shared with SAT)
- Rotate credentials regularly
- Monitor SP usage via audit logs
- Restrict SP to collection job only (don't use for other purposes)

### 4. Data Retention
**Default Behavior:**
- Tables persist until manually deleted
- Each collection run has unique `run_id`
- Historical data accumulates over time

**Privacy Considerations:**
- May contain data about former employees
- May show historical access to sensitive resources
- May reveal permission changes over time

**Retention Policy Recommendations:**
```sql
-- Delete runs older than 90 days
DELETE FROM {catalog}.{schema}.brickhound_vertices
WHERE run_id IN (
  SELECT run_id FROM {catalog}.{schema}.brickhound_collection_metadata
  WHERE collection_timestamp < CURRENT_DATE() - INTERVAL 90 DAYS
);

-- Similar for edges and metadata tables
```

**Automate Retention:**
Add retention task to data collection job or create separate cleanup job.

### 5. Query Logging
**BrickHound Queries are Logged:**
- All SQL queries logged in Unity Catalog audit logs
- App queries logged in Databricks Apps logs
- Notebook queries logged in workspace audit logs

**What This Means:**
- Admins can see what permissions are being investigated
- Suspicious queries may indicate insider threat
- Historical queries provide audit trail

**Monitoring Recommendations:**
- Alert on unusual query patterns:
  - High volume of queries from single user
  - Queries for sensitive principals (executives, SPs)
  - Queries at unusual times
- Review logs quarterly for anomalies
- Include in security incident investigations

### 6. Network Security
**App Network Access:**
- App runs in Databricks-managed network
- Accessible via workspace URL
- Subject to workspace IP access lists (if configured)

**Recommendations:**
- Apply IP access lists to workspace
- Use private connectivity (PrivateLink/VNet injection) if available
- Require SSO for workspace access
- Enable MFA for all users

**Collection Job Network Access:**
- Job calls Databricks APIs (workspace, accounts, UC)
- Requires outbound connectivity to API endpoints
- Subject to serverless egress controls (if on serverless)

**Recommendations:**
- Use private connectivity for API calls
- Monitor API usage via audit logs
- Apply serverless egress controls if available

### 7. Compliance Mappings

**DASF (Databricks Account Security Framework):**
- BrickHound supports DASF 1.x (Identity and Access Management)
- Findings map to DASF controls in `04_advanced_reports.py`

**HITRUST:**
- Identity management: 01.a, 01.b
- Access control: 01.c, 01.d, 01.e
- Monitoring and audit: 09.aa, 09.ab

**SOC 2:**
- Trust Service Criteria: CC6.1, CC6.2, CC6.3 (Logical and Physical Access Controls)

**ISO 27001:**
- A.9 (Access Control)
- A.18.1.4 (Privacy and protection of personally identifiable information)

**Use BrickHound for Compliance:**
- Quarterly access reviews (SOC 2 CC6.1)
- Privilege escalation detection (ISO 27001 A.9.2.3)
- Service principal management (DASF 1.3)
- Orphaned resource detection (ISO 27001 A.9.2.6)

---

## Getting Help

### Common Issues and Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| No data in tables | Manually run data collection job |
| App not available | Check service principal grants |
| SDK import failed | Re-run `%pip install` cell, restart kernel |
| Empty search results | Check principal name spelling, verify data collection scope |
| Slow queries | Scale SQL warehouse, add query filters |

### Additional Resources

- **BrickHound Architecture:** See `docs/BRICKHOUND_INTEGRATION.md`
- **SAT Documentation:** See main `README.md`
- **Terraform Resources:** See `terraform/README.md`
- **DABS Installation:** See `dabs/README.md`
- **API Reference:** See SecurityAnalyzer SDK docstrings in `src/brickhound/security_analyzer.py`

### Support

For issues or questions:
1. Check this user guide first
2. Review installation logs
3. Check Databricks job logs for collection errors
4. Check app logs for runtime errors
5. Open GitHub issue with:
   - Error message
   - Steps to reproduce
   - Collection job logs (if applicable)
   - App logs (if applicable)
