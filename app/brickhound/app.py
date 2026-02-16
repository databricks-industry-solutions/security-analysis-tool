#!/usr/bin/env python3
"""
Permissions Analysis Tool - Databricks Security Analysis Platform

A modern, dashboard-style security analysis app for Databricks environments.
Inspired by BloodHound for Active Directory analysis.
"""

from flask import Flask, request, jsonify
import os
import logging
from databricks.sdk import WorkspaceClient

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Read from environment variables (set in app.yaml)
# These MUST be configured in app.yaml - no hardcoded defaults
logger.info("[CONFIG] Environment variables check:")
logger.info(f"  BRICKHOUND_SCHEMA = {os.getenv('BRICKHOUND_SCHEMA')}")
logger.info(f"  WAREHOUSE_ID = {os.getenv('WAREHOUSE_ID')}")

# Validate required environment variables
BRICKHOUND_SCHEMA = os.getenv("BRICKHOUND_SCHEMA")

# Parse catalog.schema from environment variable
if BRICKHOUND_SCHEMA:
    parts = BRICKHOUND_SCHEMA.split(".")
    if len(parts) == 2:
        CATALOG, SCHEMA = parts
    else:
        CATALOG = None
        SCHEMA = None
else:
    CATALOG = None
    SCHEMA = None

if not BRICKHOUND_SCHEMA or not CATALOG or not SCHEMA:
    error_msg = "FATAL: Missing or invalid BRICKHOUND_SCHEMA in app.yaml:\n"
    if not BRICKHOUND_SCHEMA:
        error_msg += "  - BRICKHOUND_SCHEMA is not set\n"
    else:
        error_msg += f"  - BRICKHOUND_SCHEMA must be in format 'catalog.schema', got: {BRICKHOUND_SCHEMA}\n"
    error_msg += "\nPlease configure BRICKHOUND_SCHEMA in app.yaml before deploying."
    logger.error(error_msg)
    raise ValueError(error_msg)

logger.info(f"[CONFIG] BRICKHOUND_SCHEMA={BRICKHOUND_SCHEMA} -> CATALOG={CATALOG}, SCHEMA={SCHEMA}")

# Define table names
VERTICES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_vertices"
EDGES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_edges"
METADATA_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_collection_metadata"

logger.info(f"[CONFIG FINAL] CATALOG={CATALOG}, SCHEMA={SCHEMA}")
logger.info(f"[CONFIG FINAL] VERTICES_TABLE={VERTICES_TABLE}")
logger.info(f"[CONFIG FINAL] EDGES_TABLE={EDGES_TABLE}")
logger.info(f"[CONFIG FINAL] METADATA_TABLE={METADATA_TABLE}")

# Global variable to cache the current run_id for this session
_cached_run_id = None


def get_connection():
    """Get SQL connection using Databricks SDK"""
    try:
        from databricks.sdk import WorkspaceClient
        workspace_client = WorkspaceClient()
        
        # Debug: Show connection info (only first time)
        if not hasattr(get_connection, '_logged'):
            print(f"[AUTH] Connected to: {workspace_client.config.host}")
            print(f"[AUTH] Auth type: {workspace_client.config.auth_type}")
            get_connection._logged = True
        
        # Get warehouse ID from environment variable (set in app.yaml)
        warehouse_id = os.getenv("WAREHOUSE_ID") or os.getenv("DATABRICKS_WAREHOUSE_ID")

        if not warehouse_id:
            error_msg = (
                "FATAL: WAREHOUSE_ID environment variable is not set in app.yaml.\n"
                "Please configure WAREHOUSE_ID with a valid SQL warehouse ID before deploying."
            )
            print(f"[AUTH] ERROR: {error_msg}")
            raise ValueError(error_msg)

        if not hasattr(get_connection, '_warehouse_logged'):
            print(f"[AUTH] Using SQL Warehouse: {warehouse_id}")
            get_connection._warehouse_logged = True

        return workspace_client, warehouse_id
    except Exception as e:
        print(f"ERROR in get_connection(): {e}")
        raise


def exec_query(sql_query):
    """Execute query and return first column of first row"""
    try:
        workspace_client, warehouse_id = get_connection()
        result = workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            catalog=CATALOG,
            schema=SCHEMA,
            statement=sql_query,
            wait_timeout="30s"
        )
        if hasattr(result, 'result') and result.result:
            if hasattr(result.result, 'data_array') and result.result.data_array:
                value = result.result.data_array[0][0]
                return int(value) if value else 0
        return 0
    except Exception as e:
        print(f"Error executing query: {e}")
        return 0


