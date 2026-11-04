# Permissions Analysis Tool Databricks App

A **Gradio-based web application** for interactive Databricks security and permission analysis.

## 🎯 Overview

Permissions Analysis Tool App provides a **user-friendly web interface** for the 7 core permission analysis capabilities from the `06_permission_analysis_enhanced.py` notebook:

1. **Quick Check** - Simple yes/no: Can user access resource?
2. **Who Can Access?** - List all principals with access to a resource
3. **What Can User Access?** - List all resources accessible to a principal
4. **Effective Permissions** - Show all permission sources and effective access level
5. **Permission Chains** - Trace all inheritance paths (recursive analysis)
6. **Full Recursive Access** - Deep dive showing direct + indirect access via groups
7. **Escalation Risk** - Identify privilege escalation paths to admin resources

## 🏗️ Architecture

```
Permissions Analysis Tool App (Gradio)
    ↓
Databricks SQL Warehouse
    ↓
Unity Catalog Tables
    • {CATALOG}.{SCHEMA}.vertices
    • {CATALOG}.{SCHEMA}.edges
```

**Data Flow:**
1. Customer runs `permission_analysis_data_collection.py` notebook (populates vertices/edges)
2. Customer deploys Permissions Analysis Tool App
3. App queries pre-collected graph data via SQL Warehouse
4. Interactive analysis via web UI

## 📋 Prerequisites

### 1. Data Collection (Required)

Run `notebooks/permission_analysis_data_collection.py` first to populate the graph data:
```
{CATALOG}.{SCHEMA}.vertices  # All Databricks objects & principals
{CATALOG}.{SCHEMA}.edges     # All relationships & permissions
```

### 2. SQL Warehouse (Required)

You need a running SQL Warehouse. The app uses it to query the graph data.

### 3. Permissions (Required)

The app service needs:
* `SELECT` on `{CATALOG}.{SCHEMA}.vertices`
* `SELECT` on `{CATALOG}.{SCHEMA}.edges`
* `SELECT` on `{CATALOG}.{SCHEMA}.collection_metadata`
* `USE CATALOG` on the configured catalog
* `USE SCHEMA` on the configured schema

**Grant permissions to the app's service principal:**

When you deploy a Databricks App, it runs with its own service principal identity. You must grant this identity access to your data tables.

```sql
-- Replace {CATALOG} and {SCHEMA} with your values (e.g., arunuc, brickhound)
-- Replace {APP_SERVICE_PRINCIPAL} with your app's service principal name

GRANT USAGE ON CATALOG {CATALOG} TO `{APP_SERVICE_PRINCIPAL}`;
GRANT USAGE ON SCHEMA {CATALOG}.{SCHEMA} TO `{APP_SERVICE_PRINCIPAL}`;
GRANT SELECT ON SCHEMA {CATALOG}.{SCHEMA} TO `{APP_SERVICE_PRINCIPAL}`;
```

To find your app's service principal:
1. Go to **Workspace** → **Apps** → Select your app
2. Look in the app settings/configuration for the service principal name
3. It's usually named like the app or shown in the identity section

**⚠️ Important:** If you DROP and recreate the schema/tables, you must re-grant these permissions. Unity Catalog permissions are tied to specific objects and don't persist across DROP/CREATE cycles.

## 🚀 Deployment

### Option 1: Databricks Apps (Recommended)

1. **Configure app.yaml**:

   The shipped `app.yaml` uses Databricks Apps resource bindings — no manual values to fill in:
   ```yaml
   env:
     - name: BRICKHOUND_SCHEMA
       valueFrom: "analysis_schema_name"  # bound to a secret resource
     - name: WAREHOUSE_ID
       valueFrom: "warehouse"             # bound to the sql_warehouse resource

   resources:
     - name: "analysis_schema_name"
       secret:
         permission: "READ"
         scope: "<sat-scope>"
         key: analysis_schema_name
     - name: "warehouse"
       sql_warehouse:
         permission: "CAN_USE"
         id: "<warehouse-id>"
   ```
   These bindings are declared automatically by the SAT installer (DABS or Terraform).
   For BYO scope installs, SAT can bind `analysis_schema_name` directly to your scope —
   see the [Secret Scope Reference](../../docs/sat/docs/installation/secret-scope.mdx).