def exec_query_df(sql_query):
    """Execute query and return results as list of dicts"""
    try:
        workspace_client, warehouse_id = get_connection()
        result = workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            catalog=CATALOG,
            schema=SCHEMA,
            statement=sql_query,
            wait_timeout="50s"
        )
        if hasattr(result, 'result') and result.result:
            if hasattr(result.result, 'data_array') and result.result.data_array:
                columns = []
                try:
                    if hasattr(result, 'manifest') and result.manifest:
                        if hasattr(result.manifest, 'schema') and result.manifest.schema:
                            for col in result.manifest.schema.columns:
                                if hasattr(col, 'name'):
                                    columns.append(col.name)
                                elif isinstance(col, dict) and 'name' in col:
                                    columns.append(col['name'])
                except Exception:
                    pass
                rows = []
                for row in result.result.data_array:
                    if columns and len(columns) == len(row):
                        rows.append(dict(zip(columns, row)))
                    else:
                        rows.append({f"col{i}": val for i, val in enumerate(row)})
                return rows
        return []
    except Exception as e:
        print(f"Error executing query: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_latest_run_id():
    """Get the most recent run_id from collection_metadata"""
    try:
        result = exec_query_df(f"""
            SELECT run_id FROM {METADATA_TABLE}
            ORDER BY collection_timestamp DESC LIMIT 1
        """)
        if result and len(result) > 0:
            return result[0].get('run_id') or result[0].get('col0')
        return None
    except Exception as e:
        print(f"Error getting latest run_id: {e}")
        return None


def get_current_run_id():
    """Get run_id from request params, body, or default to latest"""
    global _cached_run_id
    # Check if run_id is in request args (GET parameters)
    run_id = request.args.get('run_id')
    if run_id:
        return run_id
    # Check if run_id is in request body (POST requests)
    if request.is_json:
        data = request.get_json(silent=True)
        if data and data.get('run_id'):
            return data.get('run_id')
    # Use cached run_id if available
    if _cached_run_id:
        return _cached_run_id
    # Otherwise get the latest
    _cached_run_id = get_latest_run_id()
    return _cached_run_id


def get_available_runs(limit=10):
    """Get list of available collection runs"""
    print(f"[DEBUG] get_available_runs called, METADATA_TABLE={METADATA_TABLE}")
    try:
        # Try query with new columns first
        query = f"""
            SELECT run_id,
                   CAST(collection_timestamp AS STRING) as collection_timestamp,
                   vertices_count,
                   edges_count,
                   collected_by,
                   workspaces_collected,
                   workspaces_failed,
                   collection_mode
            FROM {METADATA_TABLE}
            ORDER BY collection_timestamp DESC
            LIMIT {limit}
        """
        print(f"[DEBUG] Executing query: {query[:100]}...")
        result = exec_query_df(query)
        print(f"[DEBUG] Query returned {len(result) if result else 0} rows")
        return result
    except Exception as e:
        print(f"[ERROR] Error getting available runs with new columns: {e}")
        import traceback
        traceback.print_exc()
        # Fall back to basic columns (for backwards compatibility)
        try:
            query2 = f"""
                SELECT run_id,
                       CAST(collection_timestamp AS STRING) as collection_timestamp,
                       vertices_count,
                       edges_count,
                       collected_by
                FROM {METADATA_TABLE}
                ORDER BY collection_timestamp DESC
                LIMIT {limit}
            """
            print(f"[DEBUG] Executing fallback query: {query2[:100]}...")
            result = exec_query_df(query2)
            print(f"[DEBUG] Fallback query returned {len(result) if result else 0} rows")
            return result
        except Exception as e2:
            print(f"[ERROR] Error getting available runs (fallback): {e2}")
            import traceback
            traceback.print_exc()
            return []


def get_collection_coverage(run_id=None):
    """Get workspace coverage information for a collection run"""
    import json
    if not run_id:
        run_id = get_current_run_id()

    if not run_id:
        return None

    try:
        result = exec_query_df(f"""
            SELECT workspaces_collected, workspaces_failed, collection_mode,
                   CAST(collection_timestamp AS STRING) as collection_timestamp,
                   collected_by, vertices_count, edges_count
            FROM {METADATA_TABLE}
            WHERE run_id = '{sanitize(run_id)}'
            LIMIT 1
        """)
        if result and len(result) > 0:
            row = result[0]
            coverage = {
                'collection_mode': row.get('collection_mode', 'unknown'),
                'collection_timestamp': row.get('collection_timestamp'),
                'collected_by': row.get('collected_by'),
                'vertices_count': row.get('vertices_count'),
                'edges_count': row.get('edges_count'),
                'workspaces_collected': [],
                'workspaces_failed': []
            }
            # Parse JSON fields
            if row.get('workspaces_collected'):
                try:
                    coverage['workspaces_collected'] = json.loads(row['workspaces_collected'])
                except:
                    pass
            if row.get('workspaces_failed'):
                try:
                    coverage['workspaces_failed'] = json.loads(row['workspaces_failed'])
                except:
                    pass
            return coverage
        return None
    except Exception as e:
        print(f"Error getting collection coverage with new columns: {e}")
        # Return empty coverage for backwards compatibility
        return {
            'collection_mode': 'unknown',
            'collection_timestamp': None,
            'collected_by': None,
            'vertices_count': None,
            'edges_count': None,
            'workspaces_collected': [],
            'workspaces_failed': []
        }


def sanitize(value):
    """Sanitize string for SQL"""
    if not value:
        return ""
    return str(value).replace("'", "''")


def get_recursive_group_cte(principal_id, principal_email, principal_name, run_id):
    """
    Generate a recursive CTE to expand all group memberships including nested groups.
    Returns the CTE SQL and tracks the inheritance path.

    The CTE produces columns:
    - group_id: The group ID
    - group_name: The group name
    - inheritance_path: Full path showing how access was inherited (e.g., "Group A → Group B → Group C")
    - depth: Nesting level (0 = direct membership)
    """
    safe_id = sanitize(principal_id)
    safe_email = sanitize(principal_email)
    safe_name = sanitize(principal_name)

    return f"""
    all_groups AS (
        -- Level 0: Direct group memberships of the principal
        SELECT
            g.id as group_id,
            g.name as group_name,
            g.name as inheritance_path,
            0 as depth
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON e.dst = g.id AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND (e.src = '{safe_id}' OR e.src = '{safe_email}' OR e.src = '{safe_name}'
               OR e.src LIKE '%:{safe_id}' OR e.src LIKE '%:{safe_email}')
          AND g.node_type IN ('Group', 'AccountGroup')

        UNION ALL

        -- Level 1+: Groups that contain our groups (nested membership)
        SELECT
            parent_g.id as group_id,
            parent_g.name as group_name,
            CONCAT(ag.inheritance_path, ' → ', parent_g.name) as inheritance_path,
            ag.depth + 1 as depth
        FROM all_groups ag
        JOIN {EDGES_TABLE} e ON e.src = ag.group_id AND e.relationship = 'MemberOf' AND e.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} parent_g ON e.dst = parent_g.id AND parent_g.run_id = '{run_id}'
        WHERE parent_g.node_type IN ('Group', 'AccountGroup')
          AND ag.depth < 10  -- Prevent infinite loops, max 10 levels of nesting
    )
    """


def get_principal_identifiers_cte(principal_id, principal_email, principal_name):
    """
    Generate a CTE that lists all identifiers for a principal.
    This handles the fact that edges may reference principals by different IDs.
    """
    safe_id = sanitize(principal_id)
    safe_email = sanitize(principal_email)
    safe_name = sanitize(principal_name)

    return f"""
    principal_ids AS (
        SELECT '{safe_id}' as pid
        UNION SELECT '{safe_email}' WHERE '{safe_email}' != ''
        UNION SELECT '{safe_name}' WHERE '{safe_name}' != ''
    )
    """


def find_principal(identifier, run_id):
    """Find a principal by ID, email, name, or display_name.

    Prioritizes AccountUser over workspace-level User to ensure account-level
    group memberships (which have WorkspaceAccess edges) are found.
    """
    if not identifier:
        return None
    safe_id = sanitize(identifier)
    # Order by node_type to prefer AccountUser/AccountGroup/AccountServicePrincipal
    # These have account-level group memberships with WorkspaceAccess edges
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = '{run_id}'
      AND (id = '{safe_id}'
       OR LOWER(email) = LOWER('{safe_id}')
       OR LOWER(name) = LOWER('{safe_id}')
       OR LOWER(display_name) = LOWER('{safe_id}'))
    AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ORDER BY CASE
        WHEN node_type = 'AccountUser' THEN 1
        WHEN node_type = 'AccountGroup' THEN 2
        WHEN node_type = 'AccountServicePrincipal' THEN 3
        ELSE 4
    END
    LIMIT 1
    """
    results = exec_query_df(query)
    return results[0] if results else None


def find_account_principal(identifier, run_id):
    """Find the account-level version of a principal (AccountUser/AccountGroup/AccountServicePrincipal).

    This is used to resolve workspace access via account-level group memberships.
    """
    if not identifier:
        return None
    safe_id = sanitize(identifier)
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = '{run_id}'
      AND (id = '{safe_id}'
       OR LOWER(email) = LOWER('{safe_id}')
       OR LOWER(name) = LOWER('{safe_id}')
       OR LOWER(display_name) = LOWER('{safe_id}'))
    AND node_type IN ('AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    LIMIT 1
    """
    results = exec_query_df(query)
    return results[0] if results else None


def find_resource(identifier, run_id):
    """Find a resource by ID, name, or display_name"""
    if not identifier:
        return None
    safe_id = sanitize(identifier)
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = '{run_id}'
      AND (id = '{safe_id}'
       OR LOWER(name) = LOWER('{safe_id}')
       OR LOWER(display_name) = LOWER('{safe_id}'))
    AND node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    LIMIT 1
    """
    results = exec_query_df(query)
    return results[0] if results else None


# ============================================================================
# MAIN UI
# ============================================================================

@app.route('/')
def index():
    return get_main_html()


def get_main_html():
    """Generate the main dashboard HTML"""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Permissions Analysis Tool - Security Analysis</title>
    <style>
        :root {
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --bg-input: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --danger: #8b5cf6;
            --warning: #f59e0b;
            --success: #10b981;
            --border: #334155;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* Layout */
        .app-container { display: flex; height: 100vh; }
        .sidebar {
            width: 300px;
            background: linear-gradient(180deg, #1a1d2e 0%, #16182a 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.05);
            padding: 0;
            display: flex;
            flex-direction: column;
            box-shadow: 2px 0 16px rgba(0, 0, 0, 0.1);
            height: 100vh;
            position: sticky;
            top: 0;
        }
        .main-content {
            flex: 1;
            padding: 0;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }

        /* Stats Header Bar */
        .stats-header-bar {
            background: linear-gradient(135deg, #1a1d2e 0%, #16182a 100%);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding: 20px 28px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
        }
        .stats-header-bar.collapsed {
            padding: 12px 28px;
        }
        .stats-header-bar.collapsed .stats-header-container {
            display: none;
        }
        .stats-header-toggle {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .stats-header-bar.collapsed .stats-header-toggle {
            margin-bottom: 0;
        }
        .stats-header-toggle-text {
            font-size: 0.75em;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.5);
            font-weight: 600;
            letter-spacing: 1px;
        }
        .stats-header-toggle-btn {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            padding: 6px 12px;
            color: rgba(255, 255, 255, 0.7);
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85em;
            transition: all 0.2s;
        }
        .stats-header-toggle-btn:hover {
            background: rgba(255, 255, 255, 0.1);
            color: rgba(255, 255, 255, 0.9);
        }
        .stats-header-toggle-btn svg {
            width: 16px;
            height: 16px;
            transition: transform 0.3s;
        }
        .stats-header-bar.collapsed .stats-header-toggle-btn svg {
            transform: rotate(180deg);
        }
        .stats-header-container {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .stats-header-row {
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: nowrap;
        }
        .stats-header-section {
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 12px 16px;
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            transition: all 0.2s;
            flex: 0 0 auto;
        }
        .stats-header-section:hover {
            background: rgba(255, 255, 255, 0.05);
            transform: translateY(-1px);
        }
        .stats-header-label {
            font-size: 0.68em;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.5);
            font-weight: 600;
            letter-spacing: 1px;
            white-space: nowrap;
            margin-bottom: 2px;
        }
        .stats-header-items {
            display: flex;
            gap: 14px;
        }
        .stats-header-item {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 0;
        }
        .stats-icon {
            width: 17px;
            height: 17px;
            color: #a78bfa;
            opacity: 0.8;
            flex-shrink: 0;
        }
        .stats-value {
            font-size: 1.05em;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #c4b5fd 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            white-space: nowrap;
        }
        .stats-label {
            font-size: 0.78em;
            color: rgba(255, 255, 255, 0.6);
            font-weight: 500;
            white-space: nowrap;
        }
        .stats-header-divider {
            width: 1px;
            height: 55px;
            background: linear-gradient(180deg, transparent 0%, rgba(255, 255, 255, 0.1) 50%, transparent 100%);
            flex-shrink: 0;
        }

        /* Sidebar */
        .sidebar-header {
            padding: 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(255, 255, 255, 0.02);
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
            transition: transform 0.2s, opacity 0.2s;
        }
        .logo:hover {
            transform: translateX(4px);
            opacity: 0.8;
        }
        .logo-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }
        .logo-text {
            font-size: 0.95em;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 0%, #c4b5fd 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1.3;
        }

        .sidebar-nav {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .nav-sections-container {
            flex: 0 0 auto;
        }
        .sidebar-spacer {
            flex: 1;
            min-height: 20px;
        }
        .sidebar-nav::-webkit-scrollbar {
            width: 6px;
        }
        .sidebar-nav::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.02);
        }
        .sidebar-nav::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        .sidebar-nav::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        .nav-section {
            margin-bottom: 28px;
        }
        .nav-label {
            font-size: 0.7em;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.4);
            letter-spacing: 1.5px;
            margin-bottom: 12px;
            padding: 0 16px;
            font-weight: 600;
        }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            color: rgba(255, 255, 255, 0.65);
            margin-bottom: 4px;
            font-size: 0.95em;
            position: relative;
        }
        .nav-item::before {
            content: '';
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 3px;
            height: 0;
            background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
            border-radius: 0 3px 3px 0;
            transition: height 0.25s;
        }
        .nav-item:hover {
            background: rgba(255, 255, 255, 0.05);
            color: rgba(255, 255, 255, 0.9);
            transform: translateX(4px);
        }
        .nav-item:hover::before {
            height: 60%;
        }
        .nav-item.active {
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.15) 100%);
            color: #ffffff;
            font-weight: 500;
        }
        .nav-item.active::before {
            height: 100%;
        }
        .nav-item svg {
            width: 20px;
            height: 20px;
            opacity: 0.75;
        }
        .nav-item.active svg {
            opacity: 1;
        }

        .sidebar-footer {
            padding: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(0, 0, 0, 0.2);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
        }
        .stat-mini {
            text-align: center;
            padding: 12px 8px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            transition: all 0.2s;
        }
        .stat-mini:hover {
            background: rgba(255, 255, 255, 0.06);
            transform: translateY(-2px);
        }
        .stat-mini .value {
            font-size: 1.3em;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #c4b5fd 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-mini .label {
            font-size: 0.65em;
            color: rgba(255, 255, 255, 0.5);
            text-transform: uppercase;
            margin-top: 4px;
            letter-spacing: 0.5px;
        }

        /* Main Content */
        .page { 
            display: none;
            padding: 32px;
            flex: 1;
            background: #0f1117;
        }
        .page.active { 
            display: block;
        }

        .card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }

        .page-header {
            margin-bottom: 32px;
        }
        .page-title {
            font-size: 2em;
            font-weight: 700;
            margin-bottom: 8px;
            color: #ffffff;
        }
        .page-desc {
            color: rgba(255, 255, 255, 0.6);
            font-size: 1.1em;
        }

        /* Search Box */
        .search-container {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            position: relative;
        }
        .search-box {
            display: flex;
            gap: 12px;
            align-items: center;
        }
        .search-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 16px 20px;
            font-size: 1.1em;
            color: rgba(255, 255, 255, 0.95);
            transition: all 0.2s;
        }
        .search-input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.2);
            background: rgba(255, 255, 255, 0.08);
        }
        .search-input::placeholder { color: rgba(255, 255, 255, 0.4); }
        
        /* Autocomplete Dropdown */
        .autocomplete-dropdown {
            position: absolute;
            top: calc(100% + 4px);
            left: 0;
            right: 0;
            margin-right: 100px;
            background: var(--bg-card);
            border: 2px solid rgba(102, 126, 234, 0.3);
            border-radius: 12px;
            max-height: 300px;
            overflow-y: auto;
            z-index: 10000;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            display: none;
        }
        .autocomplete-dropdown.show {
            display: block;
        }
        .autocomplete-item {
            padding: 12px 16px;
            cursor: pointer;
            transition: background 0.2s;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .autocomplete-item:last-child {
            border-bottom: none;
        }
        .autocomplete-item:hover {
            background: rgba(102, 126, 234, 0.1);
        }
        .autocomplete-item-name {
            color: rgba(255, 255, 255, 0.9);
            font-weight: 500;
            margin-bottom: 4px;
        }
        .autocomplete-item-email {
            color: rgba(255, 255, 255, 0.6);
            font-size: 0.9em;
        }
        .autocomplete-item-id {
            color: rgba(255, 255, 255, 0.5);
            font-size: 0.85em;
            font-family: 'Courier New', monospace;
            margin-top: 4px;
        }
        .autocomplete-item-type {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 600;
            margin-left: 8px;
            text-transform: uppercase;
        }
        .autocomplete-item-type.user {
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
        }
        .autocomplete-item-type.group {
            background: rgba(139, 92, 246, 0.2);
            color: #a78bfa;
        }
        .autocomplete-item-type.sp {
            background: rgba(236, 72, 153, 0.2);
            color: #f472b6;
        }
        
        .search-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 12px;
            padding: 16px 32px;
            font-size: 1em;
            font-weight: 600;
            color: white;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }
        .search-btn:hover { 
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        .search-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        .search-clear-btn {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 8px;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
            padding: 0;
        }
        .search-clear-btn svg {
            width: 16px;
            height: 16px;
            color: var(--text-muted);
        }
        .search-clear-btn:hover {
            background: rgba(255, 255, 255, 0.15);
        }
        .search-clear-btn:hover svg {
            color: var(--text-primary);
        }

        /* Resource Type Filter */
        .resource-type-filter {
            padding: 8px 16px;
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 0.9em;
            cursor: pointer;
            transition: all 0.2s;
        }
        .resource-type-filter:hover {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%);
            border-color: rgba(59, 130, 246, 0.5);
            transform: translateY(-1px);
        }
        .resource-type-filter:active {
            transform: translateY(0);
        }

        /* Results */
        .results-container {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }
        .results-header {
            padding: 20px 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.02);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .results-title {
            font-size: 1.2em;
            font-weight: 600;
        }
        .results-count {
            background: var(--accent);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .results-body {
            max-height: 500px;
            overflow-y: auto;
        }

        /* Result Cards */
        .result-card {
            padding: 16px 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            gap: 16px;
            transition: all 0.2s;
        }
        .result-card:hover { 
            background: rgba(255, 255, 255, 0.05);
            transform: translateX(4px);
        }
        .result-card:last-child { border-bottom: none; }

        .result-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            flex-shrink: 0;
        }
        .result-icon.user { background: #3b82f620; color: #3b82f6; }
        .result-icon.group { background: #8b5cf620; color: #8b5cf6; }
        .result-icon.sp { background: #f59e0b20; color: #f59e0b; }
        .result-icon.catalog { background: #10b98120; color: #10b981; }
        .result-icon.schema { background: #06b6d420; color: #06b6d4; }
        .result-icon.table { background: #6366f120; color: #6366f1; }
        .result-icon.cluster { background: #ec489920; color: #ec4899; }
        .result-icon.default { background: #64748b20; color: #64748b; }

        .result-info { flex: 1; min-width: 0; }
        .result-name {
            font-weight: 600;
            margin-bottom: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .result-meta {
            font-size: 0.85em;
            color: var(--text-muted);
        }

        .result-badge {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.8em;
            font-weight: 600;
            white-space: nowrap;
        }
        .result-badge.high { background: #3b82f620; color: #3b82f6; }
        .result-badge.medium { background: #3b82f620; color: #3b82f6; }
        .result-badge.low { background: #3b82f620; color: #3b82f6; }

        /* Summary Cards */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .summary-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .summary-value {
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .summary-value.danger { color: var(--danger); }
        .summary-value.warning { color: var(--warning); }
        .summary-value.success { color: var(--success); }
        .summary-value.accent { color: var(--accent); }
        .summary-label {
            font-size: 0.85em;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        /* Loading */
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 48px;
            color: var(--text-muted);
        }
        .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 12px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 48px;
            color: var(--text-muted);
        }
        .empty-state svg {
            width: 64px;
            height: 64px;
            margin-bottom: 16px;
            opacity: 0.5;
        }

        /* Path Visualization */
        .path-viz {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
            padding: 16px 0;
        }
        .path-node {
            background: var(--bg-input);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9em;
        }
        .path-node.start { background: var(--accent); color: white; }
        .path-node.end { background: var(--danger); color: white; }
        .path-arrow {
            color: var(--text-muted);
            font-size: 1.2em;
        }

        /* Graph Visualization */
        .graph-container {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            min-height: 400px;
            position: relative;
        }
        .graph-canvas {
            width: 100%;
            height: 500px;
            background: radial-gradient(circle at center, #1a2744 0%, var(--bg-dark) 100%);
            border-radius: 12px;
            overflow: hidden;
        }
        .graph-canvas svg {
            width: 100%;
            height: 100%;
        }
        .graph-node {
            cursor: pointer;
            transition: transform 0.2s;
        }
        .graph-node:hover {
            transform: scale(1.1);
        }
        .graph-node circle {
            stroke-width: 3;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
        }
        .graph-node text {
            font-size: 11px;
            fill: var(--text-primary);
            text-anchor: middle;
            pointer-events: none;
            font-weight: 500;
        }
        .graph-node .node-label {
            font-size: 10px;
            fill: var(--text-secondary);
        }
        .graph-edge {
            stroke: var(--text-muted);
            stroke-width: 2;
            fill: none;
            opacity: 0.6;
        }
        .graph-edge.highlighted {
            stroke: var(--danger);
            stroke-width: 3;
            opacity: 1;
        }
        .graph-edge-arrow {
            fill: var(--text-muted);
        }
        .graph-edge.highlighted + .graph-edge-arrow,
        .graph-edge-arrow.highlighted {
            fill: var(--danger);
        }
        .graph-legend {
            position: absolute;
            bottom: 16px;
            left: 16px;
            background: var(--bg-input);
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 0.8em;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }
        .legend-item:last-child { margin-bottom: 0; }
        .legend-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .legend-dot.start { background: var(--accent); }
        .legend-dot.intermediate { background: #8b5cf6; }
        .legend-dot.target { background: var(--danger); }
        .legend-dot.unreachable { background: var(--text-muted); }

        /* Risk Meter */
        .risk-meter {
            margin: 24px 0;
        }
        .risk-bar {
            height: 8px;
            background: var(--bg-input);
            border-radius: 4px;
            overflow: hidden;
        }
        .risk-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }
        .risk-fill.critical { background: linear-gradient(90deg, #8b5cf6, #7c3aed); }
        .risk-fill.high { background: linear-gradient(90deg, #f59e0b, #d97706); }
        .risk-fill.medium { background: linear-gradient(90deg, #3b82f6, #2563eb); }
        .risk-fill.low { background: linear-gradient(90deg, #10b981, #059669); }
        .risk-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            font-size: 0.75em;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Sidebar -->
        <aside class="sidebar">
            <!-- Sidebar Header -->
            <div class="sidebar-header">
                <div class="logo" style="cursor: pointer;" data-page="home">
                    <div class="logo-icon">🛡️</div>
                    <div style="display: flex; flex-direction: column; gap: 4px;">
                        <span class="logo-text">Principal and Resource Permissions Analysis Tool (Experimental)</span>
                        <div style="font-size: 0.65em; color: #d32f2f; line-height: 1.2;">
                            <strong>⚠️ Note:</strong> May have incomplete data. Outputs are visibility/audit aids, not authoritative compliance determinations.
                        </div>
                    </div>
                </div>
            </div>

            <!-- Sidebar Navigation -->
            <nav class="sidebar-nav">
                <div class="nav-sections-container">
                    <div class="nav-section">
                        <div class="nav-label">🔍 Analysis Tools</div>
                        <div class="nav-item" data-page="principal">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                            Principal Analysis
                        </div>
                        <div class="nav-item" data-page="resource">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                            Resource Analysis
                        </div>
                        <div class="nav-item" data-page="paths">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
                            Escalation Paths
                        </div>
                        <div class="nav-item" data-page="impersonation">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                            Impersonation
                        </div>
                    </div>

                    <div class="nav-section">
                        <div class="nav-label">📊 Security Reports</div>
                        <div class="nav-item" data-page="highprivilege">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                            High Privilege
                        </div>
                        <div class="nav-item" data-page="isolated">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                            Isolated Principals
                        </div>
                        <div class="nav-item" data-page="orphaned">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                            Orphaned Resources
                        </div>
                        <div class="nav-item" data-page="overprivileged">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>
                            Over-Privileged
                        </div>
                        <div class="nav-item" data-page="secretscopes">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                            Secret Scope Access
                        </div>
                    </div>
                </div>
                
                <!-- Spacer to push footer to bottom -->
                <div class="sidebar-spacer"></div>
                
                <!-- Optional footer info -->
                <div style="padding: 20px; border-top: 1px solid rgba(255, 255, 255, 0.05); background: rgba(0, 0, 0, 0.1); font-size: 0.75em; color: rgba(255, 255, 255, 0.4); text-align: center;">
                    <a href="https://www.databricks.com/trust" target="_blank" rel="noopener noreferrer" style="color: rgba(102, 126, 234, 0.8); text-decoration: none; font-size: 1em; transition: color 0.2s; white-space: nowrap; display: inline-block;" onmouseover="this.style.color='rgba(102, 126, 234, 1)'" onmouseout="this.style.color='rgba(102, 126, 234, 0.8)'">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 14px; height: 14px; vertical-align: middle; margin-right: 4px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        Databricks Security & Trust Center
                    </a>
                </div>
            </nav>
        </aside>

        <!-- Main Content -->
        <main class="main-content">
            <!-- Inline script to prevent flash - runs immediately before page renders -->
            <script>
                (function() {
                    const hash = window.location.hash.substring(1);
                    if (hash) {
                        // Hide home page and activate the correct page immediately
                        document.addEventListener('DOMContentLoaded', function() {
                            const homePage = document.getElementById('page-home');
                            const targetPage = document.getElementById('page-' + hash);
                            const targetNav = document.querySelector('.nav-item[data-page="' + hash + '"]');
                            
                            if (targetPage && homePage !== targetPage) {
                                homePage.classList.remove('active');
                                targetPage.classList.add('active');
                                if (targetNav) {
                                    targetNav.classList.add('active');
                                }
                            }
                        });
                    }
                })();
            </script>
            
            <!-- Stats Header Bar -->
            <div class="stats-header-bar" id="stats-header-bar">
                <div class="stats-header-toggle">
                    <span class="stats-header-toggle-text">Environment Overview and Metrics</span>
                    <button class="stats-header-toggle-btn" onclick="toggleStatsHeader()">
                        <span id="stats-toggle-text">Collapse</span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 15l-6-6-6 6"/>
                        </svg>
                    </button>
                </div>
                <div class="stats-header-container">
                    <!-- Simplified Row: Data Collection and Workspaces -->
                    <div class="stats-header-row">
                        <!-- Data Collection Date & Time -->
                        <div class="stats-header-section" style="flex: 1;">
                            <span class="stats-header-label">Data Collection Date & Time</span>
                            <select id="header-run-selector" onchange="selectRun(this.value)" style="padding: 6px 10px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.9em; cursor: pointer; width: 100%; max-width: 320px; overflow: visible;">
                                <option value="">Loading runs...</option>
                            </select>
                        </div>
                        <div class="stats-header-divider"></div>
                        <!-- Workspaces in this Report -->
                        <div class="stats-header-section" style="flex: 2;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span class="stats-header-label">Workspaces in this Report</span>
                                <button id="workspace-toggle-btn" onclick="toggleWorkspaceList()" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 0.85em; padding: 4px 8px; display: none;">
                                    <span id="workspace-toggle-text">Show</span>
                                    <svg id="workspace-toggle-icon" style="width: 14px; height: 14px; display: inline-block; vertical-align: middle; margin-left: 4px; transition: transform 0.2s;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M6 9l6 6 6-6"/>
                                    </svg>
                                </button>
                            </div>
                            <div style="display: flex; align-items: center; gap: 14px; margin-top: 8px;">
                                <div id="header-coverage-collected" style="color: #10b981; font-size: 0.9em;"></div>
                                <div id="header-coverage-failed" style="color: #ef4444; font-size: 0.9em;"></div>
                            </div>
                            <div id="workspace-list-container" style="display: none; margin-top: 12px; max-height: 200px; overflow-y: auto; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; padding: 10px;">
                                <div id="workspace-list" style="font-size: 0.85em; color: var(--text-secondary);"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Home/About Page -->
            <div class="page active" id="page-home">
                <div class="page-header" style="text-align: center; margin-bottom: 18px;">
                    <h1 class="page-title" style="margin-bottom: 6px; font-size: 1.8em;">🛡️ Principal and Resource Permissions Analysis Tool</h1>
                </div>

                <div class="card" style="padding: 20px;">
                    <h2 style="font-size: 1.2em; margin-bottom: 10px; color: var(--primary);">What is the Principal and Resource Permissions Analysis Tool?</h2>
                    <p style="line-height: 1.45; color: var(--text-secondary); margin-bottom: 13px; font-size: 0.92em;">
                        The Principal and Resource Permissions Analysis Tool is a graph-based security analysis platform for Databricks environments.
                        It helps to discover privilege escalation paths, identify over-privileged principals,
                        and understand complex permission relationships across workspace(s).
                    </p>
                    
                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">🎯 Key Features</h3>
                    <ul style="line-height: 1.5; color: var(--text-secondary); list-style-position: inside; margin-bottom: 13px; font-size: 0.88em;">
                        <li><strong>Principal Analysis</strong> - Discover what a user, group, or service principal can access</li>
                        <li><strong>Resource Analysis</strong> - Find all principals with access to specific resources</li>
                        <li><strong>Escalation Paths</strong> - Identify potential privilege escalation routes</li>
                        <li><strong>Impersonation Analysis</strong> - See who can impersonate whom</li>
                        <li><strong>Security Reports</strong> - Pre-built reports for common security concerns</li>
                    </ul>

                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">🚀 Getting Started</h3>
                    
                    <!-- Environment Overview Instructions -->
                    <div style="padding: 13px; background: linear-gradient(135deg, rgba(16, 185, 129, 0.05) 0%, rgba(16, 185, 129, 0.02) 100%); border: 2px solid rgba(16, 185, 129, 0.2); border-radius: 10px; margin-bottom: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <div style="display: flex; align-items: center; gap: 9px; margin-bottom: 7px;">
                            <div style="width: 30px; height: 30px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 15px;">
                                📈
                            </div>
                            <div style="font-size: 0.9em; font-weight: 700; color: var(--text-primary);">Environment Overview & Metrics</div>
                        </div>
                        <p style="color: var(--text-secondary); font-size: 0.82em; line-height: 1.35; margin: 0 0 0 39px;">
                            The top header bar shows the Databricks environment overview, metrics, and workspace coverage. Use the <strong>Data Collection</strong> dropdown to switch between different collection runs and view historical data.
                        </p>
                    </div>
                    
                    <p style="line-height: 1.45; color: var(--text-secondary); margin-bottom: 13px; font-size: 0.9em;">
                        Use the navigation menu on the left to explore different analysis capabilities:
                    </p>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 13px; margin-top: 13px;">
                        <div style="padding: 16px; background: linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(59, 130, 246, 0.02) 100%); border: 2px solid rgba(59, 130, 246, 0.2); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <div style="display: flex; align-items: center; gap: 11px; margin-bottom: 9px;">
                                <div style="width: 38px; height: 38px; background: linear-gradient(135deg, var(--primary) 0%, #2563eb 100%); border-radius: 9px; display: flex; align-items: center; justify-content: center; font-size: 20px;">
                                    🔍
                                </div>
                                <div>
                                    <div style="font-size: 0.95em; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;">Analysis Tools</div>
                                    <div style="font-size: 0.68em; color: var(--primary); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Interactive</div>
                                </div>
                            </div>
                            <p style="color: var(--text-secondary); font-size: 0.86em; line-height: 1.35; margin: 0;">
                                Investigate principals, resources, and permission paths with interactive search tools
                            </p>
                        </div>
                        <div style="padding: 16px; background: linear-gradient(135deg, rgba(139, 92, 246, 0.05) 0%, rgba(139, 92, 246, 0.02) 100%); border: 2px solid rgba(139, 92, 246, 0.2); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                            <div style="display: flex; align-items: center; gap: 11px; margin-bottom: 9px;">
                                <div style="width: 38px; height: 38px; background: linear-gradient(135deg, var(--danger) 0%, #7c3aed 100%); border-radius: 9px; display: flex; align-items: center; justify-content: center; font-size: 20px;">
                                    📊
                                </div>
                                <div>
                                    <div style="font-size: 0.95em; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;">Security Reports</div>
                                    <div style="font-size: 0.68em; color: var(--danger); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Pre-built</div>
                                </div>
                            </div>
                            <p style="color: var(--text-secondary); font-size: 0.86em; line-height: 1.35; margin: 0;">
                                View pre-generated security insights, risks, and comprehensive audit reports
                            </p>
                        </div>
                    </div>

                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">💡 Tips</h3>
                    <ul style="line-height: 1.5; color: var(--text-secondary); list-style-position: inside; margin-bottom: 0; font-size: 0.88em;">
                        <li>Use email addresses, names, or IDs when searching for principals</li>
                        <li>For resources, use the full namespace/path (e.g., catalog.schema.table)</li>
                        <li>Click on principals or resources in results to navigate to detailed analysis</li>
                        <li>Reports auto-load when you navigate to them</li>
                    </ul>
                </div>
            </div>

            <!-- Principal Analysis Page -->
            <div class="page" id="page-principal">
                <div class="page-header">
                    <h1 class="page-title">Principal Analysis</h1>
                    <p class="page-desc">Analyze what a user, group, or service principal can access</p>
                </div>

                <!-- Input Section: Search and Browse -->
                <div style="margin: 20px 0; padding: 20px; background: var(--bg-input); border-radius: 12px; border: 1px solid var(--border-color);">
                    <div class="search-container" style="margin: 0;">
                        <div class="search-box">
                            <div style="flex: 1; position: relative;">
                                <input type="text" class="search-input" id="principal-search"
                                       placeholder="Search by name, user email, group, or service principal..."
                                       autocomplete="off">
                                <button class="search-clear-btn" id="principal-clear-btn" onclick="clearPrincipalSearch()" style="display: none;" title="Clear search">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <line x1="18" y1="6" x2="6" y2="18"></line>
                                        <line x1="6" y1="6" x2="18" y2="18"></line>
                                    </svg>
                                </button>
                                <div class="autocomplete-dropdown" id="principal-autocomplete"></div>
                            </div>
                            <button class="search-btn" onclick="analyzePrincipal()">Analyze</button>
                        </div>
                    </div>

                    <!-- Principal Type Filter -->
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                            <span style="font-size: 0.9em; color: var(--text-secondary); font-weight: 600;">Or Browse and Select by Type:</span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            <button class="resource-type-filter" data-type="User" onclick="browsePrincipalsByType('User')">Users</button>
                            <button class="resource-type-filter" data-type="Group" onclick="browsePrincipalsByType('Group')">Groups</button>
                            <button class="resource-type-filter" data-type="ServicePrincipal" onclick="browsePrincipalsByType('ServicePrincipal')">Service Principals</button>
                        </div>
                    </div>
                </div>

                <div id="principal-results"></div>
            </div>

            <!-- Resource Analysis Page -->
            <div class="page" id="page-resource">
                <div class="page-header">
                    <h1 class="page-title">Resource Analysis</h1>
                    <p class="page-desc">Find all principals that have access to a specific resource</p>
                </div>

                <!-- Input Section: Search and Browse -->
                <div style="margin: 20px 0; padding: 20px; background: var(--bg-input); border-radius: 12px; border: 1px solid var(--border-color);">
                    <div class="search-container" style="margin: 0;">
                        <div class="search-box">
                            <div style="flex: 1; position: relative;">
                                <input type="text" class="search-input" id="resource-search"
                                       placeholder="Search by resource name such as catalog, schema, table, cluster, warehouse, or job name..."
                                       autocomplete="off">
                                <button class="search-clear-btn" id="resource-clear-btn" onclick="clearResourceSearch()" style="display: none;" title="Clear search">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <line x1="18" y1="6" x2="6" y2="18"></line>
                                        <line x1="6" y1="6" x2="18" y2="18"></line>
                                    </svg>
                                </button>
                                <div class="autocomplete-dropdown" id="resource-autocomplete"></div>
                            </div>
                            <button class="search-btn" onclick="analyzeResource()">Analyze</button>
                        </div>
                    </div>

                    <!-- Resource Type Filter -->
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
                        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                            <span style="font-size: 0.9em; color: var(--text-secondary); font-weight: 600;">Or Browse and Select by Type:</span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            <button class="resource-type-filter" data-type="Catalog" onclick="browseResourcesByType('Catalog')">Catalogs</button>
                            <button class="resource-type-filter" data-type="Schema" onclick="browseResourcesByType('Schema')">Schemas</button>
                            <button class="resource-type-filter" data-type="Table" onclick="browseResourcesByType('Table')">Tables</button>
                            <button class="resource-type-filter" data-type="View" onclick="browseResourcesByType('View')">Views</button>
                            <button class="resource-type-filter" data-type="Volume" onclick="browseResourcesByType('Volume')">Volumes</button>
                            <button class="resource-type-filter" data-type="Function" onclick="browseResourcesByType('Function')">Functions</button>
                            <button class="resource-type-filter" data-type="Cluster" onclick="browseResourcesByType('Cluster')">Clusters</button>
                            <button class="resource-type-filter" data-type="Job" onclick="browseResourcesByType('Job')">Jobs</button>
                            <button class="resource-type-filter" data-type="Warehouse" onclick="browseResourcesByType('Warehouse')">Warehouses</button>
                            <button class="resource-type-filter" data-type="ServingEndpoint" onclick="browseResourcesByType('ServingEndpoint')">Endpoints</button>
                            <button class="resource-type-filter" data-type="SecretScope" onclick="browseResourcesByType('SecretScope')">Secrets</button>
                        </div>
                    </div>
                </div>

                <div id="resource-results"></div>
            </div>

            <!-- Escalation Paths Page -->
            <div class="page" id="page-paths">
                <div class="page-header">
                    <h1 class="page-title">Escalation Paths</h1>
                    <p class="page-desc">Find paths from a principal to admin or privileged groups</p>
                </div>

                <div class="search-container">
                    <div class="search-box">
                        <div style="flex: 1; position: relative;">
                            <input type="text" class="search-input" id="paths-search"
                                   placeholder="Search by name, user email, group, or service principal..."
                                   autocomplete="off">
                            <button class="search-clear-btn" id="paths-clear-btn" onclick="clearPathsSearch()" style="display: none;" title="Clear search">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <line x1="18" y1="6" x2="6" y2="18"></line>
                                    <line x1="6" y1="6" x2="18" y2="18"></line>
                                </svg>
                            </button>
                            <div class="autocomplete-dropdown" id="paths-autocomplete"></div>
                        </div>
                        <button class="search-btn" onclick="findPaths()">Find Paths</button>
                    </div>
                </div>

                <!-- Principal Type Filter -->
                <div style="margin: 20px 0; padding: 16px; background: var(--bg-input); border-radius: 12px;">
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                        <span style="font-size: 0.9em; color: var(--text-secondary); font-weight: 600;">Browse by Type:</span>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                        <button class="resource-type-filter" data-type="User" onclick="browsePathsPrincipalsByType('User')">Users</button>
                        <button class="resource-type-filter" data-type="Group" onclick="browsePathsPrincipalsByType('Group')">Groups</button>
                        <button class="resource-type-filter" data-type="ServicePrincipal" onclick="browsePathsPrincipalsByType('ServicePrincipal')">Service Principals</button>
                    </div>
                </div>

                <div id="paths-results"></div>
            </div>

            <!-- Impersonation Analysis Page -->
            <div class="page" id="page-impersonation">
                <div class="page-header">
                    <h1 class="page-title">Impersonation Analysis</h1>
                    <p class="page-desc">Discover how one entity can impersonate another through various attack paths</p>
                </div>

                <div style="background: var(--bg-input); border-radius: 12px; padding: 20px; margin-bottom: 16px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px;">
                        <div>
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 8px;">Source Type</label>
                            <select id="impersonate-source-type" class="search-input" style="width: 100%;" onchange="loadSourcePrincipals()">
                                <option value="User">User</option>
                                <option value="Group">Group</option>
                                <option value="ServicePrincipal">Service Principal</option>
                            </select>
                        </div>
                        <div>
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 8px;">Target Type</label>
                            <select id="impersonate-target-type" class="search-input" style="width: 100%;" onchange="loadTargetPrincipals()">
                                <option value="User">User</option>
                                <option value="Group">Group</option>
                                <option value="ServicePrincipal">Service Principal</option>
                            </select>
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px;">
                        <div>
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 8px;">Source</label>
                            <input type="text" id="impersonate-source" class="search-input" style="width: 100%;" placeholder="Enter source email/name or select from list">
                            <select id="impersonate-source-select" class="search-input" style="width: 100%; margin-top: 8px; display: none;"></select>
                        </div>
                        <div>
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 8px;">Target</label>
                            <input type="text" id="impersonate-target" class="search-input" style="width: 100%;" placeholder="Enter target email/name or select from list">
                            <select id="impersonate-target-select" class="search-input" style="width: 100%; margin-top: 8px; display: none;"></select>
                        </div>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 8px;">Analysis Type</label>
                        <div style="display: flex; gap: 20px;">
                            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                <input type="radio" name="analysis-type" value="all" checked>
                                <span>🔀 All Paths (1-5 hops)</span>
                                <span style="font-size: 0.8em; color: var(--text-muted);">Shows every possible attack route</span>
                            </label>
                            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                                <input type="radio" name="analysis-type" value="shortest">
                                <span>⚡ Shortest Path (1-10 hops)</span>
                                <span style="font-size: 0.8em; color: var(--text-muted);">Finds the most direct route</span>
                            </label>
                        </div>
                    </div>
                    <button class="search-btn" onclick="runImpersonationAnalysis()">▶ Run Analysis</button>
                </div>

                <div id="impersonation-results"></div>
            </div>

            <!-- Isolated Principals Report Page -->
            <div class="page" id="page-isolated">
                <div class="page-header">
                    <h1 class="page-title">Isolated Principals</h1>
                    <p class="page-desc">Principals with minimal connections - may be orphaned accounts or misconfigured users</p>
                </div>
                <div id="isolated-results"></div>
            </div>

            <!-- Orphaned Resources Report Page -->
            <div class="page" id="page-orphaned">
                <div class="page-header">
                    <h1 class="page-title">Orphaned Resources</h1>
                    <p class="page-desc">Resources with no explicit permission grants - may need access controls</p>
                </div>
                <div id="orphaned-results"></div>
            </div>

            <!-- Over-Privileged Principals Report Page -->
            <div class="page" id="page-overprivileged">
                <div class="page-header">
                    <h1 class="page-title">Over-Privileged Principals</h1>
                    <p class="page-desc">Principals with excessive permissions across the environment</p>
                </div>
                <div id="overprivileged-results"></div>
            </div>

            <!-- High Privilege Principals Report Page -->
            <div class="page" id="page-highprivilege">
                <div class="page-header">
                    <h1 class="page-title">High Privilege Principals</h1>
                    <p class="page-desc">Principals with admin-level privileges via direct or nested group membership</p>
                </div>
                <div id="highprivilege-results"></div>
            </div>

            <!-- Secret Scope Access Report Page -->
            <div class="page" id="page-secretscopes">
                <div class="page-header">
                    <h1 class="page-title">Secret Scope Access</h1>
                    <p class="page-desc">Principals with access to secret scopes - who can read, write, or manage secrets</p>
                </div>

                <!-- Filters -->
                <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                    <div style="display: flex; gap: 16px; align-items: end; flex-wrap: wrap;">
                        <div style="flex: 1; min-width: 200px;">
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 6px;">Workspace</label>
                            <select id="secretscope-workspace-filter" onchange="onSecretScopeWorkspaceChange()" style="width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-input); color: var(--text-primary); font-size: 0.95em;">
                                <option value="">All Workspaces</option>
                            </select>
                        </div>
                        <div style="flex: 1; min-width: 200px;">
                            <label style="display: block; font-size: 0.85em; color: var(--text-secondary); margin-bottom: 6px;">Secret Scope</label>
                            <select id="secretscope-scope-filter" onchange="loadSecretScopeAccess()" style="width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-input); color: var(--text-primary); font-size: 0.95em;">
                                <option value="">All Scopes</option>
                            </select>
                        </div>
                        <button onclick="clearSecretScopeFilters()" style="padding: 10px 16px; background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; color: var(--text-secondary); cursor: pointer; font-size: 0.9em;">
                            Clear Filters
                        </button>
                    </div>
                </div>

                <div id="secretscopes-results"></div>
            </div>
        </main>
    </div>

    <script>
        // Current run_id state
        let currentRunId = null;

        // Track current page and loaded reports
        let currentPage = 'dashboard';
        const reportPages = ['isolated', 'orphaned', 'overprivileged', 'highprivilege', 'secretscopes'];
        const analysisPages = ['principal', 'resource', 'paths', 'risk', 'impersonation'];

        // Track which analyses have been performed (so we can refresh on run change)
        let lastAnalysis = {
            principal: null,  // stores last search term
            resource: null,
            paths: null,
            risk: null
        };

        // Logo click handler - navigate to home page
        document.querySelector('.logo').addEventListener('click', () => {
            navigateToPage('home');
        });

        // Navigation with auto-load for reports
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                navigateToPage(page);
            });
        });

        // Function to navigate to a page and update URL hash
        function navigateToPage(page) {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            
            // Activate the correct nav item (if not home page)
            if (page !== 'home') {
                const navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
                if (navItem) navItem.classList.add('active');
            }
            
            // Show the page
            document.getElementById('page-' + page).classList.add('active');
            currentPage = page;
            
            // Update URL hash
            window.location.hash = page;

            // Auto-load reports when navigating to report pages
            if (page === 'isolated') loadIsolatedPrincipals();
            else if (page === 'orphaned') loadOrphanedResources();
            else if (page === 'overprivileged') loadOverPrivileged();
            else if (page === 'highprivilege') loadHighPrivilege();
            else if (page === 'secretscopes') loadSecretScopeAccess();
            else if (page === 'impersonation') {
                // Load principals for both dropdowns
                loadSourcePrincipals();
                loadTargetPrincipals();
            }
        }

        // Handle browser back/forward buttons
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash.substring(1) || 'home';
            if (document.getElementById(`page-${hash}`)) {
                navigateToPage(hash);
            }
        });

        // Load available runs on page load
        async function loadRuns() {
            try {
                const res = await fetch('/api/runs');
                const data = await res.json();
                const headerSelector = document.getElementById('header-run-selector');

                if (!headerSelector) {
                    console.error('Header run selector not found');
                    return;
                }

                if (data.runs && data.runs.length > 0) {
                    const optionsHTML = data.runs.map(run => {
                        const ts = new Date(run.collection_timestamp);
                        const formatted = ts.toLocaleString('en-US', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        });
                        const vertices = run.vertices_count || 0;
                        return `<option value="${run.run_id}">${formatted} (${vertices} nodes)</option>`;
                    }).join('');
                    
                    headerSelector.innerHTML = optionsHTML;

                    // Set current run_id to the latest (first in list)
                    currentRunId = data.current_run_id || data.runs[0].run_id;
                    headerSelector.value = currentRunId;
                } else {
                    const noDataHTML = '<option value="">No data collected yet</option>';
                    headerSelector.innerHTML = noDataHTML;
                }
            } catch (e) {
                console.error('Error loading runs:', e);
                const headerSelector = document.getElementById('header-run-selector');
                if (headerSelector) {
                    headerSelector.innerHTML = '<option value="">Error loading runs</option>';
                }
            }
        }

        // Handle run selection change
        function selectRun(runId) {
            if (runId && runId !== currentRunId) {
                currentRunId = runId;
                
                // Update header dropdown value
                const headerSelector = document.getElementById('header-run-selector');
                if (headerSelector) headerSelector.value = runId;
                
                // Reset cached filter data (will reload on next page visit)
                secretScopeFilterData = { workspaces: [], scopes: [] };

                // Refresh dashboard stats
                loadStats();

                // Auto-refresh current report page if on one
                if (currentPage === 'isolated') loadIsolatedPrincipals();
                else if (currentPage === 'orphaned') loadOrphanedResources();
                else if (currentPage === 'overprivileged') loadOverPrivileged();
                else if (currentPage === 'highprivilege') loadHighPrivilege();
                else if (currentPage === 'secretscopes') { clearSecretScopeFilters(); }

                // Auto-refresh analysis if user has previously performed one
                if (lastAnalysis.principal) analyzePrincipal();
                if (lastAnalysis.resource) analyzeResource();
                if (lastAnalysis.paths) findPaths();
                if (lastAnalysis.risk) assessRisk();
            }
        }

        // Helper to build URL with run_id
        function apiUrl(endpoint) {
            const url = new URL(endpoint, window.location.origin);
            if (currentRunId) {
                url.searchParams.set('run_id', currentRunId);
            }
            return url.toString();
        }

        // Load stats for current run
        async function loadStats() {
            try {
                const res = await fetch(apiUrl('/api/stats'));
                const data = await res.json();

                // Collection timestamp (sidebar) - kept for any legacy references
                const timestampEl = document.getElementById('collection-timestamp');
                if (timestampEl && data.collection_timestamp) {
                    const date = new Date(data.collection_timestamp);
                    const formatted = date.toLocaleString('en-US', {
                        month: 'short', day: 'numeric', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                    });
                    timestampEl.innerHTML = `<strong>${formatted}</strong>`;
                } else if (timestampEl) {
                    timestampEl.textContent = 'Not available';
                }

                // Workspace coverage (header)
                const headerCoverageCollected = document.getElementById('header-coverage-collected');
                const headerCoverageFailed = document.getElementById('header-coverage-failed');
                const workspaceList = document.getElementById('workspace-list');
                const workspaceToggleBtn = document.getElementById('workspace-toggle-btn');

                // Store workspace data globally for toggle function
                window.workspaceData = {
                    collected: data.workspaces_collected || [],
                    failed: data.workspaces_failed || []
                };

                if (headerCoverageCollected) {
                    if (data.workspaces_collected && data.workspaces_collected.length > 0) {
                        headerCoverageCollected.innerHTML = `✓ ${data.workspaces_collected.length} workspace${data.workspaces_collected.length > 1 ? 's' : ''} collected`;
                        if (workspaceToggleBtn) {
                            workspaceToggleBtn.style.display = 'block';
                        }
                    } else {
                        headerCoverageCollected.textContent = 'No workspaces collected';
                    }
                }

                if (headerCoverageFailed) {
                    if (data.workspaces_failed && data.workspaces_failed.length > 0) {
                        headerCoverageFailed.innerHTML = `⚠ ${data.workspaces_failed.length} failed`;
                    } else {
                        headerCoverageFailed.textContent = '';
                    }
                }

                // Populate workspace list
                if (workspaceList && window.workspaceData) {
                    let listHTML = '';
                    if (window.workspaceData.collected.length > 0) {
                        listHTML += '<div style="margin-bottom: 8px; color: #10b981; font-weight: 600;">✓ Collected:</div>';
                        listHTML += '<div style="margin-left: 12px; margin-bottom: 12px;">';
                        window.workspaceData.collected.forEach(ws => {
                            listHTML += `<div style="padding: 4px 0; border-bottom: 1px solid var(--border-color);">${ws}</div>`;
                        });
                        listHTML += '</div>';
                    }
                    if (window.workspaceData.failed.length > 0) {
                        listHTML += '<div style="margin-bottom: 8px; color: #ef4444; font-weight: 600;">⚠ Failed:</div>';
                        listHTML += '<div style="margin-left: 12px;">';
                        window.workspaceData.failed.forEach(ws => {
                            listHTML += `<div style="padding: 4px 0; border-bottom: 1px solid var(--border-color);">${ws}</div>`;
                        });
                        listHTML += '</div>';
                    }
                    workspaceList.innerHTML = listHTML;
                }
            } catch (e) { console.error(e); }
        }

        // Toggle stats header collapse/expand
        function toggleStatsHeader() {
            const statsBar = document.getElementById('stats-header-bar');
            const toggleText = document.getElementById('stats-toggle-text');

            if (statsBar.classList.contains('collapsed')) {
                statsBar.classList.remove('collapsed');
                toggleText.textContent = 'Collapse';
            } else {
                statsBar.classList.add('collapsed');
                toggleText.textContent = 'Expand';
            }
        }

        // Toggle workspace list visibility
        function toggleWorkspaceList() {
            const container = document.getElementById('workspace-list-container');
            const toggleText = document.getElementById('workspace-toggle-text');
            const toggleIcon = document.getElementById('workspace-toggle-icon');

            if (container.style.display === 'none') {
                container.style.display = 'block';
                toggleText.textContent = 'Hide';
                toggleIcon.style.transform = 'rotate(180deg)';
            } else {
                container.style.display = 'none';
                toggleText.textContent = 'Show';
                toggleIcon.style.transform = 'rotate(0deg)';
            }
        }

        // Initialize - load runs first, then stats
        async function initApp() {
            await loadRuns();
            loadStats();
            
            // Restore page from URL hash, default to home
            const hash = window.location.hash.substring(1);
            if (hash && document.getElementById(`page-${hash}`)) {
                navigateToPage(hash);
            } else {
                navigateToPage('home');
            }
        }
        initApp();

        // Icon helper
        function getIcon(type) {
            const icons = {
                'User': 'user', 'AccountUser': 'user',
                'Group': 'group', 'AccountGroup': 'group',
                'ServicePrincipal': 'sp', 'AccountServicePrincipal': 'sp',
                'Catalog': 'catalog', 'Schema': 'schema', 'Table': 'table', 'View': 'table',
                'Cluster': 'cluster', 'Job': 'cluster', 'Warehouse': 'cluster'
            };
            return icons[type] || 'default';
        }

        function getEmoji(type) {
            const emojis = {
                'User': '👤', 'AccountUser': '👤',
                'Group': '👥', 'AccountGroup': '👥',
                'ServicePrincipal': '🤖', 'AccountServicePrincipal': '🤖', 'Service Principal': '🤖',
                'Catalog': '📦', 'Schema': '📁', 'Table': '📊', 'View': '👁',
                'Cluster': '⚡', 'Job': '⏱', 'Warehouse': '🏭',
                'ServingEndpoint': '🚀', 'SecretScope': '🔐'
            };
            return emojis[type] || '📄';
        }

        function getBadgeClass(perm) {
            return 'low';  // Neutral styling for all permissions
        }

        // Format principal name with identifier for uniqueness
        // Shows "Display Name (email)" or "Display Name (name)" to distinguish principals with same display name
        function formatPrincipalName(displayName, email, name, id) {
            const display = displayName || name || email || id || 'Unknown';
            const identifier = email || name || id;
            // If display name is different from identifier, show both
            if (identifier && display.toLowerCase() !== identifier.toLowerCase()) {
                return `${display} (${identifier})`;
            }
            return display;
        }

        function showLoading(containerId) {
            document.getElementById(containerId).innerHTML = `
                <div class="results-container">
                    <div class="loading"><div class="spinner"></div>Analyzing...</div>
                </div>`;
        }

        function showEmpty(containerId, message) {
            document.getElementById(containerId).innerHTML = `
                <div class="results-container">
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
                        </svg>
                        <p>${message}</p>
                    </div>
                </div>`;
        }

        // Navigate to Principal Analysis page with pre-filled principal
        function navigateToPrincipalAnalysis(principalIdentifier) {
            // Switch to principal analysis page
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            const navItem = document.querySelector('.nav-item[data-page="principal"]');
            if (navItem) navItem.classList.add('active');
            document.getElementById('page-principal').classList.add('active');
            currentPage = 'principal';

            // Set the search field and trigger analysis
            const searchField = document.getElementById('principal-search');
            if (searchField) {
                searchField.value = decodeURIComponent(principalIdentifier);
                analyzePrincipal();
            }
        }

        // Navigate to Escalation Paths page with pre-filled principal
        function navigateToEscalation(principalIdentifier) {
            // Switch to escalation paths page
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            const navItem = document.querySelector('.nav-item[data-page="paths"]');
            if (navItem) navItem.classList.add('active');
            document.getElementById('page-paths').classList.add('active');
            currentPage = 'paths';

            // Set the search field and trigger analysis
            const searchField = document.getElementById('paths-search');
            if (searchField) {
                searchField.value = decodeURIComponent(principalIdentifier);
                findPaths();
            }
        }

        // Navigate to Resource Analysis page with pre-filled resource
        function navigateToResourceAnalysis(resourceIdentifier) {
            // Switch to resource analysis page
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            const navItem = document.querySelector('.nav-item[data-page="resource"]');
            if (navItem) navItem.classList.add('active');
            document.getElementById('page-resource').classList.add('active');
            currentPage = 'resource';

            // Set the search field and trigger analysis
            const searchField = document.getElementById('resource-search');
            if (searchField) {
                searchField.value = decodeURIComponent(resourceIdentifier);
                analyzeResource();
            }
        }

        // Principal Analysis
        async function analyzePrincipal() {
            const searchInput = document.getElementById('principal-search');
            const query = searchInput.value.trim();
            if (!query) return;

            // Use the stored identifier if available (from autocomplete), otherwise use the input value
            const identifier = searchInput.dataset.identifier || query;
            lastAnalysis.principal = identifier;  // Track for auto-refresh
            showLoading('principal-results');

            try {
                const res = await fetch('/api/what-can-access', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal: identifier, resource_type: 'All', run_id: currentRunId})
                });
                const result = await res.json();

                if (!result.success) {
                    showEmpty('principal-results', result.message);
                    return;
                }

                const data = result.data || [];

                // Get principal info from the result
                const principalInfo = result.principal_info || {};
                const principalName = principalInfo.name || query;
                const principalDisplayName = principalInfo.display_name || principalName;
                const principalEmail = principalInfo.email || '';
                const principalId = principalInfo.id || '';
                const principalType = principalInfo.type || '';
                const memberCount = principalInfo.member_count || 0;
                const isGroup = principalType === 'Group' || principalType === 'AccountGroup';
                const isServicePrincipal = principalType.includes('ServicePrincipal');

                // Group by resource type, then by resource name, collecting privileges and inheritance paths
                const byType = {};
                data.forEach(d => {
                    const t = d.resource_type || 'Other';
                    const name = d.resource_name || d.resource_id;
                    if (!byType[t]) byType[t] = {};
                    if (!byType[t][name]) byType[t][name] = { privileges: [], grant_types: new Set(), inheritance_paths: [] };
                    byType[t][name].privileges.push(d.permission_level);
                    byType[t][name].grant_types.add(d.grant_type);
                    if (d.inheritance_path) {
                        byType[t][name].inheritance_paths.push(d.inheritance_path);
                    }
                });

                // Count unique resources per type
                const typeCounts = {};
                for (const [type, resources] of Object.entries(byType)) {
                    typeCounts[type] = Object.keys(resources).length;
                }
                const uniqueResourcesCount = Object.values(typeCounts).reduce((a, b) => a + b, 0);

                // Count by access type from summary (returned by API)
                const summary = result.summary || {};
                const directCount = summary.direct || 0;
                const groupCount = summary.via_groups || 0;
                const ownershipCount = summary.via_ownership || 0;
                const parentCount = summary.via_parent || 0;

                // Get type icon and label
                const getTypeInfo = (type) => {
                    if (type === 'User' || type === 'AccountUser') return { icon: '👤', label: 'User' };
                    if (type === 'Group' || type === 'AccountGroup') return { icon: '👥', label: 'Group' };
                    if (type.includes('ServicePrincipal')) return { icon: '🤖', label: 'Service Principal' };
                    return { icon: '❓', label: type };
                };
                const typeInfo = getTypeInfo(principalType);

                let html = `
                    <!-- Principal Information Card -->
                    <div style="background: linear-gradient(135deg, #1a1d2e 0%, #16182a 100%); border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; border: 1px solid rgba(255, 255, 255, 0.05);">
                        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
                            <div style="font-size: 2.5em;">${typeInfo.icon}</div>
                            <div style="flex: 1;">
                                <div style="font-size: 1.3em; font-weight: 700; color: var(--text-primary); margin-bottom: 4px;">${escapeHtml(principalDisplayName)}</div>
                                <div style="display: inline-block; padding: 4px 10px; background: var(--accent)20; color: var(--accent); border-radius: 6px; font-size: 0.75em; font-weight: 600; text-transform: uppercase;">${typeInfo.label}</div>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.05);">
                            ${principalEmail ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Email</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary); word-break: break-all;">${escapeHtml(principalEmail)}</div>
                            </div>
                            ` : ''}
                            ${isGroup ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Members</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary);">
                                    <span style="font-size: 1.3em; font-weight: 600; color: var(--accent);">${memberCount}</span>
                                    <span style="color: var(--text-muted); font-size: 0.9em;"> ${memberCount === 1 ? 'member' : 'members'}</span>
                                </div>
                            </div>
                            ` : ''}
                            ${(!isGroup && principalName && principalName !== principalEmail) ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">${isServicePrincipal ? 'Application ID' : 'Username'}</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary); word-break: break-all; font-family: monospace;">${escapeHtml(principalName)}</div>
                            </div>
                            ` : ''}
                            ${principalId ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">ID</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary); font-family: monospace;">${escapeHtml(principalId)}</div>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    
                    <!-- Access Summary Card -->
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Access Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${uniqueResourcesCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Unique Resources</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #3b82f6;">${directCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Direct</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${groupCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Via Groups</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #10b981;">${ownershipCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Ownership</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${parentCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Via Parent</div>
                            </div>
                        </div>
                    </div>
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Accessible Resources</span>
                            <span class="results-count">${uniqueResourcesCount} resources</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by type
                const typeOrder = ['Catalog', 'Schema', 'Table', 'View', 'Volume', 'Function', 'Cluster', 'Job', 'Warehouse', 'ServingEndpoint', 'SecretScope'];
                const sortedTypes = Object.keys(byType).sort((a, b) => {
                    const aIdx = typeOrder.indexOf(a);
                    const bIdx = typeOrder.indexOf(b);
                    if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
                    if (aIdx === -1) return 1;
                    if (bIdx === -1) return -1;
                    return aIdx - bIdx;
                });

                sortedTypes.forEach((type, typeIdx) => {
                    const resources = byType[type];
                    const resourceCount = Object.keys(resources).length;
                    const typeId = 'type-' + type.replace(/[^a-zA-Z]/g, '');

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${getEmoji(type)}</span>
                                <span style="font-weight: 600; flex: 1;">${type}s(${resourceCount})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort resources alphabetically
                    const sortedResources = Object.entries(resources).sort((a, b) => a[0].localeCompare(b[0]));

                    sortedResources.forEach(([name, info], idx) => {
                        const isLast = idx === sortedResources.length - 1;
                        const uniquePrivileges = [...new Set(info.privileges)];
                        const grantTypes = [...info.grant_types].join(', ');
                        // Get inheritance paths (filter out null/undefined)
                        const inheritancePaths = [...new Set(info.inheritance_paths.filter(p => p))];

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 6px; word-break: break-all;">${name}</div>
                                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                                        ${uniquePrivileges.map(p => `<span class="result-badge low">${p}</span>`).join('')}
                                    </div>
                                    <div style="font-size: 0.8em; color: var(--text-muted); margin-top: 4px;">${grantTypes}</div>
                                    ${inheritancePaths.length > 0 ? `
                                    <div style="font-size: 0.75em; color: var(--accent); margin-top: 6px; padding: 4px 8px; background: var(--accent)10; border-radius: 4px; display: inline-block;">
                                        <span style="opacity: 0.7;">via:</span> ${inheritancePaths.join(' | ')}
                                    </div>` : ''}
                                </div>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                document.getElementById('principal-results').innerHTML = html;
            } catch (e) {
                showEmpty('principal-results', 'Error: ' + e.message);
            }
        }

        function toggleTreeSection(typeId) {
            const content = document.getElementById(typeId + '-content');
            const toggle = document.getElementById(typeId + '-toggle');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.textContent = '▼';
            } else {
                content.style.display = 'none';
                toggle.textContent = '▶';
            }
        }

        // Resource Analysis
        async function analyzeResource() {
            const searchInput = document.getElementById('resource-search');
            const query = searchInput.value.trim();
            if (!query) return;

            // Use the stored resource ID if available (from autocomplete), otherwise use the input value
            const resourceIdentifier = searchInput.dataset.resourceId || query;
            lastAnalysis.resource = resourceIdentifier;  // Track for auto-refresh
            showLoading('resource-results');

            try {
                const res = await fetch('/api/who-can-access', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({resource: resourceIdentifier, run_id: currentRunId})
                });
                const result = await res.json();

                if (!result.success) {
                    showEmpty('resource-results', result.message);
                    return;
                }

                const data = result.data || [];

                // Get resource info from the result
                const resourceInfo = result.resource_info || {};
                const resourceName = resourceInfo.name || query;
                const resourceId = resourceInfo.id || '';
                const resourceType = resourceInfo.type || '';
                const resourceOwner = resourceInfo.owner || '';

                // Group by principal type, then by unique key (canonical_id + email), collecting permissions and inheritance paths
                const byType = {};
                data.forEach(d => {
                    // Normalize type for grouping
                    let typeGroup = d.principal_type || 'Other';
                    if (typeGroup === 'AccountUser') typeGroup = 'User';
                    if (typeGroup === 'AccountGroup') typeGroup = 'Group';
                    if (typeGroup.includes('ServicePrincipal')) typeGroup = 'Service Principal';

                    // Extract canonical ID (part after ':' if present)
                    const canonicalId = d.principal_id.includes(':')
                        ? d.principal_id.split(':')[1]
                        : d.principal_id;

                    // Create unique key: canonical_id + email (to handle multiple accounts with same name)
                    const uniqueKey = canonicalId + '|' + (d.principal_email || d.principal_name || d.principal_id);

                    if (!byType[typeGroup]) byType[typeGroup] = {};
                    if (!byType[typeGroup][uniqueKey]) byType[typeGroup][uniqueKey] = {
                        name: d.principal_name || d.principal_id,
                        permissions: [],
                        grant_types: new Set(),
                        email: d.principal_email,
                        original_type: d.principal_type,
                        inheritance_paths: []
                    };
                    byType[typeGroup][uniqueKey].permissions.push(d.permission_level);
                    byType[typeGroup][uniqueKey].grant_types.add(d.grant_type);
                    if (d.inheritance_path) {
                        byType[typeGroup][uniqueKey].inheritance_paths.push(d.inheritance_path);
                    }
                });

                // Count unique principals per type
                const users = Object.keys(byType['User'] || {}).length;
                const groups = Object.keys(byType['Group'] || {}).length;
                const sps = Object.keys(byType['Service Principal'] || {}).length;
                const totalPrincipals = users + groups + sps;

                // Recalculate access type counts from grouped data (not from backend summary)
                let directCount = 0;
                let groupCount = 0;
                let ownershipCount = 0;
                let parentCount = 0;

                Object.values(byType).forEach(typeGroup => {
                    Object.values(typeGroup).forEach(principal => {
                        if (principal.grant_types.has('Direct')) directCount++;
                        if (principal.grant_types.has('Group')) groupCount++;
                        if (principal.grant_types.has('Ownership')) ownershipCount++;
                        if (principal.grant_types.has('Parent')) parentCount++;
                    });
                });

                // Get type icon and color
                const getResourceTypeInfo = (type) => {
                    const typeMap = {
                        'Catalog': { icon: '📦', color: '#667eea' },
                        'Schema': { icon: '📐', color: '#8b5cf6' },
                        'Table': { icon: '📊', color: '#3b82f6' },
                        'View': { icon: '👁️', color: '#06b6d4' },
                        'Volume': { icon: '💾', color: '#10b981' },
                        'Function': { icon: '⚡', color: '#f59e0b' },
                        'Cluster': { icon: '⚙️', color: '#ef4444' },
                        'ClusterPolicy': { icon: '📋', color: '#f87171' },
                        'Job': { icon: '🔄', color: '#f97316' },
                        'Warehouse': { icon: '🏭', color: '#ec4899' },
                        'ServingEndpoint': { icon: '🚀', color: '#a855f7' },
                        'SecretScope': { icon: '🔐', color: '#6366f1' },
                        'Metastore': { icon: '🗄️', color: '#14b8a6' }
                    };
                    return typeMap[type] || { icon: '📄', color: '#6b7280' };
                };
                const typeInfo = getResourceTypeInfo(resourceType);
                
                // Get appropriate ID label based on resource type
                const getIdLabel = (type) => {
                    if (type === 'Cluster') return 'Cluster ID';
                    if (type === 'ClusterPolicy') return 'Policy ID';
                    if (type === 'Warehouse') return 'Warehouse ID';
                    if (type === 'Job') return 'Job ID';
                    if (type === 'Catalog') return 'Catalog ID';
                    if (type === 'Schema') return 'Schema ID';
                    if (type === 'Table' || type === 'View') return 'Table ID';
                    return 'Resource ID';
                };

                let html = `
                    <!-- Resource Information Card -->
                    <div style="background: linear-gradient(135deg, #1a1d2e 0%, #16182a 100%); border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; border: 1px solid rgba(255, 255, 255, 0.05);">
                        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
                            <div style="flex: 1;">
                                <div style="font-size: 1.3em; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; word-break: break-all;">${escapeHtml(resourceName)}</div>
                                <div style="display: inline-block; padding: 4px 10px; background: ${typeInfo.color}20; color: ${typeInfo.color}; border: 1px solid ${typeInfo.color}40; border-radius: 6px; font-size: 0.75em; font-weight: 600; text-transform: uppercase;">${resourceType}</div>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.05);">
                            ${(resourceType === 'Cluster' || resourceType === 'Warehouse') ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">${getIdLabel(resourceType)}</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary); font-family: monospace; word-break: break-all;">${escapeHtml(resourceId)}</div>
                            </div>
                            ` : ''}
                            ${resourceOwner ? `
                            <div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">Owner</div>
                                <div style="font-size: 0.95em; color: var(--text-secondary); word-break: break-all;">${escapeHtml(resourceOwner)}</div>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    
                    <!-- Access Summary Card -->
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Access Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${totalPrincipals}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #3b82f6;">${directCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Direct</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${groupCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Via Groups</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #10b981;">${ownershipCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Ownership</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${parentCount}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Via Parent</div>
                            </div>
                        </div>
                    </div>
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Principals with Access</span>
                            <span class="results-count">${totalPrincipals} principals</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Sort types: User, Group, Service Principal
                const typeOrder = ['User', 'Group', 'Service Principal'];
                const sortedTypes = Object.keys(byType).sort((a, b) => {
                    const aIdx = typeOrder.indexOf(a);
                    const bIdx = typeOrder.indexOf(b);
                    if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
                    if (aIdx === -1) return 1;
                    if (bIdx === -1) return -1;
                    return aIdx - bIdx;
                });

                sortedTypes.forEach(type => {
                    const principals = byType[type];
                    const principalCount = Object.keys(principals).length;
                    const typeId = 'resource-type-' + type.replace(/[^a-zA-Z]/g, '');

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${getEmoji(type)}</span>
                                <span style="font-weight: 600; flex: 1;">${type}s(${principalCount})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort principals alphabetically by name (not by uniqueKey)
                    const sortedPrincipals = Object.entries(principals).sort((a, b) => {
                        const nameA = a[1].name || '';
                        const nameB = b[1].name || '';
                        return nameA.localeCompare(nameB);
                    });

                    sortedPrincipals.forEach(([uniqueKey, info], idx) => {
                        const isLast = idx === sortedPrincipals.length - 1;
                        const uniquePermissions = [...new Set(info.permissions)];
                        const grantTypes = [...info.grant_types].join(', ');
                        // Get unique inheritance paths (filter out null/undefined)
                        const inheritancePaths = [...new Set(info.inheritance_paths.filter(p => p))];
                        // Format name with email for uniqueness
                        const displayName = formatPrincipalName(info.name, info.email, null, null);

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 6px; word-break: break-all;">${displayName}</div>
                                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                                        ${uniquePermissions.map(p => `<span class="result-badge low">${p}</span>`).join('')}
                                    </div>
                                    <div style="font-size: 0.8em; color: var(--text-muted); margin-top: 4px;">${grantTypes}</div>
                                    ${inheritancePaths.length > 0 ? `
                                    <div style="font-size: 0.75em; color: var(--accent); margin-top: 6px; padding: 4px 8px; background: var(--accent)10; border-radius: 4px; display: inline-block;">
                                        <span style="opacity: 0.7;">via:</span> ${inheritancePaths.join(' | ')}
                                    </div>` : ''}
                                </div>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                document.getElementById('resource-results').innerHTML = html;
            } catch (e) {
                showEmpty('resource-results', 'Error: ' + e.message);
            }
        }

        // Browse Resources by Type
        async function browseResourcesByType(resourceType) {
            showLoading('resource-results');
            
            try {
                const res = await fetch('/api/browse-resources-by-type', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        resource_type: resourceType,
                        run_id: currentRunId
                    })
                });
                const result = await res.json();
                
                if (!result.success) {
                    showEmpty('resource-results', result.message || 'No resources found');
                    return;
                }
                
                const resources = result.resources || [];
                if (resources.length === 0) {
                    showEmpty('resource-results', `No ${resourceType}s found in this collection`);
                    return;
                }
                
                // Display the list of resources
                let html = `
                    <div class="card">
                        <div class="results-header">
                            <span class="results-title">${resourceType}s</span>
                            <span class="results-count">${resources.length} resource${resources.length !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">
                            <div style="max-height: 600px; overflow-y: auto;">
                `;
                
                resources.forEach((resource, idx) => {
                    const isLast = idx === resources.length - 1;
                    html += `
                        <div class="browse-resource-item" data-resource-id="${escapeHtml(resource.id)}" data-resource-name="${escapeHtml(resource.name)}"
                             style="display: flex; align-items: center; gap: 12px; padding: 14px 24px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'}; cursor: pointer; transition: background 0.2s;" 
                             onmouseover="this.style.background='var(--bg-input)'" 
                             onmouseout="this.style.background='transparent'">
                            <div style="flex: 1; min-width: 0;">
                                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 4px; word-break: break-all;">${escapeHtml(resource.name)}</div>
                                ${resource.owner ? `<div style="font-size: 0.85em; color: var(--text-secondary);">Owner: ${escapeHtml(resource.owner)}</div>` : ''}
                            </div>
                            <div style="color: var(--primary); font-size: 0.9em;">→</div>
                        </div>
                    `;
                });
                
                html += `
                            </div>
                        </div>
                    </div>
                `;
                
                document.getElementById('resource-results').innerHTML = html;
                
                // Attach click event listeners to the resource items
                document.querySelectorAll('.browse-resource-item').forEach(item => {
                    item.addEventListener('click', function() {
                        const resourceId = this.getAttribute('data-resource-id');
                        const resourceName = this.getAttribute('data-resource-name');
                        selectResource(resourceId, resourceName);
                    });
                });
            } catch (e) {
                showEmpty('resource-results', 'Error: ' + e.message);
            }
        }

        // Browse Principals by Type
        async function browsePrincipalsByType(principalType) {
            showLoading('principal-results');
            
            try {
                const res = await fetch('/api/browse-principals-by-type', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        principal_type: principalType,
                        run_id: currentRunId
                    })
                });
                const result = await res.json();
                
                if (!result.success) {
                    showEmpty('principal-results', result.message || 'No principals found');
                    return;
                }
                
                const principals = result.principals || [];
                if (principals.length === 0) {
                    showEmpty('principal-results', `No ${principalType}s found in this collection`);
                    return;
                }
                
                // Display the list of principals
                const typeLabel = principalType === 'ServicePrincipal' ? 'Service Principals' : principalType + 's';
                let html = `
                    <div class="card">
                        <div class="results-header">
                            <span class="results-title">${typeLabel}</span>
                            <span class="results-count">${principals.length} principal${principals.length !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">
                            <div style="max-height: 600px; overflow-y: auto;">
                `;
                
                principals.forEach((principal, idx) => {
                    const isLast = idx === principals.length - 1;
                    const displayName = principal.display_name || principal.name || principal.email || principal.id;
                    html += `
                        <div class="browse-principal-item" data-principal-id="${escapeHtml(principal.id)}" data-principal-name="${escapeHtml(displayName)}"
                             style="display: flex; align-items: center; gap: 12px; padding: 14px 24px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'}; cursor: pointer; transition: background 0.2s;" 
                             onmouseover="this.style.background='var(--bg-input)'" 
                             onmouseout="this.style.background='transparent'">
                            <div style="flex: 1; min-width: 0;">
                                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 4px; word-break: break-all;">${escapeHtml(displayName)}</div>
                                ${principal.email ? `<div style="font-size: 0.85em; color: var(--text-secondary);">${escapeHtml(principal.email)}</div>` : ''}
                            </div>
                            <div style="color: var(--primary); font-size: 0.9em;">→</div>
                        </div>
                    `;
                });
                
                html += `
                            </div>
                        </div>
                    </div>
                `;
                
                document.getElementById('principal-results').innerHTML = html;
                
                // Attach click event listeners to the principal items
                document.querySelectorAll('.browse-principal-item').forEach(item => {
                    item.addEventListener('click', function() {
                        const principalId = this.getAttribute('data-principal-id');
                        const principalName = this.getAttribute('data-principal-name');
                        selectPrincipal(principalId, principalName);
                    });
                });
            } catch (e) {
                showEmpty('principal-results', 'Error: ' + e.message);
            }
        }

        // Browse Principals by Type for Escalation Paths
        async function browsePathsPrincipalsByType(principalType) {
            showLoading('paths-results');
            
            try {
                const res = await fetch('/api/browse-principals-by-type', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        principal_type: principalType,
                        run_id: currentRunId
                    })
                });
                const result = await res.json();
                
                if (!result.success) {
                    showEmpty('paths-results', result.message || 'No principals found');
                    return;
                }
                
                const principals = result.principals || [];
                if (principals.length === 0) {
                    showEmpty('paths-results', `No ${principalType}s found in this collection`);
                    return;
                }
                
                // Display the list of principals
                const typeLabel = principalType === 'ServicePrincipal' ? 'Service Principals' : principalType + 's';
                let html = `
                    <div class="card">
                        <div class="results-header">
                            <span class="results-title">${typeLabel}</span>
                            <span class="results-count">${principals.length} principal${principals.length !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">
                            <div style="max-height: 600px; overflow-y: auto;">
                `;
                
                principals.forEach((principal, idx) => {
                    const isLast = idx === principals.length - 1;
                    const displayName = principal.display_name || principal.name || principal.email || principal.id;
                    html += `
                        <div class="browse-paths-principal-item" data-principal-id="${escapeHtml(principal.id)}" data-principal-name="${escapeHtml(displayName)}"
                             style="display: flex; align-items: center; gap: 12px; padding: 14px 24px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'}; cursor: pointer; transition: background 0.2s;" 
                             onmouseover="this.style.background='var(--bg-input)'" 
                             onmouseout="this.style.background='transparent'">
                            <div style="flex: 1; min-width: 0;">
                                <div style="font-weight: 500; color: var(--text-primary); margin-bottom: 4px; word-break: break-all;">${escapeHtml(displayName)}</div>
                                ${principal.email ? `<div style="font-size: 0.85em; color: var(--text-secondary);">${escapeHtml(principal.email)}</div>` : ''}
                            </div>
                            <div style="color: var(--primary); font-size: 0.9em;">→</div>
                        </div>
                    `;
                });
                
                html += `
                            </div>
                        </div>
                    </div>
                `;
                
                document.getElementById('paths-results').innerHTML = html;
                
                // Attach click event listeners to the principal items
                document.querySelectorAll('.browse-paths-principal-item').forEach(item => {
                    item.addEventListener('click', function() {
                        const principalId = this.getAttribute('data-principal-id');
                        const principalName = this.getAttribute('data-principal-name');
                        selectPathsPrincipal(principalId, principalName);
                    });
                });
            } catch (e) {
                showEmpty('paths-results', 'Error: ' + e.message);
            }
        }

        function selectPathsPrincipal(identifier, displayName) {
            const pathsInput = document.getElementById('paths-search');
            if (pathsInput) {
                pathsInput.value = displayName || identifier;
                pathsInput.dataset.identifier = identifier;
                document.getElementById('paths-clear-btn').style.display = 'flex';
            }
            const pathsAutocomplete = document.getElementById('paths-autocomplete');
            if (pathsAutocomplete) {
                pathsAutocomplete.classList.remove('show');
            }
            findPaths();
        }

        function getResourceIcon(type) {
            const icons = {
                'Catalog': '📦',
                'Schema': '📁',
                'Table': '📊',
                'View': '👁️',
                'Volume': '💾',
                'Function': '⚡',
                'Cluster': '🖥️',
                'Job': '⚙️',
                'Warehouse': '🏭',
                'ServingEndpoint': '🚀',
                'SecretScope': '🔐'
            };
            return icons[type] || '📄';
        }

        // Escalation Paths - Visual Attack Path Display
        function getRiskColor(risk) {
            const colors = { 'CRITICAL': '#8b5cf6', 'HIGH': '#f97316', 'MEDIUM': '#eab308' };
            return colors[risk] || '#8b5cf6';
        }
        function getRiskBg(risk) {
            const colors = { 'CRITICAL': '#8b5cf620', 'HIGH': '#f9731620', 'MEDIUM': '#eab30820' };
            return colors[risk] || '#8b5cf620';
        }
        function getRiskIcon(risk) {
            const icons = { 'CRITICAL': '🟣', 'HIGH': '🟠', 'MEDIUM': '🟡' };
            return icons[risk] || '⚪';
        }
        function getPathTypeIcon(type) {
            if (type === 'INDIRECT_ESCALATION') return '⚡';
            if (type === 'DIRECT_ROLE') return '👑';
            return '📋';
        }
        function getPathTypeLabel(type) {
            if (type === 'INDIRECT_ESCALATION') return 'Indirect (via Job/Notebook)';
            if (type === 'DIRECT_ROLE') return 'Direct Role Assignment';
            return 'Group Membership';
        }
        function getNodeIcon(type) {
            const icons = {
                'User': '👤', 'Group': '👥', 'ServicePrincipal': '🤖',
                'AccountUser': '👤', 'AccountGroup': '👥', 'AccountServicePrincipal': '🤖',
                'PrivilegedRole': '🛡️', 'PrivilegedPrincipal': '👑',
                'Job': '⚙️', 'Notebook': '📓', 'Pipeline': '🔄'
            };
            return icons[type] || '📦';
        }

        async function findPaths() {
            const searchInput = document.getElementById('paths-search');
            const query = searchInput.value.trim();
            if (!query) return;

            // Use the stored identifier if available (from autocomplete), otherwise use the input value
            const identifier = searchInput.dataset.identifier || query;
            lastAnalysis.paths = identifier;  // Track for auto-refresh
            showLoading('paths-results');

            try {
                const res = await fetch('/api/escalation-paths', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal: identifier, max_depth: 5, run_id: currentRunId})
                });
                const result = await res.json();

                if (!result.success) {
                    showEmpty('paths-results', result.message);
                    return;
                }

                const principal = result.principal || {};
                const summary = result.summary || {};
                const paths = result.paths || [];

                // No paths found
                if (summary.total_paths === 0) {
                    document.getElementById('paths-results').innerHTML = `
                        <div class="results-container">
                            <div style="padding: 60px 24px; text-align: center;">
                                <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                                <div style="font-size: 1.2em; color: var(--success); margin-bottom: 8px;">No Escalation Paths Found</div>
                                <div style="color: var(--text-secondary);">${formatPrincipalName(principal.display_name, principal.email, principal.name, null)} cannot reach any privileged roles</div>
                            </div>
                        </div>`;
                    return;
                }

                // Build summary cards with path type breakdown
                const groupPaths = summary.group_membership_paths || 0;
                const indirectPaths = summary.indirect_paths || 0;

                let html = `
                    <div class="summary-grid">
                        <div class="summary-card">
                            <div class="summary-value" style="color: #8b5cf6;">${summary.critical_paths || 0}</div>
                            <div class="summary-label">Critical Paths</div>
                        </div>
                        <div class="summary-card">
                            <div class="summary-value" style="color: #f97316;">${summary.high_paths || 0}</div>
                            <div class="summary-label">High Risk Paths</div>
                        </div>
                        <div class="summary-card">
                            <div class="summary-value accent">${summary.total_paths}</div>
                            <div class="summary-label">Total Paths</div>
                        </div>
                        <div class="summary-card">
                            <div class="summary-value accent">${summary.shortest_path || '-'}</div>
                            <div class="summary-label">Shortest Path</div>
                        </div>
                    </div>

                    <div style="display: flex; gap: 12px; margin-bottom: 24px;">
                        <div style="flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                <span>📋</span>
                                <span style="font-weight: 500;">Group Membership</span>
                            </div>
                            <div style="color: var(--text-secondary); font-size: 0.9em;">${groupPaths} path(s) via nested group chains</div>
                        </div>
                        <div style="flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                <span>⚡</span>
                                <span style="font-weight: 500;">Indirect Escalation</span>
                            </div>
                            <div style="color: var(--text-secondary); font-size: 0.9em;">${indirectPaths} path(s) via jobs/notebooks owned by admins</div>
                        </div>
                    </div>

                    <div class="results-container" style="margin-bottom: 24px;">
                        <div class="results-header">
                            <span class="results-title">Principal</span>
                        </div>
                        <div style="padding: 16px 24px; display: flex; align-items: center; gap: 12px;">
                            <span style="font-size: 24px;">${getNodeIcon(principal.type)}</span>
                            <div>
                                <div style="font-weight: 600;">${formatPrincipalName(principal.display_name, principal.email, principal.name, null)}</div>
                                <div style="color: var(--text-secondary); font-size: 0.9em;">${principal.type}</div>
                            </div>
                        </div>
                    </div>`;

                // Group paths by the final privileged role
                const pathsByRole = {};
                paths.forEach(p => {
                    // Find the privileged role from hops (last node with type PrivilegedRole)
                    let role = 'Unknown';
                    for (let i = p.hops.length - 1; i >= 0; i--) {
                        if (p.hops[i].node_type === 'PrivilegedRole') {
                            role = p.hops[i].node_name;
                            break;
                        }
                    }
                    if (!pathsByRole[role]) pathsByRole[role] = [];
                    pathsByRole[role].push(p);
                });

                // Sort roles by risk level
                const roleOrder = ['Account Admin', 'Metastore Admin', 'Workspace Admin', 'Catalog Owner'];
                const sortedRoles = Object.keys(pathsByRole).sort((a, b) => {
                    const ia = roleOrder.indexOf(a);
                    const ib = roleOrder.indexOf(b);
                    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
                });

                html += `<div class="results-container">
                    <div class="results-header">
                        <span class="results-title">Escalation Paths by Privileged Role</span>
                        <span class="results-count">${paths.length} paths</span>
                    </div>
                    <div class="results-body">`;

                // Render paths grouped by role
                for (const role of sortedRoles) {
                    const rolePaths = pathsByRole[role];
                    const firstPath = rolePaths[0];
                    const risk = firstPath.risk_level || 'HIGH';
                    const riskColor = getRiskColor(risk);
                    const riskBg = getRiskBg(risk);

                    html += `
                        <div class="attack-path-group" style="border-left: 4px solid ${riskColor}; margin: 16px 0; padding-left: 16px;">
                            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                                <span style="font-size: 24px;">🛡️</span>
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; font-size: 1.1em;">${role}</div>
                                    <div style="color: var(--text-secondary); font-size: 0.85em;">${rolePaths.length} path(s) to this role</div>
                                </div>
                                <span class="result-badge" style="background: ${riskBg}; color: ${riskColor};">${getRiskIcon(risk)} ${risk}</span>
                            </div>`;

                    // Show up to 3 paths per role
                    rolePaths.slice(0, 3).forEach((path, pathIdx) => {
                        const pathType = path.path_type || 'GROUP_MEMBERSHIP';
                        const isIndirect = pathType === 'INDIRECT_ESCALATION';

                        html += `
                            <div class="attack-path" style="background: var(--bg-input); border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <div style="color: var(--text-secondary); font-size: 0.8em;">
                                        Path ${pathIdx + 1} · ${path.path_length} hop${path.path_length !== 1 ? 's' : ''}
                                    </div>
                                    <span style="font-size: 0.75em; background: ${isIndirect ? '#f9731620' : '#3b82f620'}; color: ${isIndirect ? '#f97316' : '#3b82f6'}; padding: 2px 8px; border-radius: 4px;">
                                        ${getPathTypeIcon(pathType)} ${getPathTypeLabel(pathType)}
                                    </span>
                                </div>
                                <div class="path-hops">`;

                        // Render each hop
                        path.hops.forEach((hop, i) => {
                            const isStart = i === 0;
                            const isEnd = i === path.hops.length - 1;
                            const isRole = hop.node_type === 'PrivilegedRole';
                            const isPrivPrincipal = hop.node_type === 'PrivilegedPrincipal';

                            let nodeColor = '#64748b';
                            if (isStart) nodeColor = 'var(--accent)';
                            else if (isRole) nodeColor = riskColor;
                            else if (isPrivPrincipal) nodeColor = '#f97316';

                            // Edge label (for non-first hops)
                            if (i > 0) {
                                const edgeLabel = hop.edge_relationship || 'Connected';
                                const permLabel = hop.edge_permission && hop.edge_permission !== edgeLabel ? `: ${hop.edge_permission}` : '';
                                html += `
                                    <div class="path-edge" style="display: flex; align-items: center; margin: 8px 0 8px 20px;">
                                        <div style="width: 2px; height: 24px; background: ${nodeColor}; margin-right: 12px;"></div>
                                        <div style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 4px; padding: 4px 10px; font-size: 0.75em; color: var(--text-secondary);">
                                            ${edgeLabel}${permLabel}
                                        </div>
                                    </div>`;
                            }

                            // Node
                            const nodeIcon = getNodeIcon(hop.node_type);
                            html += `
                                <div class="path-node-row" style="display: flex; align-items: center; gap: 12px;">
                                    <div style="width: 32px; height: 32px; border-radius: ${isRole ? '4px' : '50%'}; background: ${nodeColor}; display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; flex-shrink: 0;">
                                        ${isStart ? '▶' : isRole ? '🛡️' : nodeIcon}
                                    </div>
                                    <div style="flex: 1;">
                                        <div style="font-weight: ${isRole ? '600' : '500'};">${hop.node_name}</div>
                                        <div style="font-size: 0.8em; color: var(--text-muted);">${hop.node_type}</div>
                                    </div>
                                    ${isStart ? '<span style="font-size: 0.75em; background: var(--accent); color: white; padding: 2px 8px; border-radius: 4px;">START</span>' : ''}
                                    ${isRole ? `<span style="font-size: 0.75em; background: ${riskBg}; color: ${riskColor}; padding: 2px 8px; border-radius: 4px;">ESCALATES TO</span>` : ''}
                                </div>`;
                        });

                        html += `
                                </div>
                            </div>`;
                    });

                    if (rolePaths.length > 3) {
                        html += `<div style="color: var(--text-muted); font-size: 0.85em; padding: 8px 0;">+ ${rolePaths.length - 3} more path(s) to ${role}</div>`;
                    }

                    html += `</div>`;
                }

                html += '</div></div>';
                document.getElementById('paths-results').innerHTML = html;
            } catch (e) {
                showEmpty('paths-results', 'Error: ' + e.message);
            }
        }

        // =====================================================================
        // REPORT FUNCTIONS
        // =====================================================================

        // Load Isolated Principals Report
        async function loadIsolatedPrincipals() {
            const container = document.getElementById('isolated-results');
            container.innerHTML = '<div class="loading">Analyzing principals...</div>';

            try {
                const res = await fetch(`/api/report/isolated?run_id=${currentRunId}`);
                const result = await res.json();

                if (result.error) {
                    showEmpty('isolated-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                // Group by level
                const byLevel = { 'Highly Isolated': [], 'Moderately Isolated': [], 'Slightly Isolated': [], 'Well Connected': [] };
                data.forEach(d => {
                    const level = d.isolation_risk || 'Well Connected';
                    if (byLevel[level]) byLevel[level].push(d);
                });

                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Isolation Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${data.length}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${summary.highly_isolated || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted);">Highly Isolated</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${summary.moderately_isolated || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted);">Moderately Isolated</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #3b82f6;">${summary.slightly_isolated || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted);">Slightly Isolated</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #22c55e;">${summary.well_connected || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted);">Well Connected</div>
                            </div>
                        </div>
                    </div>

                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Categorization Legend</div>
                        <div style="display: grid; grid-template-columns: 1fr; gap: 8px; font-size: 0.85em;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #8b5cf6;"></span>
                                <span><strong>Highly Isolated:</strong> No group memberships, no permissions, no owned resources</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #f59e0b;"></span>
                                <span><strong>Moderately Isolated:</strong> Connectivity score &lt; 5 (minimal connections)</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #3b82f6;"></span>
                                <span><strong>Slightly Isolated:</strong> Connectivity score 5-9</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #22c55e;"></span>
                                <span><strong>Well Connected:</strong> Connectivity score ≥ 10</span>
                            </div>
                        </div>
                        <div style="margin-top: 12px; font-size: 0.8em; color: var(--text-muted);">
                            Score = (Groups × 5) + Permissions + (Owned × 2)
                        </div>
                    </div>

                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Isolated Principals</span>
                            <span class="results-count">${data.length} principals</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by level
                const levelOrder = ['Highly Isolated', 'Moderately Isolated', 'Slightly Isolated', 'Well Connected'];
                const levelColors = { 'Highly Isolated': '#8b5cf6', 'Moderately Isolated': '#f59e0b', 'Slightly Isolated': '#3b82f6', 'Well Connected': '#22c55e' };
                const levelEmojis = { 'Highly Isolated': '🟣', 'Moderately Isolated': '🟠', 'Slightly Isolated': '🔵', 'Well Connected': '🟢' };

                levelOrder.forEach((level) => {
                    const items = byLevel[level];
                    if (items.length === 0) return;

                    const typeId = 'isolated-level-' + level.toLowerCase().replace(/\\s+/g, '-');

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${levelEmojis[level]}</span>
                                <span style="font-weight: 600; flex: 1; color: ${levelColors[level]};">${level} (${items.length})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort by connectivity score
                    const sortedItems = items.sort((a, b) => (a.connectivity_score || 0) - (b.connectivity_score || 0));

                    sortedItems.forEach((item, idx) => {
                        const isLast = idx === sortedItems.length - 1;
                        const name = item.name || item.email || item.id;
                        const icon = item.node_type?.includes('Service') ? '🤖' : '👤';
                        const principalId = item.email || item.id;

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <span style="font-size: 20px;">${icon}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 4px; word-break: break-all;">${name}</div>
                                    <div style="font-size: 0.8em; color: var(--text-muted);">
                                        Groups: ${item.groups || 0} | Permissions: ${item.permissions || 0} | Owned: ${item.owned || 0}
                                    </div>
                                </div>
                                <a href="javascript:void(0)" onclick="navigateToPrincipalAnalysis('${principalId.replace(/'/g, "\\'")}')"
                                   style="display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--accent); color: white; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 500; transition: opacity 0.2s;"
                                   onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                                    <span>🔍</span> Analyze
                                </a>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;
            } catch (e) {
                showEmpty('isolated-results', 'Error: ' + e.message);
            }
        }

        // Load Orphaned Resources Report
        async function loadOrphanedResources() {
            const container = document.getElementById('orphaned-results');
            container.innerHTML = '<div class="loading">Analyzing resources...</div>';

            try {
                const res = await fetch(`/api/report/orphaned?run_id=${currentRunId}`);
                const result = await res.json();

                if (result.error) {
                    showEmpty('orphaned-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                // Group by type
                const byType = {};
                data.forEach(d => {
                    const t = d.node_type || 'Unknown';
                    if (!byType[t]) byType[t] = [];
                    byType[t].push(d);
                });

                // Count by type for summary
                const typeCounts = {};
                for (const [type, items] of Object.entries(byType)) {
                    typeCounts[type] = items.length;
                }

                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Orphaned Resources Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${summary.total || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            ${Object.entries(typeCounts).map(([type, count]) => `
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${count}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">${type}s</div>
                            </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Orphaned Resources</span>
                            <span class="results-count">${summary.total || 0} resources</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by type
                const typeOrder = ['Catalog', 'Schema', 'Table', 'View', 'Volume', 'Function'];
                const sortedTypes = Object.keys(byType).sort((a, b) => {
                    const aIdx = typeOrder.indexOf(a);
                    const bIdx = typeOrder.indexOf(b);
                    if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
                    if (aIdx === -1) return 1;
                    if (bIdx === -1) return -1;
                    return aIdx - bIdx;
                });

                sortedTypes.forEach((type) => {
                    const items = byType[type];
                    const typeId = 'orphaned-type-' + type.replace(/[^a-zA-Z]/g, '');

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${getEmoji(type)}</span>
                                <span style="font-weight: 600; flex: 1;">${type}s (${items.length})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort resources alphabetically
                    const sortedItems = items.sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id));

                    sortedItems.forEach((item, idx) => {
                        const isLast = idx === sortedItems.length - 1;
                        const name = item.name || item.id;
                        const owner = item.owner || 'No owner';
                        const resourceId = item.name || item.id;

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 4px; word-break: break-all;">${name}</div>
                                    <div style="font-size: 0.8em; color: var(--text-muted);">Owner: ${owner}</div>
                                </div>
                                <a href="javascript:void(0)" onclick="navigateToResourceAnalysis('${resourceId.replace(/'/g, "\\'")}')"
                                   style="display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--accent); color: white; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 500; transition: opacity 0.2s;"
                                   onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                                    <span>🔍</span> Analyze
                                </a>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;
            } catch (e) {
                showEmpty('orphaned-results', 'Error: ' + e.message);
            }
        }

        // Load Over-Privileged Principals Report
        async function loadOverPrivileged() {
            const container = document.getElementById('overprivileged-results');
            container.innerHTML = '<div class="loading">Analyzing privileges...</div>';

            try {
                const res = await fetch(`/api/report/overprivileged?run_id=${currentRunId}`);
                const result = await res.json();

                if (result.error) {
                    showEmpty('overprivileged-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                // Group by level
                const byLevel = { 'HIGH': [], 'MEDIUM': [], 'LOW': [] };
                data.forEach(d => {
                    const level = d.risk_level || 'LOW';
                    if (byLevel[level]) byLevel[level].push(d);
                });

                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Over-Privileged Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${data.length}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${summary.high || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">High</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${summary.medium || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Medium</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #22c55e;">${summary.low || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Low</div>
                            </div>
                        </div>
                    </div>

                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Categorization Legend</div>
                        <div style="display: grid; grid-template-columns: 1fr; gap: 8px; font-size: 0.85em;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #8b5cf6;"></span>
                                <span><strong>High:</strong> Access to 3+ catalogs OR 10+ admin grants (ALL PRIVILEGES, MANAGE)</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #f59e0b;"></span>
                                <span><strong>Medium:</strong> Access to 1-2 catalogs OR 5-9 admin grants</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #22c55e;"></span>
                                <span><strong>Low:</strong> Has admin grants but below medium thresholds</span>
                            </div>
                        </div>
                    </div>

                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Over-Privileged Principals</span>
                            <span class="results-count">${data.length} principals</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by level
                const levelOrder = ['HIGH', 'MEDIUM', 'LOW'];
                const levelColors = { 'HIGH': '#8b5cf6', 'MEDIUM': '#f59e0b', 'LOW': '#22c55e' };
                const levelEmojis = { 'HIGH': '🟣', 'MEDIUM': '🟠', 'LOW': '🟢' };

                levelOrder.forEach((level) => {
                    const items = byLevel[level];
                    if (items.length === 0) return;

                    const typeId = 'overprivileged-level-' + level.toLowerCase();

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${levelEmojis[level]}</span>
                                <span style="font-weight: 600; flex: 1; color: ${levelColors[level]};">${level} (${items.length})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort by total resources descending
                    const sortedItems = items.sort((a, b) => (b.total_resources || 0) - (a.total_resources || 0));

                    sortedItems.forEach((item, idx) => {
                        const isLast = idx === sortedItems.length - 1;
                        const displayName = formatPrincipalName(item.principal_name, item.principal_email, null, item.principal_id);
                        const icon = item.principal_type?.includes('Service') ? '🤖' : '👤';
                        const analyzeId = item.principal_email || item.principal_name || item.principal_id;

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <span style="font-size: 20px;">${icon}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 4px; word-break: break-all;">${displayName}</div>
                                    <div style="font-size: 0.8em; color: var(--text-muted);">
                                        Catalogs: ${item.catalog_count || 0} | Admin Grants: ${item.admin_grants || 0} | Total Resources: ${item.total_resources || 0}
                                    </div>
                                </div>
                                <a href="javascript:void(0)" onclick="navigateToPrincipalAnalysis('${encodeURIComponent(analyzeId)}')"
                                   style="display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--accent); color: white; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 500; white-space: nowrap; transition: opacity 0.2s;"
                                   onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                                    <span>🔍</span> Analyze
                                </a>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;
            } catch (e) {
                showEmpty('overprivileged-results', 'Error: ' + e.message);
            }
        }

        // Load High Privilege Principals Report
        async function loadHighPrivilege() {
            const container = document.getElementById('highprivilege-results');
            container.innerHTML = '<div class="loading">Analyzing high privilege principals...</div>';

            try {
                const res = await fetch(`/api/report/high-privilege?run_id=${currentRunId}`);
                const result = await res.json();

                if (result.error) {
                    showEmpty('highprivilege-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                // Group by role, then by principal type
                const byRole = {
                    'Account Admin': { 'Users': {}, 'Groups': {}, 'Service Principals': {} },
                    'Metastore Admin': { 'Users': {}, 'Groups': {}, 'Service Principals': {} },
                    'Workspace Admin': { 'Users': {}, 'Groups': {}, 'Service Principals': {} },
                    'Catalog Owner': { 'Users': {}, 'Groups': {}, 'Service Principals': {} }
                };

                data.forEach(d => {
                    const role = d.role || 'Unknown';
                    const ptype = d.principal_type || '';
                    const pid = d.principal_id || '';
                    const pname = d.principal_name || pid;

                    let category = 'Users';
                    if (ptype.includes('Group')) category = 'Groups';
                    else if (ptype.includes('ServicePrincipal')) category = 'Service Principals';

                    if (!byRole[role]) byRole[role] = { 'Users': {}, 'Groups': {}, 'Service Principals': {} };
                    if (!byRole[role][category][pid]) {
                        byRole[role][category][pid] = {
                            name: pname,
                            email: d.principal_email,
                            type: ptype,
                            access: []
                        };
                    }
                    byRole[role][category][pid].access.push({
                        via: d.via,
                        access_type: d.access_type
                    });
                });

                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">High Privilege Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${summary.total_principals || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${summary.account_admin || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Account Admin</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #ec4899;">${summary.metastore_admin || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Metastore Admin</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${summary.workspace_admin || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Workspace Admin</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #3b82f6;">${summary.catalog_owner || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Catalog Owner</div>
                            </div>
                        </div>
                    </div>

                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Privilege Legend</div>
                        <div style="display: grid; grid-template-columns: 1fr; gap: 8px; font-size: 0.85em;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #8b5cf6;"></span>
                                <span><strong>Account Admin:</strong> Full control over the Databricks account</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #ec4899;"></span>
                                <span><strong>Metastore Admin:</strong> Full control over Unity Catalog metastore</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #f59e0b;"></span>
                                <span><strong>Workspace Admin:</strong> Full control over a workspace</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #3b82f6;"></span>
                                <span><strong>Catalog Owner:</strong> Full control over a catalog and its objects</span>
                            </div>
                        </div>
                        <div style="margin-top: 12px; font-size: 0.8em; color: var(--text-muted);">
                            Includes effective privileges via nested group membership (up to 2 levels deep)
                        </div>
                    </div>

                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">High Privilege Principals</span>
                            <span class="results-count">${data.length} privilege grants</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by role
                const roleOrder = ['Account Admin', 'Metastore Admin', 'Workspace Admin', 'Catalog Owner'];
                const roleColors = {
                    'Account Admin': '#8b5cf6',
                    'Metastore Admin': '#ec4899',
                    'Workspace Admin': '#f59e0b',
                    'Catalog Owner': '#3b82f6'
                };
                const roleEmojis = {
                    'Account Admin': '👑',
                    'Metastore Admin': '🗄️',
                    'Workspace Admin': '🏢',
                    'Catalog Owner': '📚'
                };
                const typeIcons = { 'Users': '👤', 'Groups': '👥', 'Service Principals': '🤖' };

                roleOrder.forEach((role) => {
                    const roleData = byRole[role];
                    const allPrincipals = [
                        ...Object.values(roleData['Users']),
                        ...Object.values(roleData['Groups']),
                        ...Object.values(roleData['Service Principals'])
                    ];
                    if (allPrincipals.length === 0) return;

                    const roleId = 'highpriv-role-' + role.replace(/\s+/g, '').toLowerCase();

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${roleId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${roleId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${roleEmojis[role]}</span>
                                <span style="font-weight: 600; flex: 1; color: ${roleColors[role]};">${role} (${allPrincipals.length})</span>
                            </div>
                            <div class="tree-type-content" id="${roleId}-content" style="display: none;">`;

                    // Sort principals
                    const sortedPrincipals = allPrincipals.sort((a, b) => a.name.localeCompare(b.name));

                    sortedPrincipals.forEach((principal, idx) => {
                        const isLast = idx === sortedPrincipals.length - 1;
                        let pIcon = '👤';
                        if (principal.type.includes('Group')) pIcon = '👥';
                        else if (principal.type.includes('ServicePrincipal')) pIcon = '🤖';
                        const displayName = formatPrincipalName(principal.name, principal.email, null, null);

                        const accessList = principal.access.map(a => {
                            return `<span style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; background: ${roleColors[role]}20; color: ${roleColors[role]}; border-radius: 4px; font-size: 0.75em; margin-right: 6px; margin-bottom: 4px;">${a.via} <span style="opacity: 0.7;">(${a.access_type})</span></span>`;
                        }).join('');

                        // Create analyze link - use email for users, name for others
                        const analyzeId = principal.email || principal.name;

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <span style="font-size: 20px;">${pIcon}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 4px; word-break: break-all;">${displayName}</div>
                                    <div style="font-size: 0.85em; line-height: 1.6; margin-top: 8px;">
                                        ${accessList}
                                    </div>
                                </div>
                                <a href="javascript:void(0)" onclick="navigateToEscalation('${encodeURIComponent(analyzeId)}')"
                                   style="display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--accent); color: white; border-radius: 6px; text-decoration: none; font-size: 0.85em; font-weight: 500; white-space: nowrap; transition: opacity 0.2s;"
                                   onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                                    <span>🔍</span> Analyze
                                </a>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;
            } catch (e) {
                showEmpty('highprivilege-results', 'Error: ' + e.message);
            }
        }

        // Secret Scope filter data cache
        let secretScopeFilterData = { workspaces: [], scopes: [] };

        // Load Secret Scope Filters
        async function loadSecretScopeFilters() {
            try {
                const res = await fetch(`/api/report/secret-scopes-filters?run_id=${currentRunId}`);
                const result = await res.json();

                if (result.success) {
                    secretScopeFilterData = result;

                    // Populate workspace dropdown
                    const wsSelect = document.getElementById('secretscope-workspace-filter');
                    wsSelect.innerHTML = '<option value="">All Workspaces</option>';
                    result.workspaces.forEach(ws => {
                        wsSelect.innerHTML += `<option value="${ws.id}">${ws.name}</option>`;
                    });

                    // Populate scope dropdown (all scopes initially)
                    updateScopeDropdown('');
                }
            } catch (e) {
                console.error('Error loading secret scope filters:', e);
            }
        }

        // Update scope dropdown based on selected workspace
        function updateScopeDropdown(workspaceId) {
            const scopeSelect = document.getElementById('secretscope-scope-filter');
            scopeSelect.innerHTML = '<option value="">All Scopes</option>';

            let filteredScopes = secretScopeFilterData.scopes;
            if (workspaceId) {
                filteredScopes = filteredScopes.filter(s => s.workspace_id === workspaceId);
            }

            // Group scopes by name (in case same name appears in multiple workspaces)
            const uniqueScopes = {};
            filteredScopes.forEach(s => {
                const key = workspaceId ? s.scope_name : `${s.scope_name} (${s.workspace_name || 'N/A'})`;
                uniqueScopes[s.scope_name] = key;
            });

            Object.entries(uniqueScopes).sort((a, b) => a[1].localeCompare(b[1])).forEach(([scopeName, displayName]) => {
                scopeSelect.innerHTML += `<option value="${scopeName}">${displayName}</option>`;
            });
        }

        // Handle workspace filter change
        function onSecretScopeWorkspaceChange() {
            const workspaceId = document.getElementById('secretscope-workspace-filter').value;
            updateScopeDropdown(workspaceId);
            // Reset scope selection and reload
            document.getElementById('secretscope-scope-filter').value = '';
            loadSecretScopeAccess();
        }

        // Clear all secret scope filters
        function clearSecretScopeFilters() {
            document.getElementById('secretscope-workspace-filter').value = '';
            document.getElementById('secretscope-scope-filter').value = '';
            updateScopeDropdown('');
            loadSecretScopeAccess();
        }

        // Load Secret Scope Access Report
        async function loadSecretScopeAccess() {
            const container = document.getElementById('secretscopes-results');
            container.innerHTML = '<div class="loading">Analyzing secret scope access...</div>';

            // Load filters if not already loaded
            if (secretScopeFilterData.scopes.length === 0) {
                await loadSecretScopeFilters();
            }

            // Get filter values
            const workspaceId = document.getElementById('secretscope-workspace-filter').value;
            const scopeName = document.getElementById('secretscope-scope-filter').value;

            try {
                let url = `/api/report/secret-scope-access?run_id=${currentRunId}`;
                if (workspaceId) url += `&workspace_id=${encodeURIComponent(workspaceId)}`;
                if (scopeName) url += `&scope_name=${encodeURIComponent(scopeName)}`;

                const res = await fetch(url);
                const result = await res.json();

                if (result.error) {
                    showEmpty('secretscopes-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                // Group by principal type, then by principal
                const byType = { 'Users': {}, 'Groups': {}, 'Service Principals': {} };

                data.forEach(d => {
                    const ptype = d.principal_type || '';
                    const pid = d.principal_id || '';
                    const pname = d.principal_name || pid;
                    let category = 'Users';
                    if (ptype.includes('Group')) category = 'Groups';
                    else if (ptype.includes('ServicePrincipal')) category = 'Service Principals';

                    if (!byType[category][pid]) {
                        byType[category][pid] = {
                            name: pname,
                            email: d.principal_email,
                            type: ptype,
                            scopes: []
                        };
                    }
                    byType[category][pid].scopes.push({
                        scope: d.scope_name,
                        permission: d.permission_level,
                        relationship: d.relationship
                    });
                });

                // Build active filter indicator
                const activeFilters = [];
                if (workspaceId) {
                    const ws = secretScopeFilterData.workspaces.find(w => w.id === workspaceId);
                    activeFilters.push(`Workspace: ${ws ? ws.name : workspaceId}`);
                }
                if (scopeName) {
                    activeFilters.push(`Scope: ${scopeName}`);
                }
                const filterIndicator = activeFilters.length > 0
                    ? `<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 0.85em; color: var(--accent);">🔍 Filtered by: ${activeFilters.join(' → ')}</div>`
                    : '';

                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Secret Scope Access Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${summary.total_scopes || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Scopes</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #3b82f6;">${summary.users || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Users</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #8b5cf6;">${summary.groups || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Groups</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #f59e0b;">${summary.service_principals || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Service Principals</div>
                            </div>
                        </div>
                        ${filterIndicator}
                    </div>

                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Permission Legend</div>
                        <div style="display: grid; grid-template-columns: 1fr; gap: 8px; font-size: 0.85em;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #8b5cf6;"></span>
                                <span><strong>MANAGE:</strong> Full control - can read, write, and manage ACLs</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #f59e0b;"></span>
                                <span><strong>WRITE:</strong> Can read and write secrets</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <span style="display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #3b82f6;"></span>
                                <span><strong>READ:</strong> Can only read secrets</span>
                            </div>
                        </div>
                    </div>

                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Principals with Secret Scope Access</span>
                            <span class="results-count">${data.length} access grants</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Render tree structure by principal type
                const typeOrder = ['Users', 'Groups', 'Service Principals'];
                const typeIcons = { 'Users': '👤', 'Groups': '👥', 'Service Principals': '🤖' };
                const typeColors = { 'Users': '#3b82f6', 'Groups': '#8b5cf6', 'Service Principals': '#f59e0b' };
                const permColors = { 'MANAGE': '#8b5cf6', 'WRITE': '#f59e0b', 'READ': '#3b82f6' };

                typeOrder.forEach((type) => {
                    const principals = byType[type];
                    const principalList = Object.values(principals);
                    if (principalList.length === 0) return;

                    const typeId = 'secretscopes-type-' + type.replace(/\s+/g, '').toLowerCase();

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${typeIcons[type]}</span>
                                <span style="font-weight: 600; flex: 1; color: ${typeColors[type]};">${type} (${principalList.length})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    // Sort principals alphabetically
                    const sortedPrincipals = principalList.sort((a, b) => a.name.localeCompare(b.name));

                    sortedPrincipals.forEach((principal, idx) => {
                        const isLast = idx === sortedPrincipals.length - 1;
                        const scopeList = principal.scopes.map(s => {
                            const permColor = permColors[s.permission] || '#64748b';
                            return `<span style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; background: ${permColor}20; color: ${permColor}; border-radius: 4px; font-size: 0.75em; margin-right: 6px; margin-bottom: 4px;">🔐 ${s.scope} <span style="font-weight: 600;">(${s.permission})</span></span>`;
                        }).join('');

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <span style="font-size: 20px;">${typeIcons[type]}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; margin-bottom: 4px; word-break: break-all;">${formatPrincipalName(principal.display_name, principal.email, principal.name, null)}</div>
                                    <div style="font-size: 0.85em; line-height: 1.6; margin-top: 8px;">
                                        ${scopeList}
                                    </div>
                                </div>
                            </div>`;
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;
            } catch (e) {
                showEmpty('secretscopes-results', 'Error: ' + e.message);
            }
        }

        // =====================================================================
        // IMPERSONATION ANALYSIS FUNCTIONS
        // =====================================================================

        async function loadSourcePrincipals() {
            const type = document.getElementById('impersonate-source-type').value;
            await loadPrincipalsForSelect('impersonate-source-select', type);
        }

        async function loadTargetPrincipals() {
            const type = document.getElementById('impersonate-target-type').value;
            await loadPrincipalsForSelect('impersonate-target-select', type);
        }

        async function loadPrincipalsForSelect(selectId, principalType) {
            const select = document.getElementById(selectId);
            select.innerHTML = '<option value="">Loading...</option>';
            select.style.display = 'block';

            // Check if currentRunId is set
            if (!currentRunId) {
                select.innerHTML = '<option value="">Select a data run first</option>';
                return;
            }

            try {
                const res = await fetch(`/api/principals-list?run_id=${currentRunId}&type=${principalType}`);

                // Check if response is OK
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }

                const result = await res.json();

                if (result.success && result.data.length > 0) {
                    let html = '<option value="">-- Select from list --</option>';
                    result.data.forEach(p => {
                        const displayName = formatPrincipalName(p.display_name, p.email, p.name, p.id);
                        html += `<option value="${p.email || p.name || p.id}">${displayName}</option>`;
                    });
                    select.innerHTML = html;

                    // Sync selection to input field
                    select.onchange = () => {
                        const inputId = selectId.replace('-select', '');
                        document.getElementById(inputId).value = select.value;
                    };
                } else {
                    select.innerHTML = '<option value="">No principals found</option>';
                }
            } catch (e) {
                console.error('Error loading principals:', e);
                select.innerHTML = '<option value="">Error loading principals</option>';
            }
        }

        async function runImpersonationAnalysis() {
            const sourceType = document.getElementById('impersonate-source-type').value;
            const source = document.getElementById('impersonate-source').value.trim();
            const targetType = document.getElementById('impersonate-target-type').value;
            const target = document.getElementById('impersonate-target').value.trim();
            const analysisType = document.querySelector('input[name="analysis-type"]:checked').value;

            if (!source || !target) {
                showEmpty('impersonation-results', 'Please enter both Source and Target');
                return;
            }

            if (!currentRunId) {
                showEmpty('impersonation-results', 'Please select a data run first');
                return;
            }

            const container = document.getElementById('impersonation-results');
            container.innerHTML = '<div class="loading">Finding impersonation paths...</div>';

            const maxHops = analysisType === 'shortest' ? 10 : 5;

            try {
                const res = await fetch('/api/impersonation-paths', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        run_id: currentRunId,
                        source_type: sourceType,
                        source: source,
                        target_type: targetType,
                        target: target,
                        analysis_type: analysisType,
                        max_hops: maxHops
                    })
                });

                // Check if response is OK before parsing JSON
                if (!res.ok) {
                    throw new Error(`Server error: ${res.status}`);
                }

                const result = await res.json();

                if (!result.success) {
                    showEmpty('impersonation-results', result.message || 'Analysis failed');
                    return;
                }

                const paths = result.paths || [];
                const sourceInfo = result.source || {};
                const targetInfo = result.target || {};

                if (paths.length === 0) {
                    showEmpty('impersonation-results', `No impersonation paths found from ${formatPrincipalName(sourceInfo.display_name, sourceInfo.email, sourceInfo.name, null)} to ${formatPrincipalName(targetInfo.display_name, targetInfo.email, targetInfo.name, null)}`);
                    return;
                }

                // Build HTML
                let html = `
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span style="font-weight: 600; color: var(--text-secondary);">Found ${paths.length} impersonation path${paths.length > 1 ? 's' : ''}</span>
                            </div>
                            <div style="display: flex; gap: 16px; align-items: center;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 1.2em;">${getNodeIcon(sourceInfo.type)}</span>
                                    <span style="font-weight: 500;">${formatPrincipalName(sourceInfo.display_name, sourceInfo.email, sourceInfo.name, null)}</span>
                                </div>
                                <span style="color: var(--text-muted);">→</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 1.2em;">${getNodeIcon(targetInfo.type)}</span>
                                    <span style="font-weight: 500;">${formatPrincipalName(targetInfo.display_name, targetInfo.email, targetInfo.name, null)}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Impersonation Paths</span>
                            <span class="results-count">${paths.length} path${paths.length > 1 ? 's' : ''}</span>
                        </div>
                        <div class="results-body" style="padding: 16px;">`;

                // Render each path
                paths.forEach((path, pathIdx) => {
                    const hops = path.hops || [];
                    html += `
                        <div style="margin-bottom: 24px; padding-bottom: 24px; border-bottom: ${pathIdx < paths.length - 1 ? '1px solid var(--border)' : 'none'};">
                            <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">
                                Path ${pathIdx + 1} (${hops.length} hop${hops.length > 1 ? 's' : ''})
                            </div>
                            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 8px;">`;

                    hops.forEach((hop, hopIdx) => {
                        const nodeType = hop.node_type || 'Unknown';
                        const nodeName = hop.node_name || hop.node_id;
                        const icon = getNodeIcon(nodeType);
                        const bgColor = getNodeBgColor(nodeType);
                        const textColor = getNodeTextColor(nodeType);

                        // Node box
                        html += `
                            <div style="display: flex; flex-direction: column; align-items: center; padding: 8px 12px; background: ${bgColor}; border-radius: 8px; border: 1px solid ${bgColor};">
                                <div style="display: flex; align-items: center; gap: 6px;">
                                    <span>${icon}</span>
                                    <span style="font-weight: 500; color: ${textColor}; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${nodeName}">${nodeName}</span>
                                </div>
                                <div style="font-size: 0.7em; color: var(--text-muted); margin-top: 2px;">(${nodeType})</div>
                            </div>`;

                        // Edge arrow (if not last node)
                        if (hopIdx < hops.length - 1) {
                            const nextHop = hops[hopIdx + 1];
                            const edgeLabel = nextHop.edge_relationship || '';
                            html += `
                                <div style="display: flex; flex-direction: column; align-items: center; padding: 0 4px;">
                                    <div style="font-size: 0.7em; color: var(--accent); font-weight: 500; white-space: nowrap;">${edgeLabel}</div>
                                    <div style="color: var(--text-muted);">→</div>
                                </div>`;
                        }
                    });

                    html += `
                            </div>
                        </div>`;
                });

                html += '</div></div>';
                container.innerHTML = html;

            } catch (e) {
                showEmpty('impersonation-results', 'Error: ' + e.message);
            }
        }

        function getNodeIcon(nodeType) {
            const icons = {
                'User': '👤', 'AccountUser': '👤',
                'Group': '👥', 'AccountGroup': '👥',
                'ServicePrincipal': '🤖', 'AccountServicePrincipal': '🤖',
                'Job': '⚙️', 'Notebook': '📓', 'Query': '📊', 'SQLQuery': '📊',
                'File': '📄', 'Pipeline': '🔄', 'Cluster': '🖥️',
                'Catalog': '📚', 'Schema': '📁', 'Table': '📋'
            };
            return icons[nodeType] || '📦';
        }

        function getNodeBgColor(nodeType) {
            if (nodeType.includes('User')) return '#3b82f620';
            if (nodeType.includes('Group')) return '#8b5cf620';
            if (nodeType.includes('ServicePrincipal')) return '#f59e0b20';
            if (['Job', 'Query', 'SQLQuery', 'Notebook', 'Pipeline'].includes(nodeType)) return '#ec489920';
            return '#64748b20';
        }

        function getNodeTextColor(nodeType) {
            if (nodeType.includes('User')) return '#3b82f6';
            if (nodeType.includes('Group')) return '#8b5cf6';
            if (nodeType.includes('ServicePrincipal')) return '#f59e0b';
            if (['Job', 'Query', 'SQLQuery', 'Notebook', 'Pipeline'].includes(nodeType)) return '#ec4899';
            return '#64748b';
        }

        // Autocomplete functionality for principal search
        let autocompleteTimeout = null;
        const principalSearchInput = document.getElementById('principal-search');
        const autocompleteDropdown = document.getElementById('principal-autocomplete');
        
        if (principalSearchInput && autocompleteDropdown) {
            principalSearchInput.addEventListener('input', function(e) {
                const query = e.target.value.trim();
                
                // Show/hide clear button
                const clearBtn = document.getElementById('principal-clear-btn');
                if (clearBtn) {
                    clearBtn.style.display = query ? 'flex' : 'none';
                }
                
                // Clear the stored identifier when user manually types
                delete principalSearchInput.dataset.identifier;
                
                // Clear existing timeout
                clearTimeout(autocompleteTimeout);
                
                // Hide dropdown if query is too short
                if (query.length < 2) {
                    autocompleteDropdown.classList.remove('show');
                    return;
                }
                
                // Debounce the search
                autocompleteTimeout = setTimeout(async () => {
                    try {
                        const url = `/api/search-principals?q=${encodeURIComponent(query)}&limit=10${currentRunId ? '&run_id=' + currentRunId : ''}`;
                        const res = await fetch(url);
                        const data = await res.json();
                        
                        if (data.principals && data.principals.length > 0) {
                            let html = '';
                            data.principals.forEach(p => {
                                const typeClass = p.type === 'User' || p.type === 'AccountUser' ? 'user' : 
                                                 p.type === 'Group' || p.type === 'AccountGroup' ? 'group' : 'sp';
                                const typeName = p.type.includes('ServicePrincipal') ? 'SP' : p.type.replace('Account', '');
                                const displayName = p.display_name || p.identifier;
                                html += `
                                    <div class="autocomplete-item" onclick="selectPrincipal('${escapeHtml(p.identifier)}', '${escapeHtml(displayName)}')">
                                        <div class="autocomplete-item-name">
                                            ${escapeHtml(displayName)}
                                            <span class="autocomplete-item-type ${typeClass}">${typeName}</span>
                                        </div>
                                        ${p.email ? `<div class="autocomplete-item-email">${escapeHtml(p.email)}</div>` : ''}
                                        <div class="autocomplete-item-id">ID: ${escapeHtml(p.identifier)}</div>
                                    </div>
                                `;
                            });
                            autocompleteDropdown.innerHTML = html;
                            autocompleteDropdown.classList.add('show');
                        } else {
                            autocompleteDropdown.classList.remove('show');
                        }
                    } catch (e) {
                        console.error('Autocomplete error:', e);
                        autocompleteDropdown.classList.remove('show');
                    }
                }, 300); // 300ms debounce
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!e.target.closest('.search-box')) {
                    autocompleteDropdown.classList.remove('show');
                }
            });
        }
        
        function selectPrincipal(identifier, displayName) {
            if (principalSearchInput) {
                // Show display name in the search box, but store the identifier for the API call
                principalSearchInput.value = displayName || identifier;
                principalSearchInput.dataset.identifier = identifier;
                // Show clear button
                document.getElementById('principal-clear-btn').style.display = 'flex';
            }
            if (autocompleteDropdown) {
                autocompleteDropdown.classList.remove('show');
            }
            analyzePrincipal();
        }

        // Clear principal search
        function clearPrincipalSearch() {
            const searchInput = document.getElementById('principal-search');
            const clearBtn = document.getElementById('principal-clear-btn');
            const resultsDiv = document.getElementById('principal-results');
            
            if (searchInput) {
                searchInput.value = '';
                delete searchInput.dataset.identifier;
            }
            if (clearBtn) {
                clearBtn.style.display = 'none';
            }
            if (resultsDiv) {
                resultsDiv.innerHTML = '';
            }
        }

        // Autocomplete functionality for escalation paths search
        let pathsAutocompleteTimeout = null;
        const pathsSearchInput = document.getElementById('paths-search');
        const pathsAutocompleteDropdown = document.getElementById('paths-autocomplete');
        
        if (pathsSearchInput && pathsAutocompleteDropdown) {
            pathsSearchInput.addEventListener('input', function(e) {
                const query = e.target.value.trim();
                
                // Show/hide clear button
                const clearBtn = document.getElementById('paths-clear-btn');
                if (clearBtn) {
                    clearBtn.style.display = query ? 'flex' : 'none';
                }
                
                // Clear the stored identifier when user manually types
                delete pathsSearchInput.dataset.identifier;
                
                // Clear existing timeout
                clearTimeout(pathsAutocompleteTimeout);
                
                // Hide dropdown if query is too short
                if (query.length < 2) {
                    pathsAutocompleteDropdown.classList.remove('show');
                    return;
                }
                
                // Debounce the search
                pathsAutocompleteTimeout = setTimeout(async () => {
                    try {
                        const url = `/api/search-principals?q=${encodeURIComponent(query)}&limit=10${currentRunId ? '&run_id=' + currentRunId : ''}`;
                        const res = await fetch(url);
                        const data = await res.json();
                        
                        if (data.principals && data.principals.length > 0) {
                            let html = '';
                            data.principals.forEach(p => {
                                const typeClass = p.type === 'User' || p.type === 'AccountUser' ? 'user' : 
                                                 p.type === 'Group' || p.type === 'AccountGroup' ? 'group' : 'sp';
                                const typeName = p.type.includes('ServicePrincipal') ? 'SP' : p.type.replace('Account', '');
                                const displayName = p.display_name || p.identifier;
                                html += `
                                    <div class="autocomplete-item" onclick="selectPathsPrincipal('${escapeHtml(p.identifier)}', '${escapeHtml(displayName)}')">
                                        <div class="autocomplete-item-name">
                                            ${escapeHtml(displayName)}
                                            <span class="autocomplete-item-type ${typeClass}">${typeName}</span>
                                        </div>
                                        ${p.email ? `<div class="autocomplete-item-email">${escapeHtml(p.email)}</div>` : ''}
                                        <div class="autocomplete-item-id">ID: ${escapeHtml(p.identifier)}</div>
                                    </div>
                                `;
                            });
                            pathsAutocompleteDropdown.innerHTML = html;
                            pathsAutocompleteDropdown.classList.add('show');
                        } else {
                            pathsAutocompleteDropdown.classList.remove('show');
                        }
                    } catch (e) {
                        console.error('Autocomplete error:', e);
                        pathsAutocompleteDropdown.classList.remove('show');
                    }
                }, 300); // 300ms debounce
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!e.target.closest('.search-box')) {
                    pathsAutocompleteDropdown.classList.remove('show');
                }
            });
        }
        
        function selectPathsPrincipal(identifier, displayName) {
            if (pathsSearchInput) {
                // Show display name in the search box, but store the identifier for the API call
                pathsSearchInput.value = displayName || identifier;
                pathsSearchInput.dataset.identifier = identifier;
                // Show clear button
                document.getElementById('paths-clear-btn').style.display = 'flex';
            }
            if (pathsAutocompleteDropdown) {
                pathsAutocompleteDropdown.classList.remove('show');
            }
            findPaths();
        }

        // Clear paths search
        function clearPathsSearch() {
            const searchInput = document.getElementById('paths-search');
            const clearBtn = document.getElementById('paths-clear-btn');
            const resultsDiv = document.getElementById('paths-results');
            
            if (searchInput) {
                searchInput.value = '';
                delete searchInput.dataset.identifier;
            }
            if (clearBtn) {
                clearBtn.style.display = 'none';
            }
            if (resultsDiv) {
                resultsDiv.innerHTML = '';
            }
        }

        // Clear resource search
        function clearResourceSearch() {
            const searchInput = document.getElementById('resource-search');
            const clearBtn = document.getElementById('resource-clear-btn');
            const resultsDiv = document.getElementById('resource-results');
            
            if (searchInput) {
                searchInput.value = '';
            }
            if (clearBtn) {
                clearBtn.style.display = 'none';
            }
            if (resultsDiv) {
                resultsDiv.innerHTML = '';
            }
        }

        // Resource search input event listener for clear button
        const resourceSearchInput = document.getElementById('resource-search');
        const resourceAutocompleteDropdown = document.getElementById('resource-autocomplete');
        let resourceAutocompleteTimeout = null;
        
        if (resourceSearchInput && resourceAutocompleteDropdown) {
            resourceSearchInput.addEventListener('input', function(e) {
                const query = e.target.value.trim();
                const clearBtn = document.getElementById('resource-clear-btn');
                if (clearBtn) {
                    clearBtn.style.display = query ? 'flex' : 'none';
                }
                
                // Clear the stored resource ID when user manually types
                delete resourceSearchInput.dataset.resourceId;
                
                // Clear existing timeout
                clearTimeout(resourceAutocompleteTimeout);
                
                // Hide dropdown if query is too short
                if (query.length < 2) {
                    resourceAutocompleteDropdown.classList.remove('show');
                    return;
                }
                
                // Debounce the search
                resourceAutocompleteTimeout = setTimeout(async () => {
                    try {
                        const url = `/api/search-resources?q=${encodeURIComponent(query)}&limit=10${currentRunId ? '&run_id=' + currentRunId : ''}`;
                        const res = await fetch(url);
                        const data = await res.json();
                        
                        if (data.resources && data.resources.length > 0) {
                            let html = '';
                            data.resources.forEach(r => {
                                // Map resource types to colors
                                const typeColors = {
                                    'Catalog': '#667eea',
                                    'Schema': '#8b5cf6',
                                    'Table': '#3b82f6',
                                    'View': '#06b6d4',
                                    'Volume': '#10b981',
                                    'Function': '#f59e0b',
                                    'Cluster': '#ef4444',
                                    'ClusterPolicy': '#f87171',
                                    'Job': '#f97316',
                                    'Warehouse': '#ec4899',
                                    'ServingEndpoint': '#a855f7',
                                    'SecretScope': '#6366f1',
                                    'Metastore': '#14b8a6'
                                };
                                const typeColor = typeColors[r.type] || '#6b7280';
                                // Use data attributes for both ID and name
                                html += `
                                    <div class="autocomplete-item resource-autocomplete-item" data-resource-id="${escapeHtml(r.identifier)}" data-resource-name="${escapeHtml(r.name)}">
                                        <div class="autocomplete-item-name">
                                            ${escapeHtml(r.name)}
                                            <span class="autocomplete-item-type" style="background: ${typeColor}20; color: ${typeColor}; border: 1px solid ${typeColor}40;">${r.type}</span>
                                        </div>
                                        <div class="autocomplete-item-id">ID: ${escapeHtml(r.identifier)}</div>
                                    </div>
                                `;
                            });
                            resourceAutocompleteDropdown.innerHTML = html;
                            resourceAutocompleteDropdown.classList.add('show');
                            
                            // Add click event listeners to the items
                            document.querySelectorAll('.resource-autocomplete-item').forEach(item => {
                                item.addEventListener('click', function() {
                                    const resourceId = this.getAttribute('data-resource-id');
                                    const resourceName = this.getAttribute('data-resource-name');
                                    selectResource(resourceId, resourceName);
                                });
                            });
                        } else {
                            resourceAutocompleteDropdown.classList.remove('show');
                        }
                    } catch (e) {
                        console.error('Autocomplete error:', e);
                        resourceAutocompleteDropdown.classList.remove('show');
                    }
                }, 300); // 300ms debounce
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!e.target.closest('.search-box')) {
                    resourceAutocompleteDropdown.classList.remove('show');
                }
            });
        }
        
        function selectResource(resourceId, resourceName) {
            if (resourceSearchInput) {
                // Show display name in the search box, but store the ID for the API call
                resourceSearchInput.value = resourceName || resourceId;
                resourceSearchInput.dataset.resourceId = resourceId;
                // Show clear button
                document.getElementById('resource-clear-btn').style.display = 'flex';
            }
            if (resourceAutocompleteDropdown) {
                resourceAutocompleteDropdown.classList.remove('show');
            }
            analyzeResource();
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Enter key handlers
        ['principal', 'resource', 'paths', 'risk'].forEach(id => {
            document.getElementById(id + '-search')?.addEventListener('keypress', e => {
                if (e.key === 'Enter') {
                    const fn = {principal: analyzePrincipal, resource: analyzeResource, paths: findPaths, risk: assessRisk};
                    fn[id]();
                }
            });
        });
    </script>
</body>
</html>'''


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/health')
def health():
    return '{"status":"healthy","service":"brickhound"}'


@app.route('/api/debug')
def api_debug():
    """Debug endpoint to test database connection"""
    import os
    debug_info = {
        'catalog': CATALOG,
        'schema': SCHEMA,
        'metadata_table': METADATA_TABLE,
        'vertices_table': VERTICES_TABLE,
        'edges_table': EDGES_TABLE,
        'warehouse_id_env': os.getenv('WAREHOUSE_ID') or os.getenv('DATABRICKS_WAREHOUSE_ID') or 'using_default',
    }

    # Test connection
    try:
        workspace_client, warehouse_id = get_connection()
        debug_info['warehouse_id_used'] = warehouse_id
        debug_info['connection'] = 'OK'
    except Exception as e:
        debug_info['connection'] = f'FAILED: {str(e)}'
        return jsonify(debug_info), 500

    # Test simple query
    try:
        result = exec_query(f"SELECT COUNT(*) FROM {METADATA_TABLE}")
        debug_info['metadata_count'] = result
        debug_info['metadata_query'] = 'OK'
    except Exception as e:
        debug_info['metadata_query'] = f'FAILED: {str(e)}'

    # Test vertices query
    try:
        result = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE}")
        debug_info['vertices_count'] = result
        debug_info['vertices_query'] = 'OK'
    except Exception as e:
        debug_info['vertices_query'] = f'FAILED: {str(e)}'

    # Test edges query
    try:
        result = exec_query(f"SELECT COUNT(*) FROM {EDGES_TABLE}")
        debug_info['edges_count'] = result
        debug_info['edges_query'] = 'OK'
    except Exception as e:
        debug_info['edges_query'] = f'FAILED: {str(e)}'

    return jsonify(debug_info)


@app.route('/api/config')
def api_config():
    """Get current configuration (catalog, schema, tables)"""
    return jsonify({
        "catalog": CATALOG,
        "schema": SCHEMA,
        "vertices_table": VERTICES_TABLE,
        "edges_table": EDGES_TABLE,
        "metadata_table": METADATA_TABLE,
        "config_source": "Determined at app startup - check logs for details"
    })


@app.route('/api/runs')
def api_runs():
    """Get available collection runs for the run selector dropdown"""
    try:
        print(f"[DEBUG] /api/runs called")
        print(f"[DEBUG] CATALOG={CATALOG}, SCHEMA={SCHEMA}")
        print(f"[DEBUG] METADATA_TABLE={METADATA_TABLE}")

        runs = get_available_runs(limit=10)
        print(f"[DEBUG] get_available_runs returned {len(runs) if runs else 0} runs")

        latest_run = get_latest_run_id()
        print(f"[DEBUG] latest_run_id={latest_run}")

        return jsonify({
            'success': True,
            'runs': runs,
            'current_run_id': latest_run
        })
    except Exception as e:
        print(f"[ERROR] /api/runs exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'runs': []}), 500


@app.route('/api/search-principals')
def api_search_principals():
    """Search for principals (users, groups, service principals) by name or email"""
    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 10))
        
        if not query or len(query) < 2:
            return jsonify({'principals': []})
        
        # Get current run_id
        run_id = get_current_run_id()
        if not run_id:
            return jsonify({'principals': [], 'error': 'No data collection runs available'})
        
        # Escape single quotes in the query for SQL
        query_escaped = query.replace("'", "''")
        search_pattern = f"%{query_escaped}%"
        starts_with_pattern = f"{query_escaped}%"
        
        # Search - filter to only principals and current run_id
        # Prioritize results that START with the query
        sql = f"""
            SELECT DISTINCT id, name, node_type, display_name, email
            FROM {VERTICES_TABLE}
            WHERE run_id = '{run_id}'
            AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
            AND (
                LOWER(COALESCE(name, '')) LIKE LOWER('{search_pattern}')
                OR LOWER(COALESCE(display_name, '')) LIKE LOWER('{search_pattern}')
                OR LOWER(COALESCE(email, '')) LIKE LOWER('{search_pattern}')
            )
            ORDER BY
                CASE
                    WHEN LOWER(name) LIKE LOWER('{starts_with_pattern}') THEN 1
                    WHEN LOWER(display_name) LIKE LOWER('{starts_with_pattern}') THEN 2
                    WHEN LOWER(email) LIKE LOWER('{starts_with_pattern}') THEN 3
                    ELSE 4
                END,
                name
            LIMIT {limit}
        """
        
        results = exec_query_df(sql)
        principals = []
        
        for row in results:
            principal = {
                'identifier': row.get('id', ''),
                'name': row.get('name', ''),
                'type': row.get('node_type', ''),
                'display_name': row.get('display_name') or row.get('name', ''),
                'email': row.get('email')
            }
            principals.append(principal)
        
        return jsonify({'principals': principals})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search-resources')
def api_search_resources():
    """Search for resources (catalogs, schemas, tables, etc.) by name"""
    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 10))
        
        if not query or len(query) < 2:
            return jsonify({'resources': []})
        
        # Get current run_id
        run_id = get_current_run_id()
        if not run_id:
            return jsonify({'resources': [], 'error': 'No data collection runs available'})
        
        # Escape single quotes in the query for SQL
        query_escaped = query.replace("'", "''")
        search_pattern = f"%{query_escaped}%"
        starts_with_pattern = f"{query_escaped}%"
        
        # Search - filter to only resources and current run_id
        # Prioritize results that START with the query
        sql = f"""
            SELECT DISTINCT id, name, node_type
            FROM {VERTICES_TABLE}
            WHERE run_id = '{run_id}'
            AND node_type IN ('Catalog', 'Schema', 'Table', 'View', 'Volume', 'Function', 
                              'Cluster', 'ClusterPolicy', 'Job', 'Warehouse', 'ServingEndpoint', 
                              'SecretScope', 'Metastore')
            AND LOWER(COALESCE(name, '')) LIKE LOWER('{search_pattern}')
            ORDER BY
                CASE
                    WHEN LOWER(name) LIKE LOWER('{starts_with_pattern}') THEN 1
                    ELSE 2
                END,
                node_type,
                name
            LIMIT {limit}
        """
        
        results = exec_query_df(sql)
        resources = []
        
        for row in results:
            resource = {
                'identifier': row.get('id', ''),  # Use ID as identifier for exact matching
                'name': row.get('name', ''),
                'type': row.get('node_type', '')
            }
            resources.append(resource)
        
        return jsonify({'resources': resources})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/browse-resources-by-type', methods=['POST'])
def api_browse_resources_by_type():
    """Get all resources of a specific type"""
    try:
        data = request.get_json() or {}
        resource_type = data.get('resource_type', '')
        run_id = data.get('run_id') or get_current_run_id()
        
        if not resource_type:
            return jsonify({'success': False, 'message': 'Resource type is required'})
        
        if not run_id:
            return jsonify({'success': False, 'message': 'No data collection runs available'})
        
        # Sanitize inputs
        resource_type = sanitize(resource_type)
        run_id = sanitize(run_id)
        
        # Query all resources of the specified type
        sql = f"""
            SELECT id, name, owner
            FROM {VERTICES_TABLE}
            WHERE run_id = '{run_id}'
            AND node_type = '{resource_type}'
            ORDER BY name
        """
        
        results = exec_query_df(sql)
        resources = []
        
        for row in results:
            resource = {
                'id': row.get('id', ''),
                'name': row.get('name', ''),
                'owner': row.get('owner', '')
            }
            resources.append(resource)
        
        return jsonify({
            'success': True,
            'resources': resources,
            'resource_type': resource_type,
            'count': len(resources)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/browse-principals-by-type', methods=['POST'])
def api_browse_principals_by_type():
    """Get all principals of a specific type"""
    try:
        data = request.get_json() or {}
        principal_type = data.get('principal_type', '')
        run_id = data.get('run_id') or get_current_run_id()
        
        if not principal_type:
            return jsonify({'success': False, 'message': 'Principal type is required'})
        
        if not run_id:
            return jsonify({'success': False, 'message': 'No data collection runs available'})
        
        # Sanitize inputs
        principal_type = sanitize(principal_type)
        run_id = sanitize(run_id)
        
        # Map to include both Account and non-Account types
        type_filter = []
        if principal_type == 'User':
            type_filter = ['User', 'AccountUser']
        elif principal_type == 'Group':
            type_filter = ['Group', 'AccountGroup']
        elif principal_type == 'ServicePrincipal':
            type_filter = ['ServicePrincipal', 'AccountServicePrincipal']
        else:
            type_filter = [principal_type]
        
        # Query all principals of the specified type
        type_list = "', '".join(type_filter)
        sql = f"""
            SELECT id, name, display_name, email
            FROM {VERTICES_TABLE}
            WHERE run_id = '{run_id}'
            AND node_type IN ('{type_list}')
            ORDER BY COALESCE(display_name, name, email, id)
        """
        
        results = exec_query_df(sql)
        principals = []
        
        for row in results:
            principal = {
                'id': row.get('id', ''),
                'name': row.get('name', ''),
                'display_name': row.get('display_name', ''),
                'email': row.get('email', '')
            }
            principals.append(principal)
        
        return jsonify({
            'success': True,
            'principals': principals,
            'principal_type': principal_type,
            'count': len(principals)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/stats')
def api_stats():
    try:
        run_id = get_current_run_id()
        if not run_id:
            return jsonify({'error': 'No collection runs available'}), 404

        # Principal counts
        users = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type IN ('User', 'AccountUser')")
        groups = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type IN ('Group', 'AccountGroup')")
        service_principals = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type IN ('ServicePrincipal', 'AccountServicePrincipal')")

        # Resource counts by type
        catalogs = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Catalog'")
        schemas = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Schema'")
        tables = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Table'")
        clusters = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Cluster'")
        jobs = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Job'")
        warehouses = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type = 'Warehouse'")

        # Total resources (excluding principals)
        resources = exec_query(f"SELECT COUNT(*) FROM {VERTICES_TABLE} WHERE run_id = '{run_id}' AND node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')")

        # Grant counts
        grants = exec_query(f"SELECT COUNT(*) FROM {EDGES_TABLE} WHERE run_id = '{run_id}' AND permission_level IS NOT NULL")

        # Collection metadata for this run
        collection_timestamp = None
        collected_by = None
        try:
            metadata = exec_query_df(f"SELECT CAST(collection_timestamp AS STRING) as ts, collected_by as cb FROM {METADATA_TABLE} WHERE run_id = '{run_id}' LIMIT 1")
            if metadata and len(metadata) > 0:
                row = metadata[0]
                # Try different possible key names (SDK might return col0, col1 if column names fail)
                collection_timestamp = row.get('ts') or row.get('col0')
                collected_by = row.get('cb') or row.get('col1')
        except Exception as e:
            print(f"Error loading collection metadata: {e}")
            pass  # Table may not exist yet

        # Get workspace coverage
        coverage = get_collection_coverage(run_id)
        workspaces_collected = coverage.get('workspaces_collected', []) if coverage else []
        workspaces_failed = coverage.get('workspaces_failed', []) if coverage else []
        collection_mode = coverage.get('collection_mode', 'unknown') if coverage else 'unknown'

        return jsonify({
            # Principals
            'users': users,
            'groups': groups,
            'service_principals': service_principals,
            # Resources
            'resources': resources,
            'catalogs': catalogs,
            'schemas': schemas,
            'tables': tables,
            'clusters': clusters,
            'jobs': jobs,
            'warehouses': warehouses,
            # Grants
            'grants': grants,
            # Metadata
            'collection_timestamp': collection_timestamp,
            'collected_by': collected_by,
            'run_id': run_id,
            # Workspace coverage
            'collection_mode': collection_mode,
            'workspaces_collected': workspaces_collected,
            'workspaces_failed': workspaces_failed
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/collection-coverage')
def api_collection_coverage():
    """Get workspace coverage information for the current collection run"""
    try:
        run_id = get_current_run_id()
        if not run_id:
            return jsonify({'success': False, 'error': 'No collection runs available'}), 404

        coverage = get_collection_coverage(run_id)
        if not coverage:
            return jsonify({'success': False, 'error': 'No coverage data found'}), 404

        return jsonify({
            'success': True,
            'run_id': run_id,
            **coverage
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/who-can-access', methods=['POST'])
def api_who_can_access():
    """Find all principals with access to a resource, including via group inheritance"""
    data = request.get_json() or {}
    resource_id = data.get('resource', '')

    run_id = get_current_run_id()
    if not run_id:
        return jsonify({'success': False, 'message': 'No collection runs available', 'data': []})

    resource = find_resource(resource_id, run_id)
    if not resource:
        return jsonify({'success': False, 'message': f"Resource '{resource_id}' not found", 'data': []})

    r_id = resource['id']
    r_name = resource['name'] or ''
    r_owner = resource['owner'] or ''

    query = f"""
    WITH RECURSIVE
    -- First, find all groups with direct access to this resource
    groups_with_access AS (
        SELECT
            g.id as group_id,
            g.name as group_name,
            e.permission_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON (e.src = g.id OR e.src = g.name) AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.dst = '{sanitize(r_id)}'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND e.permission_level IS NOT NULL
    ),
    -- Recursively expand group membership to find all members (including nested)
    group_members_recursive AS (
        -- Base case: direct members of groups with access
        SELECT
            member.id as member_id,
            member.name as member_name,
            member.display_name as member_display_name,
            member.email as member_email,
            member.node_type as member_type,
            gwa.permission_level,
            gwa.group_name as inheritance_path,
            1 as depth
        FROM groups_with_access gwa
        JOIN {EDGES_TABLE} membership ON (membership.dst = gwa.group_id OR membership.dst = gwa.group_name) AND membership.relationship = 'MemberOf' AND membership.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} member ON (membership.src = member.id OR membership.src = member.name OR membership.src = member.email) AND member.run_id = '{run_id}'

        UNION ALL

        -- Recursive case: members of nested groups
        SELECT
            member.id as member_id,
            member.name as member_name,
            member.display_name as member_display_name,
            member.email as member_email,
            member.node_type as member_type,
            gmr.permission_level,
            CONCAT(member.name, ' → ', gmr.inheritance_path) as inheritance_path,
            gmr.depth + 1 as depth
        FROM group_members_recursive gmr
        JOIN {VERTICES_TABLE} nested_group ON gmr.member_id = nested_group.id AND nested_group.run_id = '{run_id}'
        JOIN {EDGES_TABLE} membership ON (membership.dst = nested_group.id OR membership.dst = nested_group.name) AND membership.relationship = 'MemberOf' AND membership.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} member ON (membership.src = member.id OR membership.src = member.name OR membership.src = member.email) AND member.run_id = '{run_id}'
        WHERE nested_group.node_type IN ('Group', 'AccountGroup')
          AND gmr.depth < 10  -- Prevent infinite loops
    ),
    direct_grants AS (
        -- Direct grants to individual principals (users, SPs)
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name) as principal_name,
            v.node_type as principal_type,
            v.email as principal_email,
            e.permission_level,
            'Direct' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.dst = '{sanitize(r_id)}'
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND e.permission_level IS NOT NULL
    ),
    group_grants AS (
        -- Direct grants to groups (show the group itself)
        SELECT
            g.id as principal_id,
            g.name as principal_name,
            g.node_type as principal_type,
            CAST(NULL AS STRING) as principal_email,
            e.permission_level,
            'Direct' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON (e.src = g.id OR e.src = g.name) AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.dst = '{sanitize(r_id)}'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND e.permission_level IS NOT NULL
    ),
    inherited_access AS (
        -- Users/SPs who inherit access via group membership
        SELECT
            gmr.member_id as principal_id,
            COALESCE(gmr.member_display_name, gmr.member_name) as principal_name,
            gmr.member_type as principal_type,
            gmr.member_email as principal_email,
            gmr.permission_level,
            'Group' as grant_type,
            gmr.inheritance_path
        FROM group_members_recursive gmr
        WHERE gmr.member_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
    ),
    ownership AS (
        -- Owner has implicit ALL PRIVILEGES
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name) as principal_name,
            v.node_type as principal_type,
            v.email as principal_email,
            'ALL PRIVILEGES' as permission_level,
            'Ownership' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND (v.id = '{sanitize(r_owner)}' OR v.email = '{sanitize(r_owner)}' OR v.name = '{sanitize(r_owner)}')
          AND v.node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
          AND '{sanitize(r_owner)}' != ''
    ),
    parent_grants AS (
        -- Principals with DIRECT access via parent resources (e.g., access to Catalog grants access to its Schemas/Tables)
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name) as principal_name,
            v.node_type as principal_type,
            v.email as principal_email,
            e.permission_level,
            'Parent' as grant_type,
            parent.name as inheritance_path
        FROM {EDGES_TABLE} contains
        JOIN {VERTICES_TABLE} parent ON contains.src = parent.id AND parent.run_id = '{run_id}'
        JOIN {EDGES_TABLE} e ON e.dst = parent.id AND e.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        WHERE contains.run_id = '{run_id}'
          AND contains.dst = '{sanitize(r_id)}'
          AND contains.relationship = 'Contains'
          AND e.permission_level IS NOT NULL
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
    ),
    parent_groups_with_access AS (
        -- Groups with access to parent resources
        SELECT
            g.id as group_id,
            g.name as group_name,
            e.permission_level,
            parent.name as parent_name
        FROM {EDGES_TABLE} contains
        JOIN {VERTICES_TABLE} parent ON contains.src = parent.id AND parent.run_id = '{run_id}'
        JOIN {EDGES_TABLE} e ON e.dst = parent.id AND e.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} g ON (e.src = g.id OR e.src = g.name) AND g.run_id = '{run_id}'
        WHERE contains.run_id = '{run_id}'
          AND contains.dst = '{sanitize(r_id)}'
          AND contains.relationship = 'Contains'
          AND e.permission_level IS NOT NULL
          AND g.node_type IN ('Group', 'AccountGroup')
    ),
    parent_group_members_recursive AS (
        -- Base case: direct members of groups with parent access
        SELECT
            member.id as member_id,
            member.name as member_name,
            member.display_name as member_display_name,
            member.email as member_email,
            member.node_type as member_type,
            pgwa.permission_level,
            CONCAT(pgwa.group_name, ' → ', pgwa.parent_name) as inheritance_path,
            1 as depth
        FROM parent_groups_with_access pgwa
        JOIN {EDGES_TABLE} membership ON (membership.dst = pgwa.group_id OR membership.dst = pgwa.group_name) AND membership.relationship = 'MemberOf' AND membership.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} member ON (membership.src = member.id OR membership.src = member.name OR membership.src = member.email) AND member.run_id = '{run_id}'

        UNION ALL

        -- Recursive case: members of nested groups
        SELECT
            member.id as member_id,
            member.name as member_name,
            member.display_name as member_display_name,
            member.email as member_email,
            member.node_type as member_type,
            pgmr.permission_level,
            CONCAT(member.name, ' → ', pgmr.inheritance_path) as inheritance_path,
            pgmr.depth + 1 as depth
        FROM parent_group_members_recursive pgmr
        JOIN {VERTICES_TABLE} nested_group ON pgmr.member_id = nested_group.id AND nested_group.run_id = '{run_id}'
        JOIN {EDGES_TABLE} membership ON (membership.dst = nested_group.id OR membership.dst = nested_group.name) AND membership.relationship = 'MemberOf' AND membership.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} member ON (membership.src = member.id OR membership.src = member.name OR membership.src = member.email) AND member.run_id = '{run_id}'
        WHERE nested_group.node_type IN ('Group', 'AccountGroup')
          AND pgmr.depth < 10
    ),
    parent_access_via_groups AS (
        -- Users/SPs who inherit parent resource access via group membership
        SELECT
            pgmr.member_id as principal_id,
            COALESCE(pgmr.member_display_name, pgmr.member_name) as principal_name,
            pgmr.member_type as principal_type,
            pgmr.member_email as principal_email,
            pgmr.permission_level,
            'Parent' as grant_type,
            pgmr.inheritance_path
        FROM parent_group_members_recursive pgmr
        WHERE pgmr.member_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
    ),
    all_access AS (
        SELECT * FROM direct_grants
        UNION ALL
        SELECT * FROM group_grants
        UNION ALL
        SELECT * FROM inherited_access
        UNION ALL
        SELECT * FROM ownership
        UNION ALL
        SELECT * FROM parent_grants
        UNION ALL
        SELECT * FROM parent_access_via_groups
    ),
    deduplicated AS (
        -- Deduplicate by canonical ID (extract base ID from variants like ws_XXX_user:ID or account_user:ID)
        SELECT
            principal_id,
            principal_name,
            principal_email,
            principal_type,
            permission_level,
            grant_type,
            inheritance_path,
            -- Extract canonical ID: take part after last ':', or whole ID if no ':'
            CASE
                WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                ELSE principal_id
            END as canonical_id,
            -- Prefer account-level principals over workspace-level
            ROW_NUMBER() OVER (
                PARTITION BY
                    CASE
                        WHEN principal_id LIKE '%:%' THEN SPLIT(principal_id, ':')[1]
                        ELSE principal_id
                    END,
                    COALESCE(principal_email, principal_name),
                    permission_level,
                    grant_type
                ORDER BY
                    CASE principal_type
                        WHEN 'AccountUser' THEN 1
                        WHEN 'AccountGroup' THEN 1
                        WHEN 'AccountServicePrincipal' THEN 1
                        WHEN 'User' THEN 2
                        WHEN 'Group' THEN 2
                        WHEN 'ServicePrincipal' THEN 2
                        ELSE 3
                    END,
                    principal_id
            ) as rn
        FROM all_access
    )
    SELECT
        principal_id,
        principal_name,
        principal_email,
        principal_type,
        permission_level,
        grant_type,
        inheritance_path
    FROM deduplicated
    WHERE rn = 1
    ORDER BY
        CASE grant_type WHEN 'Direct' THEN 1 WHEN 'Ownership' THEN 2 WHEN 'Group' THEN 3 ELSE 4 END,
        principal_type,
        principal_name
    """

    results = exec_query_df(query)

    # Calculate summary statistics
    total = len(results)
    direct_count = sum(1 for r in results if r.get('grant_type') == 'Direct')
    group_count = sum(1 for r in results if r.get('grant_type') == 'Group')
    ownership_count = sum(1 for r in results if r.get('grant_type') == 'Ownership')
    parent_count = sum(1 for r in results if r.get('grant_type') == 'Parent')

    return jsonify({
        'success': True,
        'message': f"{total} principal(s) have access to {resource['name']}",
        'resource_info': {
            'id': resource['id'],
            'name': resource['name'],
            'type': resource['node_type'],
            'owner': resource.get('owner')
        },
        'summary': {
            'total': total,
            'direct': direct_count,
            'via_groups': group_count,
            'via_ownership': ownership_count,
            'via_parent': parent_count
        },
        'data': results
    })


@app.route('/api/what-can-access', methods=['POST'])
def api_what_can_access():
    """Find all resources a principal can access, including via group inheritance"""
    data = request.get_json() or {}
    principal_id = data.get('principal', '')
    resource_type = data.get('resource_type', 'All')

    run_id = get_current_run_id()
    if not run_id:
        return jsonify({'success': False, 'message': 'No collection runs available', 'data': []})

    principal = find_principal(principal_id, run_id)
    if not principal:
        return jsonify({'success': False, 'message': f"Principal '{principal_id}' not found", 'data': []})

    p_id = principal['id']
    p_email = principal['email'] or ''
    p_name = principal['name'] or ''

    # Handle ID format variations (account_user:123 vs 123)
    # MemberOf edges might use different formats depending on workspace vs account level
    p_id_variants = [p_id]
    if ':' in p_id:
        # If ID is prefixed (e.g., account_user:123), also try just the numeric part
        p_id_variants.append(p_id.split(':')[-1])
    else:
        # If ID is just numeric, also try all prefixed versions
        p_id_variants.append(f"account_user:{p_id}")
        p_id_variants.append(f"account_group:{p_id}")
        p_id_variants.append(f"account_sp:{p_id}")

    print(f"[DEBUG] Principal found: id={p_id}, email={p_email}, name={p_name}")
    print(f"[DEBUG] ID variants to search: {p_id_variants}")

    type_filter = f"AND v.node_type = '{sanitize(resource_type)}'" if resource_type and resource_type != 'All' else ""

    # Build SQL condition for all principal ID variants
    id_conditions = ' OR '.join([f"e.src = '{sanitize(vid)}'" for vid in p_id_variants])
    if p_email:
        id_conditions += f" OR e.src = '{sanitize(p_email)}'"
    if p_name:
        id_conditions += f" OR e.src = '{sanitize(p_name)}'"

    print(f"[DEBUG] ID conditions for groups query: {id_conditions}")

    # Build owner condition for owned_resources (uses v.owner instead of e.src)
    owner_conditions = ' OR '.join([f"v.owner = '{sanitize(vid)}'" for vid in p_id_variants])
    if p_email:
        owner_conditions += f" OR v.owner = '{sanitize(p_email)}'"
    if p_name:
        owner_conditions += f" OR v.owner = '{sanitize(p_name)}'"

    # Query groups first (like notebook does) - this is more reliable than recursive CTE
    groups_query = f"""
    WITH RECURSIVE
    all_groups AS (
        -- Level 0: Direct group memberships
        -- Match MemberOf edges where dst could be group ID or group name
        SELECT
            g.id as group_id,
            g.name as group_name,
            g.name as inheritance_path,
            0 as depth
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON (e.dst = g.id OR e.dst = g.name) AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND ({id_conditions})
          AND g.node_type IN ('Group', 'AccountGroup')

        UNION ALL

        -- Level 1+: Nested group memberships
        -- Group could be member of parent using either ID or name format
        SELECT
            parent_g.id as group_id,
            parent_g.name as group_name,
            CONCAT(ag.inheritance_path, ' → ', parent_g.name) as inheritance_path,
            ag.depth + 1 as depth
        FROM all_groups ag
        JOIN {EDGES_TABLE} e ON (e.src = ag.group_id OR e.src = ag.group_name) AND e.relationship = 'MemberOf' AND e.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} parent_g ON (e.dst = parent_g.id OR e.dst = parent_g.name) AND parent_g.run_id = '{run_id}'
        WHERE parent_g.node_type IN ('Group', 'AccountGroup')
          AND ag.depth < 10
    )
    SELECT DISTINCT group_id, group_name, inheritance_path FROM all_groups
    """
    groups_result = exec_query_df(groups_query)

    # Build lists of group IDs and names (like notebook)
    group_ids = [g['group_id'] for g in groups_result]
    group_names = [g['group_name'] for g in groups_result]
    group_paths = {g['group_id']: g['inheritance_path'] for g in groups_result}
    group_name_paths = {g['group_name']: g['inheritance_path'] for g in groups_result}

    print(f"[DEBUG] Found {len(group_ids)} groups for principal {p_id}: {group_names}")
    print(f"[DEBUG] Groups query returned {len(groups_result)} rows")

    # Build SQL-safe lists for IN clauses
    group_ids_sql = ','.join([f"'{sanitize(gid)}'" for gid in group_ids]) if group_ids else "'__none__'"
    group_names_sql = ','.join([f"'{sanitize(gname)}'" for gname in group_names]) if group_names else "'__none__'"

    # Build CASE statement for inheritance paths (match by both ID and name)
    path_cases_list = []
    for gid, path in group_paths.items():
        path_cases_list.append(f"WHEN e.src = '{sanitize(gid)}' THEN '{sanitize(path)}'")
    for gname, path in group_name_paths.items():
        path_cases_list.append(f"WHEN e.src = '{sanitize(gname)}' THEN '{sanitize(path)}'")

    # Build the inheritance_path expression - use e.src as fallback, or just e.src if no groups
    if path_cases_list:
        inheritance_path_expr = f"CASE {' '.join(path_cases_list)} ELSE e.src END"
    else:
        inheritance_path_expr = "e.src"

    print(f"[DEBUG] path_cases_list has {len(path_cases_list)} entries")

    query = f"""
    WITH direct_access AS (
        -- Direct permissions granted to the principal
        SELECT
            v.id as resource_id,
            v.name as resource_name,
            v.node_type as resource_type,
            e.permission_level,
            'Direct' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON e.dst = v.id AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND ({id_conditions})
          AND e.permission_level IS NOT NULL
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
          {type_filter}
    ),
    group_access AS (
        -- Permissions inherited via group membership (matching by both ID and name)
        SELECT
            v.id as resource_id,
            v.name as resource_name,
            v.node_type as resource_type,
            e.permission_level,
            'Group' as grant_type,
            {inheritance_path_expr} as inheritance_path
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON e.dst = v.id AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND (e.src IN ({group_ids_sql}) OR e.src IN ({group_names_sql}))
          AND e.permission_level IS NOT NULL
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
          {type_filter}
    ),
    owned_resources AS (
        -- Resources owned by the principal (implicit ALL PRIVILEGES)
        SELECT
            v.id as resource_id,
            v.name as resource_name,
            v.node_type as resource_type,
            'ALL PRIVILEGES' as permission_level,
            'Ownership' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND ({owner_conditions})
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
          {type_filter}
    ),
    parent_access AS (
        -- Inherited from parent resources (e.g., Catalog -> Schema -> Table)
        -- If principal has access to a catalog, they can access schemas/tables within it
        SELECT
            child.id as resource_id,
            child.name as resource_name,
            child.node_type as resource_type,
            e.permission_level,
            'Parent' as grant_type,
            parent.name as inheritance_path
        FROM {EDGES_TABLE} contains
        JOIN {VERTICES_TABLE} parent ON contains.src = parent.id AND parent.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} child ON contains.dst = child.id AND child.run_id = '{run_id}'
        JOIN {EDGES_TABLE} e ON e.dst = parent.id AND e.run_id = '{run_id}'
        WHERE contains.run_id = '{run_id}'
          AND contains.relationship = 'Contains'
          AND (
              -- Direct principal access to parent (with ID variants)
              {id_conditions}
              -- Group access to parent (by ID or name)
              OR e.src IN ({group_ids_sql})
              OR e.src IN ({group_names_sql})
          )
          AND e.permission_level IS NOT NULL
          AND child.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
          {type_filter}
    )
    SELECT DISTINCT
        resource_id,
        resource_name,
        resource_type,
        permission_level,
        grant_type,
        inheritance_path
    FROM (
        SELECT * FROM direct_access
        UNION ALL
        SELECT * FROM group_access
        UNION ALL
        SELECT * FROM owned_resources
        UNION ALL
        SELECT * FROM parent_access
    )
    ORDER BY resource_type, resource_name
    """

    print(f"[DEBUG] Executing main query...")
    results = exec_query_df(query)
    print(f"[DEBUG] Main query returned {len(results)} results")

    # Debug: Print first few results if any
    if results:
        print(f"[DEBUG] First result: {results[0]}")
    else:
        print(f"[DEBUG] No results! Trying simplified direct_access query...")
        # Try a simple query to test
        test_query = f"""
        SELECT COUNT(*) as cnt FROM {EDGES_TABLE} e
        WHERE (e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}')
          AND e.permission_level IS NOT NULL
        """
        test_result = exec_query_df(test_query)
        print(f"[DEBUG] Test query (edges with permission): {test_result}")

    # Calculate summary statistics
    total = len(results)
    direct_count = sum(1 for r in results if r.get('grant_type') == 'Direct')
    group_count = sum(1 for r in results if r.get('grant_type') == 'Group')
    ownership_count = sum(1 for r in results if r.get('grant_type') == 'Ownership')
    parent_count = sum(1 for r in results if r.get('grant_type') == 'Parent')

    # Count by resource type
    type_counts = {}
    for r in results:
        rt = r.get('resource_type', 'Unknown')
        type_counts[rt] = type_counts.get(rt, 0) + 1

    # Get member count if principal is a group
    member_count = 0
    if principal.get('node_type') in ('Group', 'AccountGroup'):
        # Count how many principals are members of this group (edges where dst is the group ID)
        member_query = f"""
        SELECT COUNT(DISTINCT src) as member_count
        FROM {EDGES_TABLE}
        WHERE run_id = '{run_id}'
          AND relationship = 'MemberOf'
          AND dst = '{sanitize(p_id)}'
        """
        member_result = exec_query_df(member_query)
        if member_result and len(member_result) > 0:
            member_count = member_result[0].get('member_count', 0)

    return jsonify({
        'success': True,
        'message': f"{total} resource(s) accessible to {principal['display_name'] or principal['name']}",
        'principal_info': {
            'id': principal['id'],
            'name': principal['name'],
            'display_name': principal['display_name'],
            'email': principal['email'],
            'type': principal['node_type'],
            'member_count': member_count
        },
        'summary': {
            'total': total,
            'direct': direct_count,
            'via_groups': group_count,
            'via_ownership': ownership_count,
            'via_parent': parent_count,
            'by_type': type_counts
        },
        'data': results
    })


def build_graph_from_db(run_id):
    """Build a graph structure from database for path analysis"""
    # Get all vertices
    vertices_query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = '{run_id}'
    """
    vertices = exec_query_df(vertices_query)

    # Get all edges with relationship info
    edges_query = f"""
    SELECT src, dst, relationship, permission_level
    FROM {EDGES_TABLE}
    WHERE run_id = '{run_id}'
    """
    edges = exec_query_df(edges_query)

    # Build adjacency list, node info, and edge info
    graph = {}  # node_id -> list of neighbor_ids
    node_info = {}  # node_id -> node attributes
    edge_info = {}  # (src, dst) -> edge attributes
    id_variants = {}  # Maps variant IDs to canonical ID (e.g., "123" -> "account_user:123")

    for v in vertices:
        vid = v.get('id', '')
        if vid:
            graph[vid] = []
            node_info[vid] = {
                'name': v.get('email') or v.get('name') or v.get('display_name') or vid,
                'display_name': v.get('display_name'),
                'node_type': v.get('node_type'),
                'email': v.get('email'),
                'owner': v.get('owner')
            }
            # Build ID variant mappings for edge resolution
            # e.g., "account_user:123" -> also index "123"
            if ':' in vid:
                short_id = vid.split(':')[-1]
                id_variants[short_id] = vid

    # Helper to resolve edge src/dst to canonical vertex ID
    def resolve_id(edge_id):
        if edge_id in graph:
            return edge_id
        if edge_id in id_variants:
            return id_variants[edge_id]
        return edge_id

    for e in edges:
        src_raw = e.get('src', '')
        dst_raw = e.get('dst', '')
        if src_raw and dst_raw:
            # Resolve to canonical IDs
            src = resolve_id(src_raw)
            dst = resolve_id(dst_raw)

            if src not in graph:
                graph[src] = []
            graph[src].append(dst)
            edge_info[(src, dst)] = {
                'relationship': e.get('relationship'),
                'permission_level': e.get('permission_level')
            }

    return graph, node_info, edge_info


def identify_escalation_targets_query(run_id):
    """
    Get escalation targets - GROUPS and RESOURCES that confer privileged access when joined/obtained.

    This returns the TARGET groups/roles for escalation path analysis -
    NOT the users who already have these roles.

    Targets include:
    - Account Admin groups ('admins', 'account admins')
    - Metastore Admin groups and metastores
    - Workspace Admin groups
    - Catalogs (ownership grants Catalog Owner)
    """
    query = f"""
    WITH
    -- Account Admin Groups: Groups that grant Account Admin when joined
    -- Account-level 'admins' group (by node_type OR id prefix) or groups with 'account admin' in name
    account_admin_groups AS (
        SELECT
            v.id as target_id,
            v.name as target_name,
            v.node_type as target_type,
            'Account Admin' as privileged_role,
            v.name as resource_name,
            'CRITICAL' as risk_level
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND v.node_type IN ('Group', 'AccountGroup')
          AND (((v.node_type = 'AccountGroup' OR v.id LIKE 'account_group:%') AND LOWER(v.name) = 'admins')
               OR LOWER(v.name) = 'account admins'
               OR LOWER(v.name) LIKE '%account%admin%')
    ),
    -- Metastore Admin Groups: Groups that grant Metastore Admin when joined
    metastore_admin_groups AS (
        SELECT
            v.id as target_id,
            v.name as target_name,
            v.node_type as target_type,
            'Metastore Admin' as privileged_role,
            v.name as resource_name,
            'CRITICAL' as risk_level
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND v.node_type IN ('Group', 'AccountGroup')
          AND LOWER(v.name) LIKE '%metastore%admin%'
        UNION ALL
        -- Metastore itself (ownership grants metastore admin)
        SELECT
            m.id as target_id,
            m.name as target_name,
            m.node_type as target_type,
            'Metastore Admin' as privileged_role,
            m.name as resource_name,
            'CRITICAL' as risk_level
        FROM {VERTICES_TABLE} m
        WHERE m.run_id = '{run_id}'
          AND m.node_type = 'Metastore'
    ),
    -- Workspace Admin Groups: Groups that grant Workspace Admin when joined
    -- Workspace-level 'admins' group (not account-level) or groups with 'workspace admin' in name
    workspace_admin_groups AS (
        SELECT
            v.id as target_id,
            v.name as target_name,
            v.node_type as target_type,
            'Workspace Admin' as privileged_role,
            v.name as resource_name,
            'HIGH' as risk_level
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND v.node_type IN ('Group', 'AccountGroup')
          AND ((v.node_type = 'Group' AND v.id NOT LIKE 'account_group:%' AND LOWER(v.name) = 'admins')
               OR LOWER(v.name) LIKE '%workspace%admin%'
               OR LOWER(v.name) = 'workspace admins')
    ),
    -- Catalog Owner targets: Catalogs where gaining ownership grants Catalog Owner
    catalog_owner_targets AS (
        SELECT
            c.id as target_id,
            c.name as target_name,
            c.node_type as target_type,
            'Catalog Owner' as privileged_role,
            c.name as resource_name,
            'HIGH' as risk_level
        FROM {VERTICES_TABLE} c
        WHERE c.run_id = '{run_id}'
          AND c.node_type = 'Catalog'
    )
    SELECT DISTINCT * FROM (
        SELECT * FROM account_admin_groups
        UNION ALL
        SELECT * FROM metastore_admin_groups
        UNION ALL
        SELECT * FROM workspace_admin_groups
        UNION ALL
        SELECT * FROM catalog_owner_targets
    )
    ORDER BY
        CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
        privileged_role
    """
    return exec_query_df(query)