2. **Deploy via Databricks CLI**:
   ```bash
   databricks apps create brickhound \
     --source-code-path ./app \
     --description "Permissions Analysis Tool"
   ```

3. **Access the App**:
   * Go to **Workspace** → **Apps** → **Permissions Analysis Tool**
   * Or use the direct URL provided after deployment

### Option 2: Local Testing

```bash
# Install dependencies
cd app/
pip install -r requirements.txt

# Set environment variables
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."
export DATABRICKS_WAREHOUSE_HTTP_PATH="/sql/1.0/warehouses/..."
export BRICKHOUND_CATALOG="arunuc"
export BRICKHOUND_SCHEMA="brickhound"

# Run the app
python app.py
```

Then open http://localhost:8000 in your browser.

## 🎮 Using the App

### Tab 1: Quick Check 🎯
**Use Case:** "Can this user access this table?"

**Inputs:**
* Principal: `user@company.com` or user name
* Resource: `catalog.schema.table` or resource name

**Output:**
* ✅ YES or ❌ NO
* List of access paths if access exists

### Tab 2: Who Can Access? 👥
**Use Case:** "Who has access to this sensitive table?"

**Inputs:**
* Resource: Table/catalog/schema name
* Minimum Permission: Filter by permission level (optional)

**Output:**
* List of all principals with access
* Permission levels for each
* Direct vs inherited grants

### Tab 3: What Can User Access? 🔐
**Use Case:** "What can this new user access?"

**Inputs:**
* Principal: User email or name
* Resource Type: Filter (Catalog, Table, Cluster, etc.) or "All"

**Output:**
* Complete list of accessible resources
* Permission levels
* Breakdown by resource type

### Tab 4: Effective Permissions 🔐
**Use Case:** "What's the actual permission level?"

**Inputs:**
* Principal: User/SP email or name
* Resource: Full resource name

**Output:**
* Effective permission (highest from all sources)
* All permission sources (direct, group, ownership)
* Whether permissions are inherited

### Tab 5: Permission Chains 🔗
**Use Case:** "How does this user have access?"

**Inputs:**
* Principal: User email or name
* Resource: Resource name

**Output:**
* All permission inheritance paths
* Multi-hop chains (User → Group → Resource)
* Path complexity (1-hop, 2-hop, 3+ hops)

### Tab 6: Full Recursive Access 🌳
**Use Case:** "Show me EVERYONE who can access this (including via groups)"

**Inputs:**
* Resource: Resource name

**Output:**
* All principals with direct access
* All principals with indirect access via groups
* Complete recursive resolution

### Tab 7: Escalation Risk 🔺
**Use Case:** "Can this user escalate to admin?"

**Inputs:**
* Principal: User email or name

**Output:**
* Risk assessment (Critical/High/Medium/Low)
* Paths to admin-level resources
* Distance to admin privileges

## 🔧 Configuration

### Environment Variables

The following env vars are injected at runtime by the Databricks Apps resource bindings
declared in `app.yaml` — you do not set them manually:

* `BRICKHOUND_SCHEMA` - Full schema name (`catalog.schema`), from `analysis_schema_name` secret resource
* `WAREHOUSE_ID` - SQL Warehouse ID, from the `warehouse` sql_warehouse resource
* `DATABRICKS_HOST` - Workspace URL (auto-set by Databricks Apps runtime)
* `DATABRICKS_TOKEN` - Access token (auto-set by Databricks Apps runtime)

### SQL Warehouse

The warehouse is declared as a resource in `app.yaml` (`name: "warehouse"`).
The SAT installer sets this to the warehouse you selected during install.
`WAREHOUSE_ID` resolves automatically from that resource — no hard-coded ID needed.

## 🔒 Security Notes

### Input Sanitization
* Basic SQL injection protection via quote escaping
* Always validate inputs before queries
* Users should have READ-ONLY access to graph tables

### Access Control
* App inherits permissions from the running user/service principal
* Recommended: Deploy with a service principal that has SELECT-only access
* Never grant MODIFY/DELETE on vertices/edges tables to the app

### Data Privacy
* App reveals sensitive security information
* Restrict app access to authorized security personnel only
* Consider logging all queries for audit trail

## 🐛 Troubleshooting