def identify_privileged_principals_query(run_id):
    """
    Get principals who ALREADY hold privileged roles.
    Used for finding indirect escalation paths (jobs/notebooks owned by admins).
    """
    query = f"""
    WITH
    -- Account Admins via direct AccountAdmin edge (from roles field in SCIM API)
    account_admins_direct AS (
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Account Admin' as privileged_role,
            'Direct Role Assignment' as resource_name,
            'CRITICAL' as risk_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'AccountAdmin'
    ),
    -- Account Admins: Members of account-level 'admins' (by node_type OR id prefix) or 'account admins' group
    account_admins_group AS (
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Account Admin' as privileged_role,
            g.name as resource_name,
            'CRITICAL' as risk_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} g ON e.dst = g.id AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND (((g.node_type = 'AccountGroup' OR g.id LIKE 'account_group:%') AND LOWER(g.name) = 'admins')
               OR LOWER(g.name) = 'account admins'
               OR LOWER(g.name) LIKE '%account%admin%')
    ),
    -- Metastore Admins: Members of metastore admin groups
    metastore_admins AS (
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Metastore Admin' as privileged_role,
            g.name as resource_name,
            'CRITICAL' as risk_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} g ON e.dst = g.id AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND LOWER(g.name) LIKE '%metastore%admin%'
    ),
    -- Workspace Admins: Members of workspace-level 'admins' (not account-level) or workspace admin groups
    workspace_admins AS (
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Workspace Admin' as privileged_role,
            g.name as resource_name,
            'HIGH' as risk_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name) AND v.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} g ON e.dst = g.id AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND ((g.node_type = 'Group' AND g.id NOT LIKE 'account_group:%' AND LOWER(g.name) = 'admins')
               OR LOWER(g.name) LIKE '%workspace%admin%'
               OR LOWER(g.name) = 'workspace admins')
    ),
    -- Catalog Owners: Owners of catalogs
    catalog_owners AS (
        SELECT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Catalog Owner' as privileged_role,
            c.name as resource_name,
            'HIGH' as risk_level
        FROM {VERTICES_TABLE} c
        JOIN {VERTICES_TABLE} v ON (c.owner = v.id OR c.owner = v.email OR c.owner = v.name) AND v.run_id = '{run_id}'
        WHERE c.run_id = '{run_id}'
          AND c.node_type = 'Catalog'
          AND v.node_type IN ('User', 'ServicePrincipal', 'Group', 'AccountUser', 'AccountServicePrincipal', 'AccountGroup')
    )
    SELECT DISTINCT * FROM (
        SELECT * FROM account_admins_direct
        UNION ALL
        SELECT * FROM account_admins_group
        UNION ALL
        SELECT * FROM metastore_admins
        UNION ALL
        SELECT * FROM workspace_admins
        UNION ALL
        SELECT * FROM catalog_owners
    )
    ORDER BY
        CASE risk_level WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
        privileged_role
    """
    return exec_query_df(query)


# For backward compatibility
def identify_privileged_targets_query(run_id):
    """Alias for identify_escalation_targets_query() for backward compatibility"""
    return identify_escalation_targets_query(run_id)


def find_all_paths_bfs(graph, node_info, edge_info, start, targets, max_depth=5, membership_only=True):
    """
    Find all paths from start to targets using BFS, with edge information.

    Args:
        graph: Adjacency list graph
        node_info: Node metadata dict
        edge_info: Edge metadata dict
        start: Starting node ID
        targets: Set of target node IDs
        max_depth: Maximum path depth
        membership_only: If True, only follow MemberOf/HasMember edges (for group escalation)

    Returns:
        List of path dictionaries with hops and metadata
    """
    from collections import deque

    if start not in graph:
        return []

    all_paths = []
    queue = deque([(start, [start])])
    visited_paths = set()

    while queue:
        current, path = queue.popleft()

        if len(path) > max_depth + 1:
            continue

        path_key = tuple(path)
        if path_key in visited_paths:
            continue
        visited_paths.add(path_key)

        if current in targets and current != start:
            # Validate path: if membership_only, all edges must be MemberOf/HasMember
            is_valid_path = True
            if membership_only:
                for i in range(1, len(path)):
                    edge_data = edge_info.get((path[i-1], path[i]), {})
                    rel = edge_data.get('relationship', '')
                    if rel not in ('MemberOf', 'HasMember'):
                        is_valid_path = False
                        break

            if not is_valid_path:
                continue

            # Build detailed hop information
            hops = []
            for i, node_id in enumerate(path):
                node_data = node_info.get(node_id, {})
                hop = {
                    'node_id': node_id,
                    'node_name': node_data.get('email') or node_data.get('name') or node_id,
                    'node_type': node_data.get('node_type', 'Unknown')
                }
                if i > 0:
                    prev_node = path[i-1]
                    edge_data = edge_info.get((prev_node, node_id), {})
                    hop['edge_relationship'] = edge_data.get('relationship', 'Connected')
                    hop['edge_permission'] = edge_data.get('permission_level')
                hops.append(hop)

            all_paths.append({
                'target_id': current,
                'path_length': len(path) - 1,
                'hops': hops
            })

        for neighbor in graph.get(current, []):
            if neighbor not in path:  # Avoid cycles
                queue.append((neighbor, path + [neighbor]))

    return all_paths