### "Error loading graph data"
**Cause:** Data tables don't exist or are empty  
**Fix:** Run `notebooks/permission_analysis_data_collection.py` first

### "Principal/Resource not found"
**Cause:** Name doesn't exactly match what's in vertices table  
**Fix:** Check exact names with: `SELECT DISTINCT name FROM {CATALOG}.{SCHEMA}.vertices WHERE node_type = 'User'`

### "No permission grants found"
**Cause:** Permission collection wasn't run or failed  
**Fix:** Re-run `permission_analysis_data_collection.py` with `collect_permissions = True`

### "Connection refused" or "Warehouse not available"
**Cause:** SQL Warehouse is stopped
**Fix:** Start the SQL Warehouse or update `app.yaml` with a running warehouse ID

### "No data collected yet" or all stats show 0
**Cause:** App's service principal doesn't have permission to read the tables
**Fix:** Grant SELECT permissions to the app's service principal:
```sql
GRANT USAGE ON CATALOG {CATALOG} TO `{APP_SERVICE_PRINCIPAL}`;
GRANT USAGE ON SCHEMA {CATALOG}.{SCHEMA} TO `{APP_SERVICE_PRINCIPAL}`;
GRANT SELECT ON SCHEMA {CATALOG}.{SCHEMA} TO `{APP_SERVICE_PRINCIPAL}`;
```

**Tip:** Use the `/api/debug` endpoint to diagnose connection and permission issues. It shows table counts and connection status.

### Data shows in SQL editor but not in app
**Cause:** Permissions were lost after DROP/recreate of schema
**Fix:** Re-grant permissions to the app's service principal (see above). Unity Catalog permissions don't persist across DROP/CREATE cycles.

## 📊 Data Requirements

The app expects these tables to exist with the following schema:

### `{CATALOG}.{SCHEMA}.vertices`
```sql
id               STRING    -- Unique identifier
node_type        STRING    -- Type (User, Catalog, Table, etc.)
name             STRING    -- Full name
display_name     STRING    -- Display name
owner            STRING    -- Owner identifier
email            STRING    -- Email (for users)
active           BOOLEAN   -- Active status
created_at       TIMESTAMP -- Creation time
```

### `{CATALOG}.{SCHEMA}.edges`
```sql
src              STRING    -- Source vertex ID
dst              STRING    -- Destination vertex ID
relationship     STRING    -- Relationship type
permission_level STRING    -- Permission (ALL PRIVILEGES, MANAGE, etc.)
inherited        BOOLEAN   -- Is inherited permission
created_at       TIMESTAMP -- Creation time
```

## 🎨 UI Features

* **Clean tabbed interface** - 7 analyses organized in tabs
* **Real-time results** - Click button, see results immediately
* **Sortable tables** - Click column headers to sort
* **Examples** - Pre-filled examples for testing
* **Statistics dashboard** - Environment overview at the top
* **Error handling** - Clear error messages for invalid inputs

## 📚 References

**Inspired by:**
* [BloodHound](https://github.com/SpecterOps/BloodHound) - Attack path analysis for Active Directory
* [ac-lineage](https://github.com/laurencewells/ac-lineage/) - Recursive permission visualization for Databricks

**Built with:**
* [Gradio](https://gradio.app/) - Python web UI framework
* [databricks-sql-connector](https://docs.databricks.com/dev-tools/python-sql-connector.html) - Databricks SQL queries
* [Databricks Apps](https://docs.databricks.com/dev-tools/databricks-apps/index.html) - Deployment platform

## 🚀 Next Steps

After deploying the app:

1. **Bookmark the app URL** for easy access
2. **Share with security team** (restrict access appropriately)
3. **Schedule data collection** - Run `permission_analysis_data_collection.py` weekly via Databricks Jobs
4. **Monitor trends** - Track permission changes over time
5. **Integrate with SIEM** - Export findings to security dashboard

## 💡 Tips

* **Refresh data regularly** - Run collection notebook weekly to catch new permissions
* **Use examples** - Each tab has example inputs to get started
* **Export results** - Copy tables to clipboard for reports
* **Combine with notebooks** - Use app for quick checks, notebooks for deep analysis
* **Document findings** - Screenshot results for security reviews

---

**🔒 Remember:** This app reveals sensitive security information. Restrict access to authorized personnel only.