def find_indirect_escalation_paths(principal, node_info, edge_info, run_id):
    """
    Find indirect escalation paths where a user has CAN_MANAGE/CAN_RUN on
    a Job or CAN_EDIT on a Notebook owned by a privileged principal.

    Returns:
        List of attack path dictionaries
    """
    p_id = principal['id']
    p_email = principal.get('email', '')
    p_name = principal.get('name', '')
    p_display = principal.get('display_name') or principal.get('name') or principal.get('email') or p_id

    # Get privileged principals
    privileged_df = identify_privileged_principals_query(run_id)

    # Build map of privileged principal identifiers
    privileged_principals = {}
    for row in privileged_df:
        pid = row.get('principal_id', '')
        if pid:
            if pid not in privileged_principals:
                privileged_principals[pid] = []
            privileged_principals[pid].append({
                'role': row.get('privileged_role', 'Unknown'),
                'resource': row.get('resource_name', ''),
                'risk_level': row.get('risk_level', 'UNKNOWN')
            })
            # Also index by email if available
            email = row.get('principal_email', '')
            if email:
                if email not in privileged_principals:
                    privileged_principals[email] = []
                privileged_principals[email].append({
                    'role': row.get('privileged_role', 'Unknown'),
                    'resource': row.get('resource_name', ''),
                    'risk_level': row.get('risk_level', 'UNKNOWN')
                })

    # Query for jobs/notebooks where principal has CAN_MANAGE
    indirect_query = f"""
    WITH
    principal_managed_resources AS (
        SELECT
            r.id as resource_id,
            r.name as resource_name,
            r.node_type as resource_type,
            r.owner as resource_owner,
            e.permission_level
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} r ON e.dst = r.id AND r.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND (e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}')
          AND r.node_type IN ('Job', 'Notebook', 'Pipeline')
          AND e.permission_level IN ('CAN_MANAGE', 'CAN_RUN', 'CAN_EDIT', 'IS_OWNER')
    )
    SELECT DISTINCT
        pmr.resource_id,
        pmr.resource_name,
        pmr.resource_type,
        pmr.resource_owner,
        pmr.permission_level
    FROM principal_managed_resources pmr
    WHERE pmr.resource_owner IS NOT NULL AND pmr.resource_owner != ''
    """

    try:
        results = exec_query_df(indirect_query)
    except Exception as e:
        print(f"  Warning: Error finding indirect paths: {e}")
        return []

    indirect_paths = []

    for row in results:
        resource_id = row.get('resource_id', '')
        resource_name = row.get('resource_name', '')
        resource_type = row.get('resource_type', '')
        resource_owner = row.get('resource_owner', '')
        permission = row.get('permission_level', '')

        # Check if owner is a privileged principal
        owner_roles = privileged_principals.get(resource_owner)
        if not owner_roles:
            continue

        # Build the indirect escalation path
        role_info = owner_roles[0]
        hops = [
            {
                'node_id': p_id,
                'node_name': p_display,
                'node_type': principal.get('node_type', 'User')
            },
            {
                'node_id': resource_id,
                'node_name': resource_name,
                'node_type': resource_type,
                'edge_relationship': permission,
                'edge_permission': permission
            },
            {
                'node_id': resource_owner,
                'node_name': resource_owner,
                'node_type': 'PrivilegedPrincipal',
                'edge_relationship': 'OwnedBy',
                'edge_permission': None
            },
            {
                'node_id': f"role:{role_info['role']}",
                'node_name': role_info['role'],
                'node_type': 'PrivilegedRole',
                'edge_relationship': 'Grants',
                'edge_permission': None
            }
        ]

        indirect_paths.append({
            'target_id': resource_owner,
            'target_name': resource_owner,
            'target_roles': owner_roles,
            'risk_level': role_info['risk_level'],
            'path_length': 4,
            'path_type': 'INDIRECT_ESCALATION',
            'escalation_resource': resource_name,
            'escalation_resource_type': resource_type,
            'hops': hops
        })

    print(f"  Found {len(indirect_paths)} indirect escalation paths")
    return indirect_paths


@app.route('/api/escalation-paths', methods=['POST'])
def api_escalation_paths():
    """
    Find attack paths to Databricks privileged roles.
    Matches notebook's find_escalation_paths() function.
    """
    data = request.get_json() or {}
    principal_id = data.get('principal', '')
    max_depth = int(data.get('max_depth', 5))

    run_id = get_current_run_id()
    if not run_id:
        return jsonify({'success': False, 'message': 'No collection runs available', 'data': []})

    principal = find_principal(principal_id, run_id)
    if not principal:
        return jsonify({'success': False, 'message': f"Principal '{principal_id}' not found", 'data': []})

    p_id = principal['id']
    p_name = principal.get('display_name') or principal.get('name') or principal.get('email') or p_id
    p_type = principal.get('node_type', 'Unknown')

    print(f"="*60)
    print(f"Finding escalation paths for: {p_name}")
    print(f"Principal ID: {p_id}")
    print(f"Principal email: {principal.get('email')}")

    # Build graph
    graph, node_info, edge_info = build_graph_from_db(run_id)
    total_edges = sum(len(v) for v in graph.values())
    print(f"Built graph with {len(graph)} nodes and {total_edges} edges")

    # Find ALL node IDs that match this principal (by email or name)
    # This handles account-level vs workspace-level user ID differences
    p_email = principal.get('email', '')
    p_name_lower = p_name.lower() if p_name else ''
    p_display_name = principal.get('display_name', '')
    all_principal_ids = [p_id]  # Start with the found ID

    for nid, ndata in node_info.items():
        if nid == p_id:
            continue
        # Match by email (case-insensitive)
        if p_email and ndata.get('email') and ndata.get('email').lower() == p_email.lower():
            all_principal_ids.append(nid)
            print(f"Found additional node with same email: {nid} ({ndata.get('node_type')})")
            continue
        # Match by name/display_name (for users with same identity)
        node_name = ndata.get('name', '').lower()
        node_display = (ndata.get('display_name') or '').lower()
        if ndata.get('node_type') in ('User', 'AccountUser') and p_email:
            # Check if name matches email prefix
            email_prefix = p_email.split('@')[0].lower() if '@' in p_email else ''
            if email_prefix and (email_prefix in node_name or email_prefix in node_display):
                all_principal_ids.append(nid)
                print(f"Found additional node with matching name: {nid} ({ndata.get('node_type')}) - name: {ndata.get('name')}")

    print(f"All principal IDs to search from: {all_principal_ids}")

    # Check neighbors for all principal IDs
    total_neighbors = []
    for pid in all_principal_ids:
        if pid in graph:
            neighbors = graph[pid]
            print(f"Principal {pid} has {len(neighbors)} direct neighbors")
            for n in neighbors[:3]:
                n_info = node_info.get(n, {})
                e_info = edge_info.get((pid, n), {})
                print(f"  -> {n}: {n_info.get('name')} ({n_info.get('node_type')}) via {e_info.get('relationship')}")
            total_neighbors.extend(neighbors)

    # Debug: Show some MemberOf edges
    print(f"Sample MemberOf edges:")
    memberof_count = 0
    for (src, dst), edata in edge_info.items():
        if edata.get('relationship') == 'MemberOf':
            memberof_count += 1
            if memberof_count <= 3:
                src_info = node_info.get(src, {})
                dst_info = node_info.get(dst, {})
                print(f"  {src} ({src_info.get('node_type')}) -> {dst} ({dst_info.get('node_type')})")
    print(f"Total MemberOf edges: {memberof_count}")

    # Get privileged targets (admin groups, catalogs, schemas, metastores)
    privileged_df = identify_privileged_targets_query(run_id)
    print(f"Found {len(privileged_df)} privileged target rows")

    # Build map of target_id -> role info
    privileged_map = {}
    for row in privileged_df:
        tid = row.get('target_id', '')
        if tid and tid != p_id:
            if tid not in privileged_map:
                privileged_map[tid] = []
            privileged_map[tid].append({
                'role': row.get('privileged_role', 'Unknown'),
                'resource': row.get('resource_name', ''),
                'risk_level': row.get('risk_level', 'UNKNOWN')
            })

    privileged_ids = set(privileged_map.keys())
    print(f"Unique privileged target IDs: {len(privileged_ids)}")

    # Check if any targets are in graph
    targets_in_graph = [t for t in privileged_ids if t in graph]
    print(f"Targets that exist in graph: {len(targets_in_graph)}")

    # Show admin groups specifically
    print(f"Admin group targets:")
    for tid, roles in privileged_map.items():
        if any('Admin' in r.get('role', '') for r in roles):
            t_info = node_info.get(tid, {})
            in_graph = "YES" if tid in graph else "NO"
            print(f"  {tid}: {t_info.get('name')} - in graph: {in_graph}")
            if tid in graph:
                # Check if reachable from principal
                print(f"    Neighbors of this target: {len(graph.get(tid, []))}")

    print(f"="*60)

    if not privileged_ids:
        return jsonify({
            'success': True,
            'message': 'No privileged targets found',
            'principal': {'id': p_id, 'name': p_name, 'type': p_type},
            'summary': {'total_paths': 0},
            'paths': []
        })

    # Check for DIRECT AccountAdmin edges first (Account Admin via direct role assignment)
    direct_admin_paths = []
    for pid in all_principal_ids:
        for (src, dst), edata in edge_info.items():
            if src == pid and edata.get('relationship') == 'AccountAdmin':
                dst_info = node_info.get(dst, {})
                print(f"Found direct AccountAdmin edge: {pid} -> {dst}")
                direct_admin_paths.append({
                    'start_id': pid,
                    'target_id': dst,
                    'target_name': dst_info.get('name', dst),
                    'target_roles': [{'role': 'Account Admin', 'resource': 'Direct Role Assignment', 'risk_level': 'CRITICAL'}],
                    'risk_level': 'CRITICAL',
                    'path_type': 'DIRECT_ROLE',
                    'path_length': 1,
                    'hops': [
                        {
                            'node_id': pid,
                            'node_name': node_info.get(pid, {}).get('name', pid),
                            'node_type': node_info.get(pid, {}).get('node_type', 'Unknown'),
                            'edge_relationship': None,
                            'edge_permission': None
                        },
                        {
                            'node_id': dst,
                            'node_name': dst_info.get('name', dst),
                            'node_type': dst_info.get('node_type', 'Account'),
                            'edge_relationship': 'AccountAdmin',
                            'edge_permission': None
                        },
                        {
                            'node_id': 'role:Account Admin',
                            'node_name': 'Account Admin',
                            'node_type': 'PrivilegedRole',
                            'edge_relationship': 'Grants',
                            'edge_permission': None
                        }
                    ]
                })

    print(f"Found {len(direct_admin_paths)} direct Account Admin paths")

    # Find all GROUP MEMBERSHIP paths from ALL principal IDs
    raw_paths = []
    for pid in all_principal_ids:
        print(f"Searching group membership paths from: {pid}")
        paths_from_pid = find_all_paths_bfs(graph, node_info, edge_info, pid, privileged_ids, max_depth, membership_only=True)
        print(f"  Found {len(paths_from_pid)} paths from {pid}")
        raw_paths.extend(paths_from_pid)

    # Enrich group membership paths with role info and add privileged role as final node
    attack_paths = []
    for path in raw_paths:
        target_id = path['target_id']
        roles = privileged_map.get(target_id, [{'role': 'Unknown', 'risk_level': 'UNKNOWN'}])
        role_info = roles[0]

        # Add the privileged role as the final "virtual" node
        path['hops'].append({
            'node_id': f"role:{role_info['role']}",
            'node_name': role_info['role'],
            'node_type': 'PrivilegedRole',
            'edge_relationship': 'Grants',
            'edge_permission': None
        })

        path['target_name'] = path['hops'][-2]['node_name'] if len(path['hops']) > 1 else target_id
        path['target_roles'] = roles
        path['risk_level'] = role_info['risk_level']
        path['path_type'] = 'GROUP_MEMBERSHIP'
        path['path_length'] = len(path['hops']) - 1  # Update to include role node
        attack_paths.append(path)

    # Add direct Account Admin paths
    attack_paths.extend(direct_admin_paths)

    # Find INDIRECT escalation paths (jobs/notebooks owned by admins)
    print("Searching for indirect escalation paths...")
    indirect_paths = find_indirect_escalation_paths(principal, node_info, edge_info, run_id)
    attack_paths.extend(indirect_paths)

    # Sort by risk level then path length
    risk_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'UNKNOWN': 4}
    attack_paths.sort(key=lambda p: (risk_order.get(p['risk_level'], 4), p['path_length']))

    # Build summary
    summary = {
        'total_paths': len(attack_paths),
        'critical_paths': len([p for p in attack_paths if p['risk_level'] == 'CRITICAL']),
        'high_paths': len([p for p in attack_paths if p['risk_level'] == 'HIGH']),
        'medium_paths': len([p for p in attack_paths if p['risk_level'] == 'MEDIUM']),
        'shortest_path': min([p['path_length'] for p in attack_paths]) if attack_paths else None,
        'unique_targets': len(set(p['target_id'] for p in attack_paths)),
        'group_membership_paths': len([p for p in attack_paths if p.get('path_type') == 'GROUP_MEMBERSHIP']),
        'indirect_paths': len([p for p in attack_paths if p.get('path_type') == 'INDIRECT_ESCALATION']),
        'direct_role_paths': len([p for p in attack_paths if p.get('path_type') == 'DIRECT_ROLE'])
    }

    return jsonify({
        'success': True,
        'message': f"Escalation path analysis for {p_name}",
        'principal': {'id': p_id, 'name': p_name, 'type': p_type},
        'summary': summary,
        'paths': attack_paths
    })


@app.route('/api/debug-graph', methods=['POST'])
def api_debug_graph():
    """Debug endpoint to inspect graph structure"""
    data = request.get_json() or {}
    principal_id = data.get('principal', '')

    run_id = get_current_run_id()
    if not run_id:
        return jsonify({'success': False, 'message': 'No collection runs available'})

    principal = find_principal(principal_id, run_id)
    if not principal:
        return jsonify({'success': False, 'message': f"Principal '{principal_id}' not found"})

    p_id = principal['id']

    # Build graph
    graph, node_info, id_lookup = build_graph_from_db(run_id)

    # Get neighbors of the principal
    neighbors = graph.get(p_id, [])
    neighbor_info = []
    for n in neighbors:
        info = node_info.get(n, {})
        neighbor_info.append({
            'id': n,
            'name': info.get('name'),
            'node_type': info.get('node_type')
        })

    # Get privileged principals
    privileged = identify_privileged_principals_query(run_id)

    return jsonify({
        'success': True,
        'principal': {
            'id': p_id,
            'name': principal.get('name'),
            'display_name': principal.get('display_name'),
            'email': principal.get('email')
        },
        'graph_stats': {
            'total_nodes': len(graph),
            'total_edges': sum(len(v) for v in graph.values())
        },
        'direct_neighbors': neighbor_info,
        'privileged_count': len(privileged),
        'privileged_sample': privileged[:5] if privileged else []
    })


@app.route('/api/blast-radius', methods=['POST'])
def api_blast_radius():
    """Calculate blast radius for a principal, including via group inheritance"""
    data = request.get_json() or {}
    principal_id = data.get('principal', '')

    run_id = get_current_run_id()
    if not run_id:
        return jsonify({'success': False, 'message': 'No collection runs available', 'data': []})

    principal = find_principal(principal_id, run_id)
    if not principal:
        return jsonify({'success': False, 'message': f"Principal '{principal_id}' not found", 'data': []})

    p_id = principal['id']
    p_email = principal['email'] or ''
    p_name = principal['name'] or ''

    # Query groups first (like notebook does) - match on both group ID and name
    groups_query = f"""
    WITH RECURSIVE
    all_groups AS (
        -- Level 0: Direct group memberships (match dst by ID or name)
        SELECT g.id as group_id, g.name as group_name, g.name as inheritance_path, 0 as depth
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON (e.dst = g.id OR e.dst = g.name) AND g.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND (e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}')
          AND g.node_type IN ('Group', 'AccountGroup')
        UNION ALL
        -- Level 1+: Nested group memberships (match src/dst by ID or name)
        SELECT parent_g.id, parent_g.name, CONCAT(ag.inheritance_path, ' → ', parent_g.name), ag.depth + 1
        FROM all_groups ag
        JOIN {EDGES_TABLE} e ON (e.src = ag.group_id OR e.src = ag.group_name) AND e.relationship = 'MemberOf' AND e.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} parent_g ON (e.dst = parent_g.id OR e.dst = parent_g.name) AND parent_g.run_id = '{run_id}'
        WHERE parent_g.node_type IN ('Group', 'AccountGroup') AND ag.depth < 10
    )
    SELECT DISTINCT group_id, group_name FROM all_groups
    """
    groups_result = exec_query_df(groups_query)
    group_ids = [g['group_id'] for g in groups_result]
    group_names = [g['group_name'] for g in groups_result]

    group_ids_sql = ','.join([f"'{sanitize(gid)}'" for gid in group_ids]) if group_ids else "'__none__'"
    group_names_sql = ','.join([f"'{sanitize(gname)}'" for gname in group_names]) if group_names else "'__none__'"

    query = f"""
    WITH direct_access AS (
        -- Direct permissions granted to the principal
        SELECT DISTINCT v.id, v.node_type, 'Direct' as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON e.dst = v.id AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND (e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}')
          AND e.permission_level IS NOT NULL
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ),
    group_access AS (
        -- Permissions inherited via group membership
        SELECT DISTINCT v.id, v.node_type, 'Group' as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON e.dst = v.id AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND (e.src IN ({group_ids_sql}) OR e.src IN ({group_names_sql}))
          AND e.permission_level IS NOT NULL
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ),
    owned_resources AS (
        -- Resources owned by the principal
        SELECT DISTINCT v.id, v.node_type, 'Ownership' as access_type
        FROM {VERTICES_TABLE} v
        WHERE v.run_id = '{run_id}'
          AND (v.owner = '{sanitize(p_id)}' OR v.owner = '{sanitize(p_email)}' OR v.owner = '{sanitize(p_name)}')
          AND v.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ),
    parent_access AS (
        -- Inherited from parent resources (e.g., Catalog -> Schema -> Table)
        SELECT DISTINCT child.id, child.node_type, 'Parent' as access_type
        FROM {EDGES_TABLE} contains
        JOIN {VERTICES_TABLE} parent ON contains.src = parent.id AND parent.run_id = '{run_id}'
        JOIN {VERTICES_TABLE} child ON contains.dst = child.id AND child.run_id = '{run_id}'
        JOIN {EDGES_TABLE} e ON e.dst = parent.id AND e.run_id = '{run_id}'
        WHERE contains.run_id = '{run_id}'
          AND contains.relationship = 'Contains'
          AND (
              e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}'
              OR e.src IN ({group_ids_sql})
              OR e.src IN ({group_names_sql})
          )
          AND e.permission_level IS NOT NULL
          AND child.node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ),
    all_accessible AS (
        SELECT * FROM direct_access
        UNION
        SELECT * FROM group_access
        UNION
        SELECT * FROM owned_resources
        UNION
        SELECT * FROM parent_access
    )
    SELECT
        node_type as resource_type,
        COUNT(DISTINCT id) as count,
        SUM(CASE WHEN access_type = 'Direct' THEN 1 ELSE 0 END) as direct_count,
        SUM(CASE WHEN access_type = 'Group' THEN 1 ELSE 0 END) as group_count,
        SUM(CASE WHEN access_type = 'Ownership' THEN 1 ELSE 0 END) as ownership_count,
        SUM(CASE WHEN access_type = 'Parent' THEN 1 ELSE 0 END) as parent_count
    FROM all_accessible
    GROUP BY node_type
    ORDER BY count DESC
    """

    results = exec_query_df(query)
    total = sum(int(r.get('count', 0)) for r in results)
    direct_total = sum(int(r.get('direct_count', 0)) for r in results)
    group_total = sum(int(r.get('group_count', 0)) for r in results)
    ownership_total = sum(int(r.get('ownership_count', 0)) for r in results)
    parent_total = sum(int(r.get('parent_count', 0)) for r in results)

    risk = 'LOW'
    if total > 100:
        risk = 'CRITICAL'
    elif total > 50:
        risk = 'HIGH'
    elif total > 20:
        risk = 'MEDIUM'

    return jsonify({
        'success': True,
        'message': f"Blast Radius: {total} resources exposed ({risk} risk) - {direct_total} direct, {group_total} via groups, {parent_total} via parent",
        'summary': {
            'total': total,
            'direct': direct_total,
            'via_groups': group_total,
            'via_ownership': ownership_total,
            'via_parent': parent_total,
            'risk_level': risk
        },
        'data': results
    })


@app.route('/api/impersonation-paths', methods=['POST'])
def api_impersonation_paths():
    """
    Find impersonation paths from source principal to target principal.
    Discovers how one entity can impersonate another through various attack vectors:
    - Group membership chains
    - Jobs/Notebooks that run as other users
    - Resources (queries, files) owned by other users
    """
    try:
        data = request.get_json() or {}
        source_type = data.get('source_type', 'User')  # User, Group, ServicePrincipal
        source_value = data.get('source', '')
        target_type = data.get('target_type', 'User')
        target_value = data.get('target', '')
        analysis_type = data.get('analysis_type', 'all')  # 'all' or 'shortest'
        max_hops = int(data.get('max_hops', 5))

        # Get run_id from request body, then query params, then fallback to current
        run_id = data.get('run_id') or request.args.get('run_id') or get_current_run_id()
        if not run_id:
            return jsonify({'success': False, 'message': 'No collection runs available', 'paths': []})

        if not source_value or not target_value:
            return jsonify({'success': False, 'message': 'Source and Target are required', 'paths': []})

        # Find source principal
        source_principal = find_principal(source_value, run_id)
        if not source_principal:
            return jsonify({'success': False, 'message': f"Source '{source_value}' not found", 'paths': []})

        # Find target principal
        target_principal = find_principal(target_value, run_id)
        if not target_principal:
            return jsonify({'success': False, 'message': f"Target '{target_value}' not found", 'paths': []})

        source_id = source_principal['id']
        target_id = target_principal['id']
        source_name = source_principal.get('display_name') or source_principal.get('name') or source_principal.get('email') or source_id
        target_name = target_principal.get('display_name') or target_principal.get('name') or target_principal.get('email') or target_id

        print(f"="*60)
        print(f"Finding impersonation paths")
        print(f"Source: {source_name} ({source_principal.get('node_type')})")
        print(f"Target: {target_name} ({target_principal.get('node_type')})")

        # Build graph
        graph, node_info, edge_info = build_graph_from_db(run_id)

        # Find ALL node IDs that match source/target (handles account vs workspace level)
        source_ids = set([source_id])
        target_ids = set([target_id])

        source_email = (source_principal.get('email') or '').lower()
        target_email = (target_principal.get('email') or '').lower()

        for nid, ndata in node_info.items():
            node_email = (ndata.get('email') or '').lower()
            if source_email and node_email == source_email:
                source_ids.add(nid)
            if target_email and node_email == target_email:
                target_ids.add(nid)

        print(f"Source IDs: {source_ids}")
        print(f"Target IDs: {target_ids}")

        # BFS to find paths from source to target
        all_paths = []

        for start_id in source_ids:
            if start_id not in graph:
                continue

            # BFS with path tracking
            queue = [(start_id, [start_id], [])]  # (current_node, path_nodes, path_edges)
            visited_paths = set()

            while queue and len(all_paths) < 100:  # Limit to 100 paths
                current, path_nodes, path_edges = queue.pop(0)

                # Check if we reached target
                if current in target_ids:
                    path_key = tuple(path_nodes)
                    if path_key not in visited_paths:
                        visited_paths.add(path_key)
                        all_paths.append({
                            'nodes': path_nodes,
                            'edges': path_edges
                        })
                    continue

                if len(path_nodes) >= max_hops + 1:
                    continue

                # Explore neighbors
                for neighbor in graph.get(current, []):
                    if neighbor not in path_nodes:  # Avoid cycles
                        edge = edge_info.get((current, neighbor), {})
                        new_path_nodes = path_nodes + [neighbor]
                        new_path_edges = path_edges + [edge]
                        queue.append((neighbor, new_path_nodes, new_path_edges))

        print(f"Found {len(all_paths)} paths")

        # Format paths for response
        formatted_paths = []
        for path in all_paths:
            hops = []
            for i, node_id in enumerate(path['nodes']):
                node_data = node_info.get(node_id, {})
                hop = {
                    'node_id': node_id,
                    'node_name': node_data.get('display_name') or node_data.get('name') or node_id,
                    'node_type': node_data.get('node_type', 'Unknown')
                }
                if i > 0:
                    edge = path['edges'][i-1]
                    hop['edge_relationship'] = edge.get('relationship', '')
                    hop['edge_permission'] = edge.get('permission_level')
                hops.append(hop)

            formatted_paths.append({
                'path_length': len(path['nodes']),
                'hops': hops
            })

        # Sort by path length
        formatted_paths.sort(key=lambda p: p['path_length'])

        # If shortest path only, return just the first one
        if analysis_type == 'shortest' and formatted_paths:
            formatted_paths = [formatted_paths[0]]

        return jsonify({
            'success': True,
            'message': f"Found {len(formatted_paths)} impersonation path(s) from {source_name} to {target_name}",
            'source': {
                'id': source_id,
                'name': source_name,
                'type': source_principal.get('node_type')
            },
            'target': {
                'id': target_id,
                'name': target_name,
                'type': target_principal.get('node_type')
            },
            'paths': formatted_paths
        })

    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"ERROR in impersonation-paths: {error_msg}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f"Server error: {error_msg}",
            'paths': []
        })


@app.route('/api/principals-list')
def api_principals_list():
    """Get list of principals for dropdown selection"""
    run_id = request.args.get('run_id') or get_current_run_id()
    principal_type = request.args.get('type', 'all')  # User, Group, ServicePrincipal, or all

    if not run_id:
        return jsonify({'success': False, 'data': []})

    type_filter = ""
    if principal_type == 'User':
        type_filter = "AND node_type IN ('User', 'AccountUser')"
    elif principal_type == 'Group':
        type_filter = "AND node_type IN ('Group', 'AccountGroup')"
    elif principal_type == 'ServicePrincipal':
        type_filter = "AND node_type IN ('ServicePrincipal', 'AccountServicePrincipal')"
    else:
        type_filter = "AND node_type IN ('User', 'AccountUser', 'Group', 'AccountGroup', 'ServicePrincipal', 'AccountServicePrincipal')"

    # Deduplicate by unique identifier:
    # - Users: email
    # - Groups: name
    # - SPs: application_id (stable identifier across workspace/account levels)
    query = f"""
    WITH ranked_principals AS (
        SELECT
            id,
            display_name,
            name,
            email,
            application_id,
            node_type,
            ROW_NUMBER() OVER (
                PARTITION BY
                    CASE
                        -- Users: dedupe by email
                        WHEN node_type IN ('User', 'AccountUser')
                        THEN LOWER(COALESCE(email, name, id))
                        -- SPs: dedupe by application_id (consistent across workspace/account)
                        WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal')
                        THEN LOWER(COALESCE(application_id, name, id))
                        -- Groups: dedupe by name
                        ELSE LOWER(COALESCE(name, id))
                    END
                ORDER BY
                    -- Prefer Account-level nodes (they typically have more complete info)
                    CASE WHEN node_type LIKE 'Account%' THEN 0 ELSE 1 END,
                    display_name NULLS LAST
            ) as rn
        FROM {VERTICES_TABLE}
        WHERE run_id = '{run_id}'
          {type_filter}
    )
    SELECT
        id,
        -- Format: "Display Name (identifier)" for Users with email, just name for SPs/Groups
        CASE
            WHEN node_type IN ('User', 'AccountUser')
                 AND email IS NOT NULL AND display_name IS NOT NULL AND display_name != email
            THEN CONCAT(display_name, ' (', email, ')')
            WHEN node_type IN ('User', 'AccountUser')
                 AND email IS NOT NULL
            THEN email
            ELSE COALESCE(display_name, name, id)
        END as name,
        email,
        node_type
    FROM ranked_principals
    WHERE rn = 1
    ORDER BY name
    LIMIT 500
    """

    results = exec_query_df(query)
    return jsonify({'success': True, 'data': results})


# ============================================================================
# REPORT ENDPOINTS
# ============================================================================

@app.route('/api/report/isolated')
def report_isolated_principals():
    """
    Find principals with minimal connections in the security graph.
    These may be orphaned accounts or misconfigured users.
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    if not run_id:
        return jsonify({'error': 'No run_id available'})

    # Get all principals with their connectivity metrics
    # Note: Edges may reference principals by id, email, or name, so we need to match on all
    # Deduplicate by email (for Users) or application_id/name (for SPs) to avoid counting same person twice
    # But aggregate counts across ALL vertices for the same logical principal
    query = f"""
    WITH all_principals AS (
        SELECT id, name, email, application_id, node_type, display_name,
            -- Create a canonical key to identify the same logical principal across workspace/account levels
            CASE
                WHEN node_type IN ('User', 'AccountUser')
                THEN LOWER(COALESCE(email, name, id))
                WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal')
                THEN LOWER(COALESCE(application_id, name, id))
                ELSE LOWER(COALESCE(name, id))
            END as principal_key
        FROM {VERTICES_TABLE}
        WHERE run_id = '{run_id}'
          AND node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
    ),
    -- Count group memberships across ALL vertices with the same principal_key
    group_memberships AS (
        SELECT
            p.principal_key,
            COUNT(DISTINCT e.dst) as group_count
        FROM all_principals p
        LEFT JOIN {EDGES_TABLE} e ON e.run_id = '{run_id}'
            AND e.relationship = 'MemberOf'
            AND (e.src = p.id OR e.src = p.email OR e.src = p.name)
        GROUP BY p.principal_key
    ),
    -- Count direct permissions across ALL vertices with the same principal_key
    direct_permissions AS (
        SELECT
            p.principal_key,
            COUNT(DISTINCT e.dst) as permission_count
        FROM all_principals p
        LEFT JOIN {EDGES_TABLE} e ON e.run_id = '{run_id}'
            AND e.permission_level IS NOT NULL
            AND (e.src = p.id OR e.src = p.email OR e.src = p.name)
        GROUP BY p.principal_key
    ),
    -- Count owned resources across ALL vertices with the same principal_key
    owned_resources AS (
        SELECT
            p.principal_key,
            COUNT(DISTINCT v.id) as owned_count
        FROM all_principals p
        LEFT JOIN {VERTICES_TABLE} v ON v.run_id = '{run_id}'
            AND v.owner IS NOT NULL
            AND (v.owner = p.id OR v.owner = p.email OR v.owner = p.name)
        GROUP BY p.principal_key
    ),
    -- Deduplicate to get one row per logical principal (prefer account-level)
    principals AS (
        SELECT id, name, email, application_id, node_type, display_name, principal_key,
            ROW_NUMBER() OVER (
                PARTITION BY principal_key
                ORDER BY
                    CASE node_type
                        WHEN 'AccountUser' THEN 1
                        WHEN 'User' THEN 2
                        WHEN 'AccountServicePrincipal' THEN 1
                        WHEN 'ServicePrincipal' THEN 2
                        ELSE 3
                    END
            ) as rn
        FROM all_principals
    )
    SELECT
        p.id,
        CASE
            -- Users: show "Display Name (email)"
            WHEN p.node_type IN ('User', 'AccountUser') AND p.email IS NOT NULL AND p.email != '' AND COALESCE(p.display_name, p.name) != p.email
            THEN CONCAT(COALESCE(p.display_name, p.name), ' (', p.email, ')')
            -- SPs: show "Display Name (application_id)" if available
            WHEN p.node_type IN ('ServicePrincipal', 'AccountServicePrincipal') AND p.application_id IS NOT NULL AND COALESCE(p.display_name, p.name) != p.application_id
            THEN CONCAT(COALESCE(p.display_name, p.name), ' (', p.application_id, ')')
            ELSE COALESCE(p.display_name, p.name, p.email, p.application_id)
        END as name,
        p.email,
        p.application_id,
        p.node_type,
        COALESCE(gm.group_count, 0) as groups,
        COALESCE(dp.permission_count, 0) as permissions,
        COALESCE(o.owned_count, 0) as owned,
        (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) as connectivity_score,
        CASE
            WHEN COALESCE(gm.group_count, 0) = 0 AND COALESCE(dp.permission_count, 0) = 0 AND COALESCE(o.owned_count, 0) = 0 THEN 'Highly Isolated'
            WHEN (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) < 5 THEN 'Moderately Isolated'
            WHEN (COALESCE(gm.group_count, 0) * 5 + COALESCE(dp.permission_count, 0) + COALESCE(o.owned_count, 0) * 2) < 10 THEN 'Slightly Isolated'
            ELSE 'Well Connected'
        END as isolation_risk
    FROM principals p
    LEFT JOIN group_memberships gm ON p.principal_key = gm.principal_key
    LEFT JOIN direct_permissions dp ON p.principal_key = dp.principal_key
    LEFT JOIN owned_resources o ON p.principal_key = o.principal_key
    WHERE p.rn = 1
    ORDER BY connectivity_score ASC
    """

    results = exec_query_df(query)

    # Calculate summary
    summary = {'highly_isolated': 0, 'moderately_isolated': 0, 'slightly_isolated': 0, 'well_connected': 0}
    for r in results:
        risk = r.get('isolation_risk', 'Well Connected')
        if risk == 'Highly Isolated':
            summary['highly_isolated'] += 1
        elif risk == 'Moderately Isolated':
            summary['moderately_isolated'] += 1
        elif risk == 'Slightly Isolated':
            summary['slightly_isolated'] += 1
        else:
            summary['well_connected'] += 1

    return jsonify({
        'success': True,
        'summary': summary,
        'data': results
    })


@app.route('/api/report/orphaned')
def report_orphaned_resources():
    """
    Find resources with no explicit permission grants.
    These are only accessible via ownership or inheritance.
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    if not run_id:
        return jsonify({'error': 'No run_id available'})

    query = f"""
    WITH granted_resources AS (
        SELECT DISTINCT dst as resource_id
        FROM {EDGES_TABLE}
        WHERE run_id = '{run_id}'
          AND permission_level IS NOT NULL
    )
    SELECT
        v.id,
        v.name,
        v.node_type,
        v.owner
    FROM {VERTICES_TABLE} v
    LEFT JOIN granted_resources gr ON v.id = gr.resource_id
    WHERE gr.resource_id IS NULL
      AND v.run_id = '{run_id}'
      AND v.node_type IN ('Table', 'View', 'Schema', 'Catalog', 'Volume', 'Function')
    ORDER BY v.node_type, v.name
    """

    results = exec_query_df(query)

    # Calculate summary
    types = set()
    for r in results:
        types.add(r.get('node_type', 'Unknown'))

    return jsonify({
        'success': True,
        'summary': {
            'total': len(results),
            'types': len(types)
        },
        'data': results
    })


@app.route('/api/report/overprivileged')
def report_overprivileged_principals():
    """
    Find principals with excessive permissions.
    Identifies users with ALL PRIVILEGES on multiple catalogs or MANAGE on many resources.
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    if not run_id:
        return jsonify({'error': 'No run_id available'})

    query = f"""
    WITH all_principals AS (
        SELECT
            id,
            name,
            email,
            application_id,
            node_type,
            display_name,
            CASE
                WHEN node_type IN ('User', 'AccountUser') THEN LOWER(COALESCE(email, name, id))
                WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal') THEN LOWER(COALESCE(application_id, name, id))
                ELSE LOWER(COALESCE(name, id))
            END as principal_key
        FROM {VERTICES_TABLE}
        WHERE node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND run_id = '{run_id}'
    ),
    permission_counts AS (
        -- Count permissions across ALL node variants with same principal_key
        SELECT
            p.principal_key,
            COUNT(DISTINCT e.dst) as total_resources,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Catalog' THEN r.id END) as catalog_count,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Schema' THEN r.id END) as schema_count,
            COUNT(DISTINCT CASE WHEN r.node_type = 'Table' THEN r.id END) as table_count,
            COUNT(DISTINCT CASE WHEN e.permission_level IN ('ALL PRIVILEGES', 'ALL_PRIVILEGES', 'MANAGE', 'CAN_MANAGE') THEN r.id END) as admin_grants
        FROM {EDGES_TABLE} e
        JOIN all_principals p ON (e.src = p.id OR e.src = p.email OR e.src = p.name)
        JOIN {VERTICES_TABLE} r ON e.dst = r.id AND r.run_id = '{run_id}'
        WHERE e.permission_level IS NOT NULL
          AND e.run_id = '{run_id}'
        GROUP BY p.principal_key
    ),
    deduplicated_principals AS (
        -- Keep one row per principal_key (prefer account-level nodes)
        SELECT
            id as principal_id,
            COALESCE(display_name, name) as principal_name,
            email as principal_email,
            node_type as principal_type,
            principal_key,
            ROW_NUMBER() OVER (
                PARTITION BY principal_key
                ORDER BY
                    CASE
                        WHEN node_type = 'AccountUser' THEN 1
                        WHEN node_type = 'User' THEN 2
                        WHEN node_type = 'AccountServicePrincipal' THEN 1
                        WHEN node_type = 'ServicePrincipal' THEN 2
                        ELSE 3
                    END
            ) as rn
        FROM all_principals
    )
    SELECT
        d.principal_id,
        d.principal_name,
        d.principal_email,
        d.principal_type,
        p.total_resources,
        p.catalog_count,
        p.schema_count,
        p.table_count,
        p.admin_grants,
        CASE
            WHEN p.catalog_count >= 3 OR p.admin_grants >= 10 THEN 'HIGH'
            WHEN p.catalog_count >= 1 OR p.admin_grants >= 5 THEN 'MEDIUM'
            ELSE 'LOW'
        END as risk_level
    FROM deduplicated_principals d
    JOIN permission_counts p ON d.principal_key = p.principal_key
    WHERE d.rn = 1
      AND (p.admin_grants > 0 OR p.catalog_count > 0)
    ORDER BY p.admin_grants DESC, p.catalog_count DESC, p.total_resources DESC
    """

    results = exec_query_df(query)

    # Calculate summary
    summary = {'high': 0, 'medium': 0, 'low': 0}
    for r in results:
        risk = r.get('risk_level', 'LOW').lower()
        if risk in summary:
            summary[risk] += 1

    return jsonify({
        'success': True,
        'summary': summary,
        'data': results
    })


@app.route('/api/report/high-privilege')
def report_high_privilege_principals():
    """
    Find principals with high privilege roles using graph traversal.
    Identifies effective privileges through:
    - Direct group membership to admin groups
    - Nested group membership (group in admin group)
    - Direct permissions (MANAGE/ALL PRIVILEGES on metastores)
    - Ownership (catalog owners with ALL PRIVILEGES)

    Privileged Roles:
    - Account Admin: Members of 'admins' or account admin groups
    - Metastore Admin: MANAGE on metastore or metastore admin groups
    - Workspace Admin: Members of workspace admin groups
    - Catalog Owner: ALL PRIVILEGES or ownership on catalogs
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    if not run_id:
        return jsonify({'error': 'No run_id available'})

    # Query that finds effective high privileges through graph traversal
    # Including nested group membership (up to 3 levels deep)
    # AND direct role assignments via AccountAdmin edge
    query = f"""
    WITH
    -- Account Admins via direct AccountAdmin edge (from roles field in SCIM API)
    -- This captures users/SPs with account_admin role directly assigned
    account_admins_direct AS (
        SELECT DISTINCT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Account Admin' as role,
            'Direct Role' as via,
            'Direct' as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'AccountAdmin'
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND v.run_id = '{run_id}'
    ),

    -- Level 1: Identify admin groups directly
    -- Key distinction: Account-level 'admins' group = Account Admin
    --                  Workspace-level 'admins' group = Workspace Admin
    -- Use both node_type AND id prefix to identify (id prefix is more reliable)
    admin_groups AS (
        SELECT id, name, node_type,
            CASE
                -- Account-level admins group (by node_type OR id prefix) or groups with 'account admin' in name
                WHEN ((node_type = 'AccountGroup' OR id LIKE 'account_group:%') AND LOWER(name) = 'admins')
                     OR LOWER(name) LIKE '%account%admin%' THEN 'Account Admin'
                WHEN LOWER(name) LIKE '%metastore%admin%' THEN 'Metastore Admin'
                -- Workspace-level admins group (not account-level) or groups with 'workspace admin' in name
                WHEN (node_type = 'Group' AND id NOT LIKE 'account_group:%' AND LOWER(name) = 'admins')
                     OR LOWER(name) LIKE '%workspace%admin%'
                     OR LOWER(name) = 'workspace admins' THEN 'Workspace Admin'
            END as admin_role
        FROM {VERTICES_TABLE}
        WHERE run_id = '{run_id}'
          AND node_type IN ('Group', 'AccountGroup')
          AND (LOWER(name) = 'admins'
               OR LOWER(name) LIKE '%account%admin%'
               OR LOWER(name) LIKE '%metastore%admin%'
               OR LOWER(name) LIKE '%workspace%admin%'
               OR LOWER(name) = 'workspace admins')
    ),

    -- Level 2: Groups that are members of admin groups (nested level 1)
    nested_groups_l1 AS (
        SELECT g.id, g.name, g.node_type, ag.admin_role, ag.name as admin_group_name
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON e.src = g.id
        JOIN admin_groups ag ON e.dst = ag.id
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND g.run_id = '{run_id}'
    ),

    -- Level 3: Groups that are members of nested groups (nested level 2)
    nested_groups_l2 AS (
        SELECT g.id, g.name, g.node_type, ng.admin_role, ng.admin_group_name
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} g ON e.src = g.id
        JOIN nested_groups_l1 ng ON e.dst = ng.id
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND g.node_type IN ('Group', 'AccountGroup')
          AND g.run_id = '{run_id}'
    ),

    -- All admin groups (direct + nested)
    all_admin_groups AS (
        SELECT id, name, admin_role, name as via_group, 'Direct' as path_type FROM admin_groups
        UNION ALL
        SELECT id, name, admin_role, admin_group_name as via_group, 'Nested (L1)' as path_type FROM nested_groups_l1
        UNION ALL
        SELECT id, name, admin_role, admin_group_name as via_group, 'Nested (L2)' as path_type FROM nested_groups_l2
    ),

    -- Principals in admin groups (direct or via nested groups)
    principals_via_groups AS (
        SELECT DISTINCT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            aag.admin_role as role,
            aag.name as via,
            CASE aag.path_type
                WHEN 'Direct' THEN 'Group'
                ELSE 'Nested'
            END as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
        JOIN all_admin_groups aag ON e.dst = aag.id
        WHERE e.run_id = '{run_id}'
          AND e.relationship = 'MemberOf'
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND v.run_id = '{run_id}'
    ),

    -- Metastore admins via direct permission
    metastore_admins_direct AS (
        SELECT DISTINCT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Metastore Admin' as role,
            m.name as via,
            'Direct' as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
        JOIN {VERTICES_TABLE} m ON e.dst = m.id
        WHERE e.run_id = '{run_id}'
          AND m.node_type = 'Metastore'
          AND e.permission_level IN ('MANAGE', 'ALL PRIVILEGES', 'ALL_PRIVILEGES', 'CAN_MANAGE')
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND v.run_id = '{run_id}'
          AND m.run_id = '{run_id}'
    ),

    -- Catalog owners (have full control)
    catalog_owners AS (
        SELECT DISTINCT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Catalog Owner' as role,
            c.name as via,
            'Owner' as access_type
        FROM {VERTICES_TABLE} c
        JOIN {VERTICES_TABLE} v ON (c.owner = v.id OR c.owner = v.email OR c.owner = v.name)
        WHERE c.run_id = '{run_id}'
          AND c.node_type = 'Catalog'
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND v.run_id = '{run_id}'
    ),

    -- Catalog ALL PRIVILEGES holders
    catalog_all_privileges AS (
        SELECT DISTINCT
            v.id as principal_id,
            COALESCE(v.display_name, v.name, v.email) as principal_name,
            v.email as principal_email,
            v.node_type as principal_type,
            'Catalog Owner' as role,
            c.name as via,
            'Grant' as access_type
        FROM {EDGES_TABLE} e
        JOIN {VERTICES_TABLE} v ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
        JOIN {VERTICES_TABLE} c ON e.dst = c.id
        WHERE e.run_id = '{run_id}'
          AND c.node_type = 'Catalog'
          AND e.permission_level IN ('ALL PRIVILEGES', 'ALL_PRIVILEGES')
          AND v.node_type IN ('User', 'ServicePrincipal', 'AccountUser', 'AccountServicePrincipal')
          AND v.run_id = '{run_id}'
          AND c.run_id = '{run_id}'
    )

    SELECT principal_id, principal_name, principal_email, principal_type, role, via, access_type
    FROM (
        SELECT * FROM account_admins_direct
        UNION ALL
        SELECT * FROM principals_via_groups
        UNION ALL
        SELECT * FROM metastore_admins_direct
        UNION ALL
        SELECT * FROM catalog_owners
        UNION ALL
        SELECT * FROM catalog_all_privileges
    )
    ORDER BY
        CASE role
            WHEN 'Account Admin' THEN 1
            WHEN 'Metastore Admin' THEN 2
            WHEN 'Workspace Admin' THEN 3
            WHEN 'Catalog Owner' THEN 4
            ELSE 5
        END,
        CASE principal_type
            WHEN 'User' THEN 1
            WHEN 'AccountUser' THEN 1
            WHEN 'ServicePrincipal' THEN 2
            WHEN 'AccountServicePrincipal' THEN 2
            ELSE 3
        END,
        principal_name
    """

    results = exec_query_df(query)

    # Build summary
    summary = {
        'account_admin': 0,
        'metastore_admin': 0,
        'workspace_admin': 0,
        'catalog_owner': 0,
        'total_principals': set()
    }

    for r in results:
        role = r.get('role', '')
        pid = r.get('principal_id', '')
        summary['total_principals'].add(pid)

        if role == 'Account Admin':
            summary['account_admin'] += 1
        elif role == 'Metastore Admin':
            summary['metastore_admin'] += 1
        elif role == 'Workspace Admin':
            summary['workspace_admin'] += 1
        elif role == 'Catalog Owner':
            summary['catalog_owner'] += 1

    summary['total_principals'] = len(summary['total_principals'])

    return jsonify({
        'success': True,
        'summary': summary,
        'data': results
    })


@app.route('/api/report/secret-scope-access')
def report_secret_scope_access():
    """
    Find principals with access to secret scopes.
    Shows who can READ, WRITE, or MANAGE secrets.
    Supports optional filters: workspace_id, scope_name
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    workspace_id = request.args.get('workspace_id', '')
    scope_name_filter = request.args.get('scope_name', '')

    if not run_id:
        return jsonify({'error': 'No run_id available'})

    # Build additional WHERE clauses for filters
    filter_clauses = ""
    if scope_name_filter:
        safe_scope = sanitize(scope_name_filter)
        filter_clauses += f" AND s.name = '{safe_scope}'"
    if workspace_id:
        safe_ws = sanitize(workspace_id)
        # Filter by workspace_id in properties JSON
        filter_clauses += f" AND s.properties LIKE '%\"workspace_id\": \"{safe_ws}\"%'"

    query = f"""
    WITH all_principals AS (
        SELECT
            id,
            name,
            email,
            application_id,
            node_type,
            display_name,
            CASE
                WHEN node_type IN ('User', 'AccountUser') THEN LOWER(COALESCE(email, name, id))
                WHEN node_type IN ('ServicePrincipal', 'AccountServicePrincipal') THEN LOWER(COALESCE(application_id, name, id))
                WHEN node_type IN ('Group', 'AccountGroup') THEN LOWER(COALESCE(name, id))
                ELSE LOWER(COALESCE(name, id))
            END as principal_key
        FROM {VERTICES_TABLE}
        WHERE run_id = '{run_id}'
          AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ),
    secret_access AS (
        SELECT DISTINCT
            p.principal_key,
            s.name as scope_name,
            s.properties as scope_properties,
            e.permission_level,
            e.relationship
        FROM {EDGES_TABLE} e
        JOIN all_principals p ON (e.src = p.id OR e.src = p.email OR e.src = p.name)
        JOIN {VERTICES_TABLE} s ON e.dst = s.id AND s.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND s.node_type = 'SecretScope'
          AND e.permission_level IS NOT NULL
          {filter_clauses}
    ),
    deduplicated_principals AS (
        SELECT
            id,
            COALESCE(display_name, name, email, application_id) as principal_name,
            email as principal_email,
            node_type as principal_type,
            principal_key,
            ROW_NUMBER() OVER (
                PARTITION BY principal_key
                ORDER BY
                    CASE
                        WHEN node_type = 'AccountUser' THEN 1
                        WHEN node_type = 'User' THEN 2
                        WHEN node_type = 'AccountGroup' THEN 1
                        WHEN node_type = 'Group' THEN 2
                        WHEN node_type = 'AccountServicePrincipal' THEN 1
                        WHEN node_type = 'ServicePrincipal' THEN 2
                        ELSE 3
                    END
            ) as rn
        FROM all_principals
    )
    SELECT
        d.id as principal_id,
        d.principal_name,
        d.principal_email,
        d.principal_type,
        sa.scope_name,
        sa.scope_properties,
        sa.permission_level,
        sa.relationship
    FROM secret_access sa
    JOIN deduplicated_principals d ON sa.principal_key = d.principal_key AND d.rn = 1
    ORDER BY
        CASE d.principal_type
            WHEN 'User' THEN 1
            WHEN 'AccountUser' THEN 1
            WHEN 'Group' THEN 2
            WHEN 'AccountGroup' THEN 2
            WHEN 'ServicePrincipal' THEN 3
            WHEN 'AccountServicePrincipal' THEN 3
            ELSE 4
        END,
        d.principal_name,
        sa.scope_name
    """

    results = exec_query_df(query)

    # Group by principal type for summary
    summary = {'users': 0, 'groups': 0, 'service_principals': 0, 'total_scopes': set()}
    principals_seen = {'users': set(), 'groups': set(), 'sps': set()}

    for r in results:
        ptype = r.get('principal_type', '')
        pid = r.get('principal_id', '')
        scope = r.get('scope_name', '')
        summary['total_scopes'].add(scope)

        if 'User' in ptype:
            principals_seen['users'].add(pid)
        elif 'Group' in ptype:
            principals_seen['groups'].add(pid)
        elif 'ServicePrincipal' in ptype:
            principals_seen['sps'].add(pid)

    summary['users'] = len(principals_seen['users'])
    summary['groups'] = len(principals_seen['groups'])
    summary['service_principals'] = len(principals_seen['sps'])
    summary['total_scopes'] = len(summary['total_scopes'])

    return jsonify({
        'success': True,
        'summary': summary,
        'data': results
    })


@app.route('/api/report/secret-scopes-filters')
def report_secret_scopes_filters():
    """
    Get available workspaces and secret scopes for filter dropdowns.
    """
    run_id = request.args.get('run_id') or get_current_run_id()
    workspace_id = request.args.get('workspace_id', '')

    if not run_id:
        return jsonify({'error': 'No run_id available', 'run_id_received': run_id})

    # Debug: Check what node_types exist that contain 'Secret'
    try:
        debug_query = f"""
        SELECT node_type, COUNT(*) as cnt
        FROM {VERTICES_TABLE}
        WHERE run_id = '{run_id}'
          AND (LOWER(node_type) LIKE '%secret%')
        GROUP BY node_type
        """
        debug_node_types = exec_query_df(debug_query)
    except:
        debug_node_types = []

    # Get all secret scopes with their workspace info from properties
    scopes_query = f"""
    SELECT
        id as scope_id,
        name as scope_name,
        properties as scope_properties
    FROM {VERTICES_TABLE}
    WHERE run_id = '{run_id}'
      AND node_type = 'SecretScope'
    """

    query_error = None
    try:
        scopes_results = exec_query_df(scopes_query)
    except Exception as e:
        scopes_results = []
        query_error = str(e)

    # Parse workspace info from scope properties and build lists
    workspaces = {}  # {workspace_id: workspace_name}
    scopes = []  # [{scope_id, scope_name, workspace_id, workspace_name}]

    import json

    for r in scopes_results:
        scope_id = r.get('scope_id', '')
        scope_name = r.get('scope_name', '')
        props_raw = r.get('scope_properties')

        # Parse properties - could be JSON string, dict, or None
        props = {}
        if props_raw:
            if isinstance(props_raw, dict):
                props = props_raw
            elif isinstance(props_raw, str):
                try:
                    props = json.loads(props_raw)
                except:
                    props = {}

        # Also try to extract workspace from scope_id (format: ws_{ws_id}_secret_scope:{name})
        ws_id = props.get('workspace_id', '')
        ws_name = props.get('workspace_name', '')

        if not ws_id and scope_id and scope_id.startswith('ws_'):
            # Extract from ID format: ws_{ws_id}_secret_scope:{name}
            try:
                parts = scope_id.split('_')
                if len(parts) >= 2:
                    ws_id = parts[1]
            except:
                pass

        if ws_id and ws_name:
            workspaces[ws_id] = ws_name

        scopes.append({
            'scope_id': scope_id,
            'scope_name': scope_name,
            'workspace_id': ws_id,
            'workspace_name': ws_name
        })

    # Convert workspaces dict to sorted list
    workspace_list = [{'id': k, 'name': v} for k, v in workspaces.items()]
    workspace_list.sort(key=lambda x: x['name'])

    # Filter scopes by workspace if specified
    if workspace_id:
        scopes = [s for s in scopes if s['workspace_id'] == workspace_id]

    # Debug: include raw scope count for troubleshooting
    return jsonify({
        'success': True,
        'workspaces': workspace_list,
        'scopes': scopes,
        'debug': {
            'run_id': run_id,
            'total_scopes_found': len(scopes_results),
            'workspaces_extracted': len(workspaces),
            'secret_node_types': debug_node_types,
            'query_error': query_error,
            'query': scopes_query.strip()
        }
    })


if __name__ == '__main__':
    # Debug mode should be explicitly enabled via environment variable
    # Never enable debug=True in production - it exposes sensitive information
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=8000, debug=debug_mode)
