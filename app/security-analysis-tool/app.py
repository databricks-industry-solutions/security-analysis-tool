#!/usr/bin/env python3
"""
Permissions Analysis Tool - Databricks Security Analysis Platform

A modern, dashboard-style security analysis app for Databricks environments.
Inspired by BloodHound for Active Directory analysis.
"""

from flask import Flask, request, jsonify, send_from_directory
import os
import re
import json
import time
import uuid
import logging
import threading
from databricks.sdk import WorkspaceClient

# Strict allowlist for run_id values used in SQL identifier positions. The
# collector generates run_ids in the format `YYYYMMDD_HHMMSS_<hex>` (see
# notebooks/permission_analysis_data_collection.py); we accept anything that
# could plausibly be a run_id across older schemas but refuse anything that
# could escape a SQL string literal.
_VALID_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_run_id(value):
    """Return value if it is a well-formed run_id, else None."""
    if value is None:
        return None
    value = str(value)
    if _VALID_RUN_ID_RE.match(value):
        return value
    return None

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

# Configuration - Read from environment variables (set in app.yaml)
# These MUST be configured in app.yaml - no hardcoded defaults
logger.info("[CONFIG] Environment variables check:")
logger.info(f"  BRICKHOUND_SCHEMA = {os.getenv('BRICKHOUND_SCHEMA')}")
logger.info(f"  WAREHOUSE_ID = {os.getenv('WAREHOUSE_ID')}")

# Validate required environment variables
BRICKHOUND_SCHEMA = os.getenv("BRICKHOUND_SCHEMA")

# Parse catalog.schema from environment variable.
# The secret written by dabs/sat/config.py wraps the catalog in backticks
# (`catalog`.schema) for SQL identifier quoting — necessary for catalog
# names containing dashes. Strip the backticks here because the Statement
# Execution API's `catalog`/`schema` bind params expect bare identifiers;
# the SQL statements below re-quote explicitly.
if BRICKHOUND_SCHEMA:
    _clean = BRICKHOUND_SCHEMA.replace("`", "").strip()
    parts = _clean.split(".")
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

# Define table names. Backtick-quote each identifier so catalog/schema
# names containing special characters (dashes, reserved words) are safe
# to interpolate into SQL.
VERTICES_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_vertices"
EDGES_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_edges"
METADATA_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_collection_metadata"
SHARED_TO_ACCOUNT_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_shared_to_account"
PRIVILEGED_NON_IDP_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_privileged_non_idp"
DENYLIST_CANDIDATES_TABLE = f"`{CATALOG}`.`{SCHEMA}`.brickhound_denylist_candidates"

logger.info(f"[CONFIG FINAL] CATALOG={CATALOG}, SCHEMA={SCHEMA}")
logger.info(f"[CONFIG FINAL] VERTICES_TABLE={VERTICES_TABLE}")
logger.info(f"[CONFIG FINAL] EDGES_TABLE={EDGES_TABLE}")
logger.info(f"[CONFIG FINAL] METADATA_TABLE={METADATA_TABLE}")

# Global variable to cache the current run_id for this session
_cached_run_id = None


class NoAccessError(Exception):
    """Raised when the calling user lacks UC SELECT on the permissions-graph tables.

    Caught by the Flask errorhandler below and rendered as a friendly banner
    rather than a 500 / SQL stack trace.
    """


def _looks_like_no_access(exc):
    """Detect UC permission, missing-grant, or missing-OBO-scope errors.

    Matches three classes of failure that should render as a friendly
    no-access banner rather than a generic 500 / silent empty result:
      1. Typed `PermissionDenied` / `Unauthenticated` from the Databricks
         SDK (preferred — the SDK does expose these for `execute_statement`).
      2. `403 Forbidden` with `Invalid scope, required scopes: sql` —
         user authorization is configured but the `sql` scope isn't in
         the scope list.
      3. Message-based fallback covering UC permission errors and
         "table/schema/catalog does not exist" (UC hides resources the
         caller can't see).
    """
    try:
        from databricks.sdk.errors.platform import (
            PermissionDenied, Unauthenticated,
        )
        if isinstance(exc, (PermissionDenied, Unauthenticated)):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    keywords = (
        "invalid scope",
        "required scopes",
        "permission denied",
        "permissiondenied",
        "access denied",
        "not authorized",
        "unauthorized",
        "insufficient_permissions",
        "403 forbidden",
        "does not exist",       # UC returns "table or view ... does not exist" when the user can't see it
        "table_not_found",
        "schema_not_found",
        "catalog_not_found",
    )
    return any(k in msg for k in keywords)


def _log_no_access_detail(exc):
    """Record the underlying error verbatim.

    The user-facing banner is deliberately short, which makes diagnosis hard when
    the guess is wrong. This keeps the raw provider message in the app log.
    """
    logger.warning("no_access underlying error: %r", exc)


def _no_access_message(exc=None):
    """Pick the most accurate banner text based on the underlying error.

    Two distinct failure modes:
      * Missing OAuth scope on the app — the platform forwards a token but
        it doesn't carry `sql`, so the warehouse rejects with
        "Invalid scope, required scopes: sql". Fix is on the app config.
      * Missing UC grant — the user lacks SELECT on the permissions-graph
        tables. Fix is on the schema grants.
    """
    msg = str(exc).lower() if exc is not None else ""
    if exc is not None:
        _log_no_access_detail(exc)
    if "invalid scope" in msg or "required scopes" in msg:
        return (
            "This app needs your permission to run queries on your behalf.\n\n"
            "Sign out and sign back in to grant it: open the account menu in the "
            "top-right of the app and choose Sign out, then reload this page and "
            "accept the access request. Your existing sign-in was issued before "
            "query access was enabled, so it cannot be upgraded in place.\n\n"
            "The app only ever reads data, and only what your own Unity Catalog "
            "permissions already allow."
        )

    return (
        "You don't have read access to the security analysis data.\n\n"
        "This app shows only what your own Unity Catalog permissions allow, so "
        f"nothing is displayed until you are granted SELECT on the "
        f"{CATALOG}.{SCHEMA} schema.\n\n"
        "Ask whoever administers your Databricks account for read access to that "
        "schema, then reload this page."
    )


def get_user_email():
    """Return the calling user's email from Databricks Apps headers.

    `X-Forwarded-Email` is set by the Apps platform on every request reaching
    the app process. Falls back to 'unknown' for local-dev / non-Apps contexts.
    """
    try:
        return request.headers.get("X-Forwarded-Email", "unknown")
    except RuntimeError:
        # Outside a request context (e.g. module import) — return unknown.
        return "unknown"



def _token_has_sql_scope(token):
    """Whether a forwarded user token carries the `sql` scope.

    Databricks Apps forwards a user token whenever user authorization is enabled,
    but that token only carries the scopes the platform has actually minted for
    the app. A token without `sql` cannot call the Statement Execution API, and
    the failure surfaces late as a confusing permission error — so it is checked
    up front by reading the token's own claims.

    Returns True when the scope is present, False when provably absent, and True
    when the token cannot be decoded (fail open, so an unexpected token format
    does not disable on-behalf-of-user access).
    """
    if not token:
        return False
    try:
        import base64
        parts = token.split(".")
        if len(parts) < 2:
            return True
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001
        return True
    scope_claim = claims.get("scope") or claims.get("scp") or ""
    scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim)
    return "sql" in scopes


def get_connection():
    """Get a Databricks SDK client, preferring the calling user's identity (OBO).

    When the Apps platform forwards the user's OAuth token via the
    `x-forwarded-access-token` header, we build a per-request WorkspaceClient
    bound to that token. This makes every Statement Execution run as the
    user, so UC enforces the user's grants on the permissions-graph tables.

    If the header is absent (user authorization not configured for this app
    in the Databricks UI, or local dev), we fall back to the app SP. This
    keeps the app working during the OBO migration and surfaces a one-time
    warning so an admin can finish the configuration.
    """
    user_token = None
    try:
        user_token = request.headers.get("x-forwarded-access-token")
    except RuntimeError:
        # Outside a request context — keep user_token None and use SP.
        pass

    # A forwarded token that lacks the `sql` scope cannot call the Statement
    # Execution API.
    #
    # The app does NOT quietly fall back to its service principal here: doing so
    # shows every viewer the same data while looking identical to per-user
    # filtering, which is exactly the wrong failure mode for a security tool. The
    # request fails with an explanation instead.
    #
    # ALLOW_SERVICE_PRINCIPAL_FALLBACK=true opts into the shared-visibility mode
    # for deployments where per-user filtering is not required and every viewer is
    # already trusted with the whole dataset.
    if user_token and not _token_has_sql_scope(user_token):
        allow_fallback = (
            os.getenv("ALLOW_SERVICE_PRINCIPAL_FALLBACK", "false").strip().lower()
            == "true"
        )
        if not allow_fallback:
            raise NoAccessError(
                "This app cannot query on your behalf yet.\n\n"
                "Your sign-in does not include query access, so the app has no way "
                "to read the security tables as you. Rather than showing data that "
                "is not filtered to your own permissions, it stops here.\n\n"
                "An administrator can resolve this by recreating the app with query "
                "access enabled, which is how per-user filtering is granted."
            )
        if not hasattr(get_connection, "_scope_fallback_logged"):
            logger.warning(
                "Forwarded user token lacks the `sql` scope and "
                "ALLOW_SERVICE_PRINCIPAL_FALLBACK is enabled: querying as the app "
                "service principal. Results are NOT filtered per user."
            )
            get_connection._scope_fallback_logged = True
        user_token = None
        get_connection._degraded_to_sp = True

    if user_token:
        # `auth_type="pat"` is required: without it the SDK's auth resolver
        # sees the user's bearer token AND the app SP env vars
        # (DATABRICKS_CLIENT_ID/SECRET injected by Databricks Apps) and
        # raises `more than one authorization method configured: oauth and
        # pat`. Pinning auth_type forces the SDK to use only the user token.
        # `host` must also be explicit so the env-driven OAuth path is fully
        # bypassed.
        workspace_client = WorkspaceClient(
            host=os.getenv("DATABRICKS_HOST"),
            token=user_token,
            auth_type="pat",
        )
        if not hasattr(get_connection, "_obo_logged"):
            logger.info(
                "OBO mode: forwarding user access token (host=%s, user=%s)",
                workspace_client.config.host, get_user_email(),
            )
            get_connection._obo_logged = True
    else:
        workspace_client = WorkspaceClient()
        if not hasattr(get_connection, "_sp_logged"):
            logger.warning(
                "App SP mode: no x-forwarded-access-token on request. Configure user "
                "authorization for this app in the Databricks UI to enable OBO."
            )
            logger.info(
                "Connected as app SP: host=%s auth_type=%s",
                workspace_client.config.host, workspace_client.config.auth_type,
            )
            get_connection._sp_logged = True

    warehouse_id = os.getenv("WAREHOUSE_ID") or os.getenv("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        error_msg = (
            "FATAL: WAREHOUSE_ID environment variable is not set in app.yaml.\n"
            "Please configure WAREHOUSE_ID with a valid SQL warehouse ID before deploying."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not hasattr(get_connection, "_warehouse_logged"):
        logger.info("Using SQL Warehouse: %s", warehouse_id)
        get_connection._warehouse_logged = True

    return workspace_client, warehouse_id


def _build_sdk_parameters(params):
    """Map a {name: value} dict to the SDK's parameter list shape.

    Each value is sent as STRING — Databricks SQL coerces from there into
    the column type at execution time. Lazy import so older SDKs that
    don't expose StatementParameterListItem at this path don't break the
    no-params codepath.
    """
    if not params:
        return None
    from databricks.sdk.service.sql import StatementParameterListItem
    return [
        StatementParameterListItem(
            name=name,
            value=None if value is None else str(value),
            type="STRING",
        )
        for name, value in params.items()
    ]


def exec_query(sql_query, params=None):
    """Execute query and return first column of first row.

    `params` is a {name: value} dict bound to `:name` placeholders in
    the SQL. Always prefer bind params over string interpolation for
    user-controlled values.

    UC permission errors are translated to NoAccessError so the Flask
    errorhandler can render a friendly banner instead of a 500.
    """
    try:
        workspace_client, warehouse_id = get_connection()
        kwargs = {
            "warehouse_id": warehouse_id,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "statement": sql_query,
            "wait_timeout": "30s",
        }
        sdk_params = _build_sdk_parameters(params)
        if sdk_params:
            kwargs["parameters"] = sdk_params
        result = workspace_client.statement_execution.execute_statement(**kwargs)
        if hasattr(result, 'result') and result.result:
            if hasattr(result.result, 'data_array') and result.result.data_array:
                value = result.result.data_array[0][0]
                return int(value) if value else 0
        return 0
    except NoAccessError:
        raise
    except Exception as e:
        if _looks_like_no_access(e):
            raise NoAccessError(_no_access_message(e)) from e
        logger.exception("executing query")
        return 0


def exec_query_df(sql_query, params=None):
    """Execute query and return results as list of dicts.

    `params` is a {name: value} dict bound to `:name` placeholders in
    the SQL. Always prefer bind params over string interpolation for
    user-controlled values.

    UC permission errors are translated to NoAccessError so the Flask
    errorhandler can render a friendly banner instead of a 500.
    """
    try:
        workspace_client, warehouse_id = get_connection()
        kwargs = {
            "warehouse_id": warehouse_id,
            "catalog": CATALOG,
            "schema": SCHEMA,
            "statement": sql_query,
            "wait_timeout": "50s",
        }
        sdk_params = _build_sdk_parameters(params)
        if sdk_params:
            kwargs["parameters"] = sdk_params
        result = workspace_client.statement_execution.execute_statement(**kwargs)
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
    except NoAccessError:
        raise
    except Exception as e:
        if _looks_like_no_access(e):
            raise NoAccessError(_no_access_message(e)) from e
        logger.exception("executing query")
        return []


def _truthy(val):
    """Coerce a Statement-Execution cell to a bool.

    The SQL Statement Execution API returns every value as a string, so a
    BOOLEAN column arrives as 'true'/'false'. Treat those (and real bools)
    consistently; anything else is falsy.
    """
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() == 'true'


def get_latest_run_id():
    """Get the most recent run_id from collection_metadata"""
    try:
        result = exec_query_df(f"""
            SELECT run_id FROM {METADATA_TABLE}
            ORDER BY collection_timestamp DESC LIMIT 1
        """)
        if result and len(result) > 0:
            value = result[0].get('run_id') or result[0].get('col0')
            return _validate_run_id(value)
        return None
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception as e:
        logger.exception("getting latest run_id")
        return None


def get_current_run_id():
    """Get run_id from request params, body, or default to latest.

    Every path is validated against _VALID_RUN_ID_RE before return so that
    callers can safely interpolate the value into SQL string literals. An
    invalid user-supplied run_id falls through to the next source (body,
    cache, latest) rather than being returned raw.
    """
    global _cached_run_id
    # Check if run_id is in request args (GET parameters)
    run_id = _validate_run_id(request.args.get('run_id'))
    if run_id:
        return run_id
    # Check if run_id is in request body (POST requests)
    if request.is_json:
        data = request.get_json(silent=True)
        if data:
            run_id = _validate_run_id(data.get('run_id'))
            if run_id:
                return run_id
    # Use cached run_id if available
    if _cached_run_id:
        return _cached_run_id
    # Otherwise get the latest
    _cached_run_id = get_latest_run_id()
    return _cached_run_id


def get_available_runs(limit=10):
    """Get list of available collection runs"""
    logger.debug(f"get_available_runs called, METADATA_TABLE={METADATA_TABLE}")
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
        logger.debug(f"Executing query: {query[:100]}...")
        result = exec_query_df(query)
        logger.debug(f"Query returned {len(result) if result else 0} rows")
        return result
    except NoAccessError:
        # Don't fall back — the user lacks access; surface the friendly banner.
        raise
    except Exception as e:
        logger.exception("Error getting available runs with new columns")
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
            logger.debug(f"Executing fallback query: {query2[:100]}...")
            result = exec_query_df(query2)
            logger.debug(f"Fallback query returned {len(result) if result else 0} rows")
            return result
        except NoAccessError:
            raise
        except Exception as e2:
            logger.exception("Error getting available runs (fallback)")
            return []


def get_collection_coverage(run_id=None):
    """Get workspace coverage information for a collection run"""
    import json
    if not run_id:
        run_id = get_current_run_id()

    if not run_id:
        return None

    try:
        result = exec_query_df(
            f"""
            SELECT workspaces_collected, workspaces_failed, collection_mode,
                   CAST(collection_timestamp AS STRING) as collection_timestamp,
                   collected_by, vertices_count, edges_count
            FROM {METADATA_TABLE}
            WHERE run_id = :run_id
            LIMIT 1
            """,
            params={"run_id": run_id},
        )
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
    except NoAccessError:
        raise
    except Exception as e:
        logger.exception("getting collection coverage with new columns")
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
    """Escape a string for safe use as a SQL string literal.

    DEPRECATED — prefer bind parameters via `exec_query_df(..., params=...)`
    over interpolating sanitized values. This helper is kept for sites
    that build dynamic SQL fragments (e.g. IN-list construction over
    runtime-determined principal-ID variants); those will be migrated to
    parameterized queries in a follow-up pass.

    Escapes both single quotes and backslashes — Spark SQL's default
    string parser doesn't honor backslash escapes, but defense-in-depth
    against future parser changes (or operators that read these values
    via Spark configurations that DO honor escapes) is cheap.
    """
    if not value:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "''")
    )


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
    # Order by node_type to prefer AccountUser/AccountGroup/AccountServicePrincipal
    # These have account-level group memberships with WorkspaceAccess edges
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = :run_id
      AND (id = :ident
       OR LOWER(email) = LOWER(:ident)
       OR LOWER(name) = LOWER(:ident)
       OR LOWER(display_name) = LOWER(:ident))
    AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    ORDER BY CASE
        WHEN node_type = 'AccountUser' THEN 1
        WHEN node_type = 'AccountGroup' THEN 2
        WHEN node_type = 'AccountServicePrincipal' THEN 3
        ELSE 4
    END
    LIMIT 1
    """
    results = exec_query_df(query, params={"run_id": run_id, "ident": identifier})
    return results[0] if results else None


def find_account_principal(identifier, run_id):
    """Find the account-level version of a principal (AccountUser/AccountGroup/AccountServicePrincipal).

    This is used to resolve workspace access via account-level group memberships.
    """
    if not identifier:
        return None
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = :run_id
      AND (id = :ident
       OR LOWER(email) = LOWER(:ident)
       OR LOWER(name) = LOWER(:ident)
       OR LOWER(display_name) = LOWER(:ident))
    AND node_type IN ('AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    LIMIT 1
    """
    results = exec_query_df(query, params={"run_id": run_id, "ident": identifier})
    return results[0] if results else None


def find_resource(identifier, run_id):
    """Find a resource by ID, name, or display_name"""
    if not identifier:
        return None
    query = f"""
    SELECT id, name, display_name, email, node_type, owner
    FROM {VERTICES_TABLE}
    WHERE run_id = :run_id
      AND (id = :ident
       OR LOWER(name) = LOWER(:ident)
       OR LOWER(display_name) = LOWER(:ident))
    AND node_type NOT IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
    LIMIT 1
    """
    results = exec_query_df(query, params={"run_id": run_id, "ident": identifier})
    return results[0] if results else None


# ============================================================================
# Request lifecycle: audit log + friendly no-access handler
# ============================================================================


@app.before_request
def _audit_log_request():
    """Emit one info-level log line per API request capturing the calling
    user's identity (from Databricks Apps `X-Forwarded-Email`), the path,
    and the upstream client IP. Provides per-user attribution without
    requiring OBO to be configured.
    """
    if request.path.startswith("/api/") or request.path == "/":
        logger.info(
            "request: path=%s user=%s ip=%s req_id=%s",
            request.path,
            get_user_email(),
            request.headers.get("X-Real-Ip", "-"),
            request.headers.get("X-Request-Id", "-"),
        )


@app.after_request
def _security_headers(resp):
    """Apply baseline security headers on every response.

    The inline `<script>` and `<style>` blocks in get_main_html() require
    `'unsafe-inline'` on script-src/style-src. Pulling that JS/CSS out into
    served static files is a separate refactor; until then this header
    set still adds meaningful defense-in-depth against MIME sniffing,
    referrer leaks, and outbound resource loads.

    `X-Frame-Options` is intentionally not set — the app is rendered in
    the Databricks Apps UI inside an iframe, and a stricter value would
    break that integration. Frame ancestry is left to the Databricks
    platform's reverse proxy.
    """
    resp.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ))
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.errorhandler(NoAccessError)
def _no_access_handler(exc):
    """Translate a NoAccessError raised from exec_query[_df] into a friendly
    JSON banner the UI can render. The full stack trace is left in app
    logs (logger.exception) for admins to triage.
    """
    logger.warning(
        "no_access: user=%s path=%s message=%s",
        get_user_email(), request.path, str(exc),
    )
    return jsonify({
        "error": "no_access",
        "message": str(exc),
    }), 403


# ============================================================================
# MAIN UI
# ============================================================================

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static assets (e.g. the favicon) from the app's static/ dir."""
    return send_from_directory(_STATIC_DIR, filename)


@app.route('/favicon.svg')
def favicon():
    return send_from_directory(_STATIC_DIR, "favicon.svg")


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
    <title>Security Analysis Tool</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
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
        /* ---------------------------------------------------------------
           Security assistant — floating launcher and slide-over panel.
           Fixed position so it is reachable from every page without taking
           a nav slot.
           --------------------------------------------------------------- */
        .assistant-fab {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 52px;
            height: 52px;
            border-radius: 26px;
            border: none;
            cursor: pointer;
            z-index: 1200;
            display: grid;
            place-items: center;
            color: #fff;
            background: linear-gradient(135deg, #667eea 0%, #8b5cf6 100%);
            box-shadow: 0 8px 24px rgba(102, 126, 234, .42);
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .assistant-fab:hover { transform: translateY(-2px); box-shadow: 0 12px 30px rgba(102,126,234,.55); }
        .assistant-fab svg { width: 23px; height: 23px; }
        .assistant-fab.hidden { display: none; }
        /* The settings drawer sits above the assistant button, which would
           otherwise float over the panel's content. */
        body.drawer-open .assistant-fab { opacity: 0; pointer-events: none; }

        .assistant-panel {
            position: fixed;
            top: 0;
            right: 0;
            bottom: 0;
            width: 460px;
            max-width: 94vw;
            background: var(--bg-card);
            border-left: 1px solid var(--border);
            box-shadow: -14px 0 40px rgba(0, 0, 0, .5);
            z-index: 1300;
            display: flex;
            flex-direction: column;
            transform: translateX(100%);
            transition: transform .22s ease;
        }
        .assistant-panel.open { transform: translateX(0); }

        .assistant-head {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 14px 16px;
            border-bottom: 1px solid var(--border);
        }
        .assistant-head-mark {
            width: 28px; height: 28px; flex: 0 0 28px;
            border-radius: 8px;
            display: grid; place-items: center;
            background: linear-gradient(135deg, #667eea 0%, #8b5cf6 100%);
            color: #fff;
        }
        .assistant-head-mark svg { width: 15px; height: 15px; }
        .assistant-head-title { font-weight: 650; font-size: .96em; }
        .assistant-head-sub { font-size: .72em; color: var(--text-muted); }
        .assistant-close {
            background: transparent; border: none; cursor: pointer;
            color: var(--text-muted); font-size: 1.25em; line-height: 1;
        }
        .assistant-close:hover { background: var(--bg-input); color: var(--text-primary); }

        /* Header actions sit together at the right edge. */
        .assistant-head-actions {
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 2px;
            flex: 0 0 auto;
        }
        .assistant-icon-btn {
            background: transparent;
            border: none;
            cursor: pointer;
            color: var(--text-muted);
            padding: 4px;
            border-radius: 6px;
            display: grid;
            place-items: center;
            flex: 0 0 auto;
        }
        .assistant-icon-btn:hover { background: var(--bg-input); color: var(--text-primary); }
        .assistant-icon-btn svg { width: 15px; height: 15px; }
        .assistant-icon-btn,
        .assistant-close {
            width: 28px;
            height: 28px;
            padding: 0;
            display: grid;
            place-items: center;
            border-radius: 6px;
            flex: 0 0 28px;
        }
        .assistant-icon-btn.is-open { background: var(--bg-input); color: #a5b4fc; }

        .assistant-models {
            padding: 12px 16px 14px;
            border-bottom: 1px solid var(--border);
            background: rgba(0, 0, 0, 0.16);
        }
        .assistant-models-head {
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 7px;
        }
        .assistant-models-head span:first-child {
            font-size: 0.72em;
            font-weight: 650;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .assistant-models-note {
            margin-left: auto;
            font-size: 0.7em;
            color: var(--text-muted);
        }
        .assistant-models select {
            width: 100%;
            background: var(--bg-input);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 10px;
            font-family: inherit;
            font-size: 0.85em;
            cursor: pointer;
        }
        .assistant-models select:focus {
            outline: none;
            border-color: rgba(102, 126, 234, 0.7);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.14);
        }
        .assistant-models-hint {
            font-size: 0.74em;
            color: var(--text-muted);
            margin-top: 6px;
            min-height: 14px;
        }

        .assistant-log { flex: 1; overflow-y: auto; padding: 16px; }
        .assistant-msg { display: flex; gap: 9px; margin-bottom: 15px; }
        .assistant-av {
            width: 24px; height: 24px; flex: 0 0 24px; border-radius: 6px;
            display: grid; place-items: center; font-size: .62em; font-weight: 700;
        }
        .assistant-msg.me .assistant-av { background: var(--bg-input); color: var(--text-secondary); }
        .assistant-msg.ai .assistant-av { background: linear-gradient(135deg,#667eea,#8b5cf6); color: #fff; }
        .assistant-body { flex: 1; min-width: 0; }
        .assistant-who {
            font-size: .66em; font-weight: 660; letter-spacing: .05em;
            text-transform: uppercase; color: var(--text-muted); margin-bottom: 3px;
        }
        .assistant-text { font-size: .9em; line-height: 1.5; word-wrap: break-word; }
        .assistant-text div { margin-bottom: 4px; }
        .assistant-text ul { margin: 5px 0 8px 17px; padding: 0; }
        .assistant-text li { margin-bottom: 3px; }
        .assistant-text code {
            background: rgba(255,255,255,.07); padding: 1px 4px; border-radius: 3px;
            font-size: .92em;
        }

        .assistant-trace {
            margin-top: 7px; border: 1px solid var(--border);
            border-radius: 6px; background: rgba(0,0,0,.22);
        }
        .assistant-trace summary {
            padding: 5px 9px; cursor: pointer; font-size: .76em; color: var(--text-muted);
        }
        .assistant-trace pre {
            margin: 0; padding: 9px; border-top: 1px solid var(--border);
            font-size: .72em; color: var(--text-muted); overflow-x: auto;
        }

        .assistant-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
        .assistant-chip {
            padding: 5px 10px; border-radius: 13px; cursor: pointer;
            background: var(--bg-input); border: 1px solid var(--border);
            font-size: .76em; color: var(--text-secondary);
        }
        .assistant-chip:hover { border-color: var(--accent); color: var(--text-primary); }

        .assistant-compose {
            border-top: 1px solid var(--border);
            padding: 12px 14px;
            display: flex; gap: 8px; align-items: flex-end;
        }
        .assistant-compose textarea {
            flex: 1; resize: none; min-height: 36px; max-height: 150px;
            background: var(--bg-input); color: var(--text-primary);
            border: 1px solid var(--border); border-radius: 6px;
            padding: 8px 10px; font-family: inherit; font-size: .88em;
        }
        .assistant-compose textarea:focus { outline: none; border-color: var(--accent); }
        .assistant-note {
            padding: 0 14px 10px; font-size: .7em; color: var(--text-muted);
            display: flex; align-items: center; gap: 5px;
        }
        .assistant-note svg { width: 11px; height: 11px; flex: 0 0 11px; }

        /* Buttons used by the secret-scanning filters and the assistant.
           Matches .search-btn's gradient and lift so the app reads as one
           surface, at a size suited to inline controls. */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 7px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-family: inherit;
            font-size: 0.88em;
            font-weight: 600;
            color: #fff;
            cursor: pointer;
            white-space: nowrap;
            transition: transform 0.16s ease, box-shadow 0.16s ease, opacity 0.16s;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.28);
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(102, 126, 234, 0.42);
        }
        .btn:active:not(:disabled) { transform: translateY(0); }
        .btn:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn svg { width: 15px; height: 15px; }

        /* btn-primary is an alias so markup can be explicit about intent. */
        .btn-primary { }

        .btn-stop {
            background: var(--bg-input);
            color: #fca5a5;
            border: 1px solid rgba(248, 113, 113, 0.45);
            box-shadow: none;
        }
        .btn-stop:hover:not(:disabled) {
            background: rgba(248, 113, 113, 0.12);
            border-color: rgba(248, 113, 113, 0.7);
        }
        .btn-ghost {
            background: var(--bg-input);
            color: var(--text-secondary);
            border: 1px solid var(--border);
            box-shadow: none;
        }
        .btn-ghost:hover:not(:disabled) {
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-primary);
            box-shadow: none;
        }

        .btn-sm { padding: 7px 13px; font-size: 0.8em; border-radius: 8px; }

        /* ---------------------------------------------------------------
           Data Collection. Laid out as grouped rows rather than free-floating
           cards: an operator scans a list of pipelines, checks freshness, and
           acts on one — the same shape an observability console uses.
           --------------------------------------------------------------- */
        .collect-group { margin-bottom: 26px; }
        .collect-group-head {
            display: flex;
            align-items: baseline;
            gap: 9px;
            margin-bottom: 9px;
        }
        .collect-group-title {
            font-size: 0.74em;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .collect-group-rule {
            flex: 1;
            height: 1px;
            background: var(--border);
        }

        .collect-row {
            display: grid;
            /* status rail | name+description | freshness | actions
               Fixed outer columns keep the status dots and action buttons on the
               same vertical line across every row, regardless of text length. */
            grid-template-columns: 132px minmax(0, 1fr) 150px auto;
            gap: 20px;
            align-items: start;
            padding: 15px 18px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            margin-bottom: 8px;
            transition: border-color 0.16s, background 0.16s;
        }
        .collect-row:hover { border-color: rgba(102, 126, 234, 0.35); }
        .collect-row.is-running { border-color: rgba(102, 126, 234, 0.5); }
        .collect-row.is-stale { box-shadow: inset 3px 0 0 #f59e0b; }
        .collect-row.is-failed { box-shadow: inset 3px 0 0 #ef4444; }
        .collect-row.is-unconfigured { opacity: 0.6; }

        .collect-name { font-weight: 600; font-size: 0.95em; margin-bottom: 3px; }
        .collect-desc {
            font-size: 0.79em;
            color: var(--text-muted);
            line-height: 1.45;
        }
        .collect-feeds {
            font-size: 0.75em;
            color: var(--text-muted);
            margin-top: 4px;
        }
        .collect-feeds span { color: var(--text-secondary); }

        /* Status rail — first column, so health is the first thing scanned. */
        .collect-state {
            display: flex; align-items: center; gap: 7px;
            font-size: 0.84em; font-weight: 500;
            white-space: nowrap;
        }
        .collect-dot { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px; }
        .collect-dot.ok      { background: #22c55e; }
        .collect-dot.stale   { background: #f59e0b; }
        .collect-dot.failed  { background: #ef4444; }
        .collect-dot.idle    { background: #64748b; }
        .collect-dot.running { background: #667eea; animation: collect-pulse 1.4s ease-in-out infinite; }
        @keyframes collect-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(102,126,234,.6); }
            50%      { box-shadow: 0 0 0 5px rgba(102,126,234,0); }
        }
        .collect-substate {
            font-size: 0.75em; color: var(--text-muted);
            margin-top: 4px; padding-left: 14px;
            font-variant-numeric: tabular-nums;
        }

        /* Freshness */
        /* The job name links to its definition in Workflows. Styled as a heading
           first so the row stays scannable; the arrow appears on hover only.
           The SVG needs explicit sizing on all axes — an unconstrained inline SVG
           expands to fill its grid cell, which previously blew the row to 762px. */
        .collect-link {
            color: var(--text-primary);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .collect-link:hover { color: #a5b4fc; text-decoration: none; }
        .collect-link-icon {
            width: 12px;
            height: 12px;
            min-width: 12px;
            min-height: 12px;
            flex: 0 0 12px;
            opacity: 0;
            transition: opacity 0.14s;
        }
        .collect-link:hover .collect-link-icon { opacity: 0.75; }

        /* Guard: any icon added to a row later inherits a sane box. */
        .collect-row svg { max-width: 16px; max-height: 16px; }

        /* Anchors styled as buttons need the button box model. */
        a.btn, a.btn:hover { text-decoration: none; }
        a.btn.btn-sm { line-height: 1; }

        .collect-fresh { font-size: 0.84em; color: var(--text-secondary); white-space: nowrap; }
        .collect-fresh-sub { font-size: 0.75em; color: var(--text-muted); margin-top: 4px; }

        /* Actions */
        .collect-actions {
            display: flex; gap: 7px; align-items: center;
            justify-self: end; white-space: nowrap;
        }

        /* Progress line spanning the full row while a collection runs. */
        .collect-bar {
            grid-column: 1 / -1;
            height: 3px;
            border-radius: 2px;
            background: var(--bg-input);
            overflow: hidden;
            margin-top: 4px;
        }
        .collect-bar-fill {
            height: 100%;
            width: 34%;
            border-radius: 2px;
            background: linear-gradient(90deg, transparent, #667eea 45%, #8b5cf6 62%, transparent);
            animation: collect-sweep 1.7s ease-in-out infinite;
        }
        @keyframes collect-sweep {
            0%   { transform: translateX(-110%); }
            100% { transform: translateX(330%); }
        }

        .collect-row.just-finished { animation: collect-flash 1.8s ease-out; }
        @keyframes collect-flash {
            0%   { box-shadow: inset 0 0 0 2px rgba(34,197,94,.5); }
            100% { box-shadow: inset 0 0 0 2px rgba(34,197,94,0); }
        }

        /* Schedule drawer — same surface language as the rest of the app. */
        .collect-drawer {
            grid-column: 1 / -1;
            margin-top: 12px;
            padding-top: 14px;
            border-top: 1px solid var(--border);
        }
        .collect-drawer-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
            gap: 12px;
            align-items: end;
        }
        .collect-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
        .collect-field-label {
            font-size: 0.71em;
            font-weight: 650;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .collect-drawer select,
        .collect-drawer input[type="text"] {
            background: var(--bg-input);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 9px 11px;
            font-family: inherit;
            font-size: 0.86em;
            width: 100%;
        }
        .collect-drawer select:focus,
        .collect-drawer input[type="text"]:focus {
            outline: none;
            border-color: rgba(102, 126, 234, 0.7);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.14);
        }

        /* Toggle switch, so enabling a schedule doesn't rely on a raw checkbox. */
        .collect-switch {
            display: inline-flex; align-items: center; gap: 9px;
            cursor: pointer; font-size: 0.86em; color: var(--text-secondary);
        }
        .collect-switch input { position: absolute; opacity: 0; pointer-events: none; }
        .collect-switch-track {
            width: 36px; height: 20px; border-radius: 11px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            position: relative;
            transition: background 0.18s, border-color 0.18s;
            flex: 0 0 36px;
        }
        .collect-switch-track::after {
            content: "";
            position: absolute;
            top: 2px; left: 2px;
            width: 14px; height: 14px; border-radius: 50%;
            background: var(--text-muted);
            transition: transform 0.18s, background 0.18s;
        }
        .collect-switch input:checked + .collect-switch-track {
            background: rgba(102, 126, 234, 0.28);
            border-color: rgba(102, 126, 234, 0.6);
        }
        .collect-switch input:checked + .collect-switch-track::after {
            transform: translateX(16px);
            background: #a5b4fc;
        }

        .collect-msg { font-size: 0.82em; margin-top: 10px; min-height: 18px; }

        @media (max-width: 1100px) {
            .collect-row { grid-template-columns: minmax(0, 1fr); gap: 11px; }
            .collect-actions { justify-self: start; }
            .collect-substate { padding-left: 0; }
        }

        /* Secret-scanning filter row */
        .secrets-filter-row {
            display: flex;
            gap: 12px;
            align-items: flex-end;
            flex-wrap: wrap;
        }
        .secrets-filter-row .filter-field {
            display: flex;
            flex-direction: column;
            gap: 5px;
            flex: 1 1 180px;
            min-width: 0;
        }
        .secrets-filter-row .filter-label {
            font-size: 0.72em;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .secrets-filter-row select {
            background: var(--bg-input);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 0.9em;
            width: 100%;
            cursor: pointer;
        }
        .secrets-filter-row select:focus {
            outline: none;
            border-color: var(--accent);
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

        /* --- Settings panel --- */
        .icon-btn {
            position: relative;
            width: 32px;
            height: 32px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: 1px solid transparent;
            border-radius: 9px;
            background: transparent;
            color: var(--text-muted);
            cursor: pointer;
            transition: color .15s, background .15s, border-color .15s;
        }
        .icon-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, .06);
            border-color: rgba(255, 255, 255, .1);
        }
        .icon-btn svg { width: 17px; height: 17px; pointer-events: none; }
        .status-dot {
            position: absolute;
            top: 5px;
            right: 5px;
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #f59e0b;
            box-shadow: 0 0 0 2px var(--bg-card);
        }

        .drawer-scrim {
            position: fixed;
            inset: 0;
            background: rgba(3, 6, 15, .55);
            backdrop-filter: blur(2px);
            z-index: 900;
            animation: drawerFade .16s ease;
        }
        .drawer {
            position: fixed;
            top: 0;
            right: 0;
            bottom: 0;
            width: 460px;
            max-width: 92vw;
            background: var(--bg-card, #12151f);
            border-left: 1px solid rgba(255, 255, 255, .09);
            box-shadow: -18px 0 48px rgba(0, 0, 0, .45);
            z-index: 901;
            display: flex;
            flex-direction: column;
            animation: drawerIn .2s cubic-bezier(.22, .61, .36, 1);
        }
        @keyframes drawerIn { from { transform: translateX(24px); opacity: .6; } }
        @keyframes drawerFade { from { opacity: 0; } }
        .drawer-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            padding: 20px 22px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, .07);
        }
        .drawer-title { font-size: 1.05em; font-weight: 650; letter-spacing: -.01em; }
        .drawer-sub { font-size: .82em; color: var(--text-muted); margin-top: 2px; }
        .drawer-body { padding: 18px 22px 26px; overflow-y: auto; }

        /* Problems, stated plainly. Healthy items are not listed: eight rows
           reading "Healthy" is noise, not information. */
        .all-clear {
            display: flex;
            align-items: center;
            gap: 9px;
            font-size: .88em;
            color: #86efac;
            padding: 12px 14px;
            border-radius: 10px;
            background: rgba(34, 197, 94, .09);
            margin-bottom: 4px;
        }
        .all-clear svg { width: 15px; height: 15px; flex-shrink: 0; }
        .issue {
            padding: 13px 15px;
            border-radius: 10px;
            background: rgba(245, 158, 11, .08);
            border: 1px solid rgba(245, 158, 11, .22);
            margin-bottom: 10px;
        }
        .issue-head { font-size: .9em; font-weight: 650; color: #fcd34d; }
        .issue-body { font-size: .85em; color: var(--text-secondary); margin-top: 4px; line-height: 1.5; }
        .issue-fix { font-size: .83em; color: var(--text-muted); margin-top: 7px; line-height: 1.5; }

        .field { margin-bottom: 20px; }
        .field-label {
            display: block;
            font-size: .88em;
            font-weight: 600;
            margin-bottom: 7px;
        }
        .field-help {
            display: block;
            font-size: .8em;
            color: var(--text-muted);
            margin-top: 6px;
            line-height: 1.5;
        }
        .field-input {
            width: 100%;
            box-sizing: border-box;
            background: rgba(255, 255, 255, .04);
            border: 1px solid rgba(255, 255, 255, .12);
            border-radius: 9px;
            padding: 9px 12px;
            color: var(--text-primary);
            font-size: .9em;
            transition: border-color .15s, background .15s;
        }
        .field-input:hover { background: rgba(255, 255, 255, .06); }
        .field-input:focus {
            outline: none;
            border-color: var(--accent);
            background: rgba(255, 255, 255, .06);
        }
        .switch-row {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            cursor: pointer;
        }
        .switch-row input { margin-top: 3px; flex-shrink: 0; }

        .drawer-savebar {
            position: sticky;
            bottom: 0;
            display: flex;
            align-items: center;
            gap: 9px;
            margin: 8px -22px -26px;
            padding: 14px 22px;
            background: var(--bg-card);
            border-top: 1px solid rgba(255, 255, 255, .1);
        }
        .savebar-text {
            flex: 1;
            font-size: .82em;
            color: var(--text-muted);
        }
        .savebar-text.is-error { color: #fca5a5; }

        /* --- Secret-scanning alerts --- */
        .alert-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 18px;
        }
        .alert-toolbar-note {
            font-size: 0.85em;
            color: var(--text-muted);
        }
        .alert-list { display: flex; flex-direction: column; gap: 12px; }
        .alert-card {
            display: grid;
            grid-template-columns: 4px minmax(0, 1fr) auto;
            align-items: center;
            gap: 0 18px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            overflow: hidden;
            transition: border-color 0.15s, background 0.15s;
        }
        .alert-card:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.14);
        }
        /* Severity rail, so the list scans by urgency without relying on colour
           alone for meaning -- the state pill carries the text. */
        .alert-rail { align-self: stretch; background: var(--text-muted); }
        .alert-rail.critical { background: #ef4444; }
        .alert-rail.high { background: #f59e0b; }
        .alert-rail.medium { background: #3b82f6; }
        .alert-card.is-paused { opacity: 0.62; }
        .alert-body { padding: 15px 0; min-width: 0; }
        .alert-name {
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 9px;
            flex-wrap: wrap;
        }
        .alert-meta {
            margin-top: 5px;
            font-size: 0.84em;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        .alert-meta .sep { opacity: 0.4; }
        .alert-actions {
            display: flex;
            align-items: center;
            gap: 8px;
            padding-right: 16px;
            flex-shrink: 0;
        }
        .alert-pill {
            font-size: 0.7em;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            padding: 3px 9px;
            border-radius: 20px;
            white-space: nowrap;
        }
        .alert-pill.triggered { background: rgba(239,68,68,.16); color: #fca5a5; }
        .alert-pill.ok { background: rgba(34,197,94,.14); color: #86efac; }
        .alert-pill.unknown { background: rgba(148,163,184,.14); color: #cbd5e1; }
        .alert-pill.error { background: rgba(245,158,11,.16); color: #fcd34d; }
        .alert-pill.paused { background: rgba(148,163,184,.14); color: #94a3b8; }

        /* Editor */
        .alert-form {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 20px 22px;
            margin-bottom: 18px;
        }
        .alert-form-title { font-weight: 600; font-size: 1.05em; margin-bottom: 4px; }
        .alert-form-sub {
            font-size: 0.85em;
            color: var(--text-muted);
            margin-bottom: 18px;
        }
        .alert-type-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 10px;
            margin-bottom: 20px;
        }
        .alert-type {
            text-align: left;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.09);
            border-radius: 10px;
            padding: 13px 14px;
            cursor: pointer;
            transition: border-color 0.15s, background 0.15s;
            color: inherit;
            font: inherit;
        }
        .alert-type:hover { background: rgba(255, 255, 255, 0.05); }
        .alert-type.selected {
            border-color: var(--accent);
            background: rgba(99, 102, 241, 0.1);
        }
        .alert-type-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 5px;
        }
        .alert-type-label { font-weight: 600; font-size: 0.92em; }
        .alert-type-desc {
            font-size: 0.82em;
            color: var(--text-muted);
            line-height: 1.45;
        }
        .alert-field-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 14px 16px;
            margin-bottom: 16px;
        }
        .alert-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
        .alert-field.wide { grid-column: 1 / -1; }
        .alert-field label {
            font-size: 0.75em;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--text-muted);
        }
        .alert-field input,
        .alert-field select {
            background: var(--bg-input);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 9px 11px;
            color: var(--text-primary);
            font-size: 0.92em;
            width: 100%;
            box-sizing: border-box;
        }
        .alert-field input:focus,
        .alert-field select:focus {
            outline: none;
            border-color: var(--accent);
        }
        .alert-field-hint { font-size: 0.78em; color: var(--text-muted); }
        .alert-check {
            display: flex;
            align-items: center;
            gap: 9px;
            font-size: 0.88em;
            color: var(--text-secondary);
        }
        .alert-check input { width: auto; }
        .alert-form-actions {
            display: flex;
            align-items: center;
            gap: 10px;
            padding-top: 16px;
            margin-top: 4px;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
        }
        .alert-form-error {
            color: #fca5a5;
            font-size: 0.86em;
            margin-right: auto;
        }
        .alert-sql {
            margin-top: 14px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.8em;
            color: var(--text-muted);
            background: rgba(0, 0, 0, 0.25);
            border-radius: 8px;
            padding: 12px 14px;
            white-space: pre-wrap;
            max-height: 190px;
            overflow: auto;
        }
        .alert-empty {
            text-align: center;
            padding: 40px 24px;
            border: 1px dashed rgba(255, 255, 255, 0.12);
            border-radius: 14px;
        }
        .alert-empty-title { font-weight: 600; margin-bottom: 5px; }
        .alert-empty-sub {
            font-size: 0.88em;
            color: var(--text-muted);
            max-width: 460px;
            margin: 0 auto 16px;
            line-height: 1.5;
        }
        /* Secret-scanning summary. Six figures sat in a bare grid with no
           separation, so the numbers read as one run of digits; each now gets a
           bounded cell, and the grid wraps instead of crushing columns. */
        .secret-summary { padding: 18px 20px; margin-bottom: 16px; }
        .secret-section-title {
            font-weight: 600;
            font-size: 0.95em;
            margin-bottom: 14px;
        }
        .secret-stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        .secret-stat {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 10px;
            padding: 14px 10px;
            text-align: center;
        }
        .secret-stat-value {
            font-size: 1.7em;
            font-weight: 700;
            line-height: 1.15;
            font-variant-numeric: tabular-nums;
        }
        .secret-stat-label {
            margin-top: 4px;
            font-size: 0.72em;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--text-muted);
            line-height: 1.3;
        }
        .secret-summary-foot {
            margin-top: 14px;
            padding-top: 12px;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
            font-size: 0.82em;
            color: var(--text-muted);
        }
        /* Card headers used above the secret tables. */
        .secret-card { padding: 16px 18px; }
        .secret-card-sub {
            font-size: 0.85em;
            color: var(--text-muted);
            margin-top: 3px;
            margin-bottom: 14px;
        }
        /* Table cards let the table meet the card edge, so the head rule spans
           the full width instead of stopping short of it. */
        .secret-table-card { padding: 16px 0 4px; }
        .secret-table-card > .secret-section-title,
        .secret-table-card > .secret-card-sub { padding: 0 18px; }
        .secret-table-card .data-table th:first-child,
        .secret-table-card .data-table td:first-child { padding-left: 18px; }
        .secret-table-card .data-table th:last-child,
        .secret-table-card .data-table td:last-child { padding-right: 18px; }

        /* Tabular data in the secret-scanning views. These tables previously
           carried a class with no rule behind it, so they fell back to browser
           defaults: no cell padding, collapsed columns, and text from adjacent
           cells running together. */
        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }
        .data-table th {
            text-align: left;
            padding: 10px 14px;
            font-size: 0.78em;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--text-muted);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            white-space: nowrap;
        }
        .data-table td {
            padding: 11px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            color: var(--text-secondary);
            vertical-align: middle;
        }
        .data-table tbody tr:last-child td { border-bottom: none; }
        .data-table tbody tr:hover { background: rgba(255, 255, 255, 0.035); }
        /* Numeric columns are right-aligned by the markup; keep them from
           touching the next column's value. */
        .data-table th[style*="right"], .data-table td[style*="right"] {
            padding-right: 18px;
        }
        .data-table .nowrap-muted {
            white-space: nowrap;
            font-size: 0.88em;
            color: var(--text-muted);
        }
        /* A table flush inside .results-container needs its own edge padding. */
        .data-table-padded th:first-child,
        .data-table-padded td:first-child { padding-left: 24px; }
        .data-table-padded th:last-child,
        .data-table-padded td:last-child { padding-right: 24px; }
        .data-table .mono {
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.88em;
            color: var(--text-muted);
        }
        /* Long paths and hashes truncate rather than forcing the table wide. */
        .data-table .truncate {
            max-width: 320px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
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
                        <span class="logo-text">Security Analysis Tool</span>
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
                        <div class="nav-label">⚙️ Operations</div>
                        <div class="nav-item" data-page="collection">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                            Data Collection
                        </div>
                    </div>

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
                        <div class="nav-item" data-page="denylistbuilder">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                            Denylist Builder
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
                        <div class="nav-item" data-page="sharedtoaccount">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                            Shared to All Users
                        </div>
                        <div class="nav-item" data-page="privilegednonidp">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
                            Privileged Non-IdP
                        </div>
                    </div>

                    <div class="nav-section">
                        <div class="nav-label">🔑 Secret Scanning</div>
                        <div class="nav-item" data-page="secretsoverview">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v5M12 17h.01"/></svg>
                            Credential Exposure
                        </div>
                        <div class="nav-item" data-page="secretsfindings">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                            Secret Findings
                        </div>
                        <div class="nav-item" data-page="secretsalerts">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                            Alerts
                        </div>
                    </div>

                    <div class="nav-section">
                        <div class="nav-label">🧩 Code Security</div>
                        <div class="nav-item" data-page="codeoverview">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                            Code Overview
                        </div>
                        <div class="nav-item" data-page="codefindings">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2 2 7l10 5 10-5-10-5z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>
                            Code Findings
                        </div>
                    </div>
                </div>

            </nav>

            <div class="sidebar-footer">
                <a class="sidebar-footer-link" href="https://www.databricks.com/trust"
                       target="_blank" rel="noopener noreferrer">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                        Trust Center
                    </a>
                    <button class="icon-btn" id="settings-gear" title="Settings"
                            aria-label="Settings" onclick="openSettingsPanel()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                        <span class="status-dot" id="settings-dot" hidden></span>
                    </button>
                </div>
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

                            // Match navigateToPage's rule here too, otherwise deep
                            // links to these pages briefly flash the graph-collection
                            // bar before the main script hides it.
                            const noStatsBar = ['home', 'sharedtoaccount', 'privilegednonidp',
                                                'denylistbuilder', 'collection',
                                                'secretsoverview', 'secretsfindings',
                                                'secretsalerts', 'codeoverview',
                                                'codefindings'];
                            const bar = document.getElementById('stats-header-bar');
                            if (bar && noStatsBar.includes(hash)) bar.style.display = 'none';
                        });
                    }
                })();
            </script>
            
            <!-- Stats Header Bar -->
            <div class="stats-header-bar" id="stats-header-bar">
                <div class="stats-header-toggle">
                    <span class="stats-header-toggle-text">Graph Collection — Inventory &amp; Coverage</span>
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
            <!-- Data Collection: run and schedule the jobs that populate this app. -->
            <div class="page" id="page-collection">
                <div class="page-header">
                    <h1 class="page-title">Data Collection</h1>
                    <p class="page-desc">Collection health, on-demand runs, and recurring schedules for every analysis job.</p>
                </div>
                <div id="collection-panel"></div>
            </div>

            <div class="page active" id="page-home">
                <div class="page-header" style="text-align: center; margin-bottom: 18px;">
                    <h1 class="page-title" style="margin-bottom: 6px; font-size: 1.8em;">🛡️ Security Analysis Tool</h1>
                </div>

                <div class="card" style="padding: 20px;">
                    <h2 style="font-size: 1.2em; margin-bottom: 10px; color: var(--primary);">What is the Security Analysis Tool?</h2>
                    <p style="line-height: 1.45; color: var(--text-secondary); margin-bottom: 13px; font-size: 0.92em;">
                        The Security Analysis Tool is a security observability platform for Databricks environments.
                        It maps the permissions graph to surface privilege escalation paths, over-privileged principals,
                        and complex access relationships across workspaces; scans notebooks and cluster configurations
                        for hardcoded credentials; and answers questions about any of it in plain language.
                    </p>
                    
                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">🎯 Key Features</h3>
                    <ul style="line-height: 1.5; color: var(--text-secondary); list-style-position: inside; margin-bottom: 13px; font-size: 0.88em;">
                        <li><strong>Principal Analysis</strong> - Discover what a user, group, or service principal can access</li>
                        <li><strong>Resource Analysis</strong> - Find all principals with access to specific resources</li>
                        <li><strong>Escalation Paths</strong> - Identify potential privilege escalation routes</li>
                        <li><strong>Impersonation Analysis</strong> - See who can impersonate whom</li>
                        <li><strong>Security Reports</strong> - Pre-built reports for common security concerns</li>
                    </ul>

                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">🪪 Account &amp; Identity Governance <span style="font-size: 0.7em; font-weight: 600; color: #10b981; text-transform: uppercase; letter-spacing: 0.5px; vertical-align: middle;">New</span></h3>
                    <p style="line-height: 1.45; color: var(--text-secondary); margin-bottom: 9px; font-size: 0.88em;">
                        Account-level detections that complement Automatic Identity Management (AIM). These run their own account-wide detection jobs and are surfaced with their own point-in-time coverage:
                    </p>
                    <ul style="line-height: 1.5; color: var(--text-secondary); list-style-position: inside; margin-bottom: 13px; font-size: 0.88em;">
                        <li><strong>Shared to All Users</strong> - Find resources shared with the built-in <em>account users</em> group (i.e. exposed to everyone in the account) and optionally remediate them</li>
                        <li><strong>Privileged Non-IdP</strong> - Surface Account Admin / Workspace Admin held by identities that aren't IdP-managed (no <code>externalId</code>), or assigned directly to users and service principals — access that bypasses your identity provider's joiner/mover/leaver governance</li>
                        <li><strong>Denylist Builder</strong> - Rank IdP groups by inactive members to find safe <a href="https://learn.microsoft.com/en-gb/azure/databricks/admin/users-groups/automatic-identity-management/account-access-denylist" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">account access denylist</a> candidates, plus an Entra ID dynamic-group rule helper to scale a single denylist entry to thousands of users</li>
                    </ul>

                    <h3 style="font-size: 1em; margin: 15px 0 9px 0; color: var(--primary);">🚀 Getting Started</h3>
                    
                    <!-- Graph Collection status instructions -->
                    <div style="padding: 13px; background: linear-gradient(135deg, rgba(16, 185, 129, 0.05) 0%, rgba(16, 185, 129, 0.02) 100%); border: 2px solid rgba(16, 185, 129, 0.2); border-radius: 10px; margin-bottom: 13px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                        <div style="display: flex; align-items: center; gap: 9px; margin-bottom: 7px;">
                            <div style="width: 30px; height: 30px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 15px;">
                                📈
                            </div>
                            <div style="font-size: 0.9em; font-weight: 700; color: var(--text-primary);">Graph Collection — Inventory &amp; Coverage</div>
                        </div>
                        <p style="color: var(--text-secondary); font-size: 0.82em; line-height: 1.35; margin: 0 0 0 39px;">
                            When you open an <strong>Analysis Tool</strong> or graph <strong>Security Report</strong>, a header bar shows the graph collection's inventory and workspace coverage. Use its <strong>Data Collection</strong> dropdown to switch between collection runs and view historical data. Account &amp; Identity Governance pages run their own account-wide jobs and show their own coverage instead.
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
                    <p class="page-desc">Everything a user, group, or service principal can reach, directly or through group membership.</p>
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
                    <p class="page-desc">Every principal that can reach a given resource, and the grant that allows it.</p>
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
                    <p class="page-desc">Routes by which a principal could obtain admin or otherwise privileged access.</p>
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
                    <p class="page-desc">Principals that can act as another identity, and the permissions that make it possible.</p>
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
                    <p class="page-desc">Identities with almost no group membership or grants. Often leftover or misconfigured accounts.</p>
                </div>
                <div id="isolated-results"></div>
            </div>

            <!-- Orphaned Resources Report Page -->
            <div class="page" id="page-orphaned">
                <div class="page-header">
                    <h1 class="page-title">Orphaned Resources</h1>
                    <p class="page-desc">Resources with no explicit grants. Access falls back to inherited or default permissions.</p>
                </div>
                <div id="orphaned-results"></div>
            </div>

            <!-- Over-Privileged Principals Report Page -->
            <div class="page" id="page-overprivileged">
                <div class="page-header">
                    <h1 class="page-title">Over-Privileged Principals</h1>
                    <p class="page-desc">Identities holding more access than their activity suggests they need.</p>
                </div>
                <div id="overprivileged-results"></div>
            </div>

            <!-- High Privilege Principals Report Page -->
            <div class="page" id="page-highprivilege">
                <div class="page-header">
                    <h1 class="page-title">High Privilege Principals</h1>
                    <p class="page-desc">Identities with administrative rights, whether granted directly or inherited through groups.</p>
                </div>
                <div id="highprivilege-results"></div>
            </div>

            <!-- Secret Scope Access Report Page -->
            <div class="page" id="page-secretscopes">
                <div class="page-header">
                    <h1 class="page-title">Secret Scope Access</h1>
                    <p class="page-desc">Who can read, write, or manage each secret scope.</p>
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

            <!-- Shared to All Account Users Report Page -->
            <div class="page" id="page-sharedtoaccount">
                <div class="page-header">
                    <h1 class="page-title">Shared to All Account Users</h1>
                    <p class="page-desc">Dashboards, Genie spaces, and apps shared with the built-in account users group, and therefore readable by everyone in the account.</p>
                </div>
                <div id="sharedtoaccount-results"></div>
            </div>

            <!-- Privileged Non-IdP Group Identities Report Page -->
            <div class="page" id="page-privilegednonidp">
                <div class="page-header">
                    <h1 class="page-title">Privileged Non-IdP Group Identities</h1>
                    <p class="page-desc">Administrative rights held outside your identity provider. These accounts survive offboarding, because removing someone from the IdP does not revoke them.</p>
                </div>
                <div id="privilegednonidp-results"></div>
            </div>

            <!-- Account Denylist Builder Page -->
            <div class="page" id="page-denylistbuilder">
                <div class="page-header">
                    <h1 class="page-title">Account Denylist Builder</h1>
                    <p class="page-desc">Tools to help build an <a href="https://learn.microsoft.com/en-gb/azure/databricks/admin/users-groups/automatic-identity-management/account-access-denylist" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">account access denylist</a>: find IdP groups whose members aren't using Databricks, and generate Entra ID dynamic-group rules that scale a single denylist entry to thousands of users.</p>
                </div>

                <!-- Section 1: Inactive-user group candidates -->
                <div style="margin-bottom: 28px;">
                    <h2 style="font-size: 1.1em; margin-bottom: 4px;">1. Inactive-User Group Candidates</h2>
                    <p style="color: var(--text-muted); font-size: 0.85em; margin-bottom: 12px;">
                        IdP-managed (external) groups ranked by count of inactive members (users with no
                        <code>system.access.audit</code> activity in the look-back window — a heuristic for the
                        <a href="https://learn.microsoft.com/en-gb/azure/databricks/admin/users-groups/automatic-identity-management/#status" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">"Inactive: No usage"</a> status). Groups whose members mostly aren't logging in are good denylist candidates.
                        <br><span style="color: #f59e0b;">Note:</span> under Automatic Identity Management, IdP group memberships are resolved just-in-time and aren't returned by the account SCIM API, so this ranking can be empty even for populated groups. Where that's the case, use the Entra rule builder below.
                    </p>
                    <div id="denylist-candidates-results"></div>
                </div>

                <!-- Section 2: Entra ID dynamic group rule helper -->
                <div>
                    <h2 style="font-size: 1.1em; margin-bottom: 4px;">2. Entra ID Dynamic Group Rule Builder</h2>
                    <p style="color: var(--text-muted); font-size: 0.85em; margin-bottom: 12px;">
                        Denylists support up to 100 groups, but a single
                        <a href="https://learn.microsoft.com/en-us/entra/identity/users/groups-dynamic-membership" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">Entra ID dynamic group</a>
                        can contain thousands of users via a membership rule. Build a rule below, then create the
                        group in Entra and add it to your denylist. See also
                        <a href="https://learn.microsoft.com/en-us/entra/identity/users/groups-dynamic-rule-more-efficient" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">writing efficient rules</a>.
                    </p>
                    <div id="entra-rule-builder"></div>
                </div>
            </div>

            <!-- Credential Exposure (secret scanning overview) -->
            <div class="page" id="page-secretsoverview">
                <div class="page-header">
                    <h1 class="page-title">Credential Exposure</h1>
                    <p class="page-desc">Hardcoded credentials found in notebook source and cluster environment variables by the SAT secret scanner. Secrets are stored as SHA-256 hashes, never plaintext. <strong>Active</strong> means the credential was validated against the live service and is confirmed working.</p>
                </div>
                <div id="secretsoverview-results"></div>
            </div>

            <!-- Secret Findings (detail table) -->
            <!-- Code Security Overview Page -->
            <div class="page" id="page-codeoverview">
                <div class="page-header">
                    <h1 class="page-title">Code Overview</h1>
                    <p class="page-desc">Insecure patterns found in notebook and file source, and known vulnerabilities in the packages that code declares. Two independent scanners: one reads your code, the other checks your dependencies against published CVEs.</p>
                </div>
                <div id="codeoverview-results"></div>
            </div>

            <!-- Code Findings Page -->
            <div class="page" id="page-codefindings">
                <div class="page-header">
                    <h1 class="page-title">Code Findings</h1>
                    <p class="page-desc">Every finding from the most recent scan. Filter by scanner, severity, or search for a path, rule, or package.</p>
                </div>
                <div class="card" style="padding:16px 18px;margin-bottom:18px;">
                    <div class="alert-field-grid">
                        <div class="alert-field">
                            <label for="cf-scanner">Scanner</label>
                            <select id="cf-scanner">
                                <option value="">All scanners</option>
                                <option value="semgrep">Code patterns</option>
                                <option value="trivy">Dependencies</option>
                            </select>
                        </div>
                        <div class="alert-field">
                            <label for="cf-severity">Severity</label>
                            <select id="cf-severity">
                                <option value="">All severities</option>
                                <option value="CRITICAL">Critical</option>
                                <option value="HIGH">High</option>
                                <option value="MEDIUM">Medium</option>
                                <option value="LOW">Low</option>
                            </select>
                        </div>
                        <div class="alert-field wide">
                            <label for="cf-search">Search</label>
                            <input id="cf-search" type="text" placeholder="Path, rule, or package name">
                        </div>
                    </div>
                    <div style="display:flex;justify-content:flex-end;">
                        <button class="btn btn-sm" onclick="runCodeFindings()">Apply</button>
                    </div>
                </div>
                <div id="codefindings-results"></div>
            </div>

            <!-- Settings / Health Page -->
            <!-- Secret Scanning Alerts Page -->
            <div class="page" id="page-secretsalerts">
                <div class="page-header">
                    <h1 class="page-title">Alerts</h1>
                    <p class="page-desc">Get notified when the scanner finds exposed credentials. These are standard Databricks SQL alerts &mdash; the schedule, notifications and history work exactly as they do elsewhere, and each one stays editable in the workspace.</p>
                </div>
                <div id="secretsalerts-results"></div>
            </div>

            <div class="page" id="page-secretsfindings">
                <div class="page-header">
                    <h1 class="page-title">Secret Findings</h1>
                    <p class="page-desc">Individual detections from the most recent scan per workspace. Filter by workspace, source, detector, or confirmed-active status.</p>
                </div>
                <div class="card" style="padding: 16px; margin-bottom: 18px;">
                    <div class="secrets-filter-row">
                        <div class="filter-field">
                            <label class="filter-label">Workspace</label>
                            <select id="sf-workspace"><option value="">All workspaces</option></select>
                        </div>
                        <div class="filter-field">
                            <label class="filter-label">Source</label>
                            <select id="sf-source">
                                <option value="">Notebooks and clusters</option>
                                <option value="notebook">Notebooks</option>
                                <option value="cluster">Cluster configs</option>
                            </select>
                        </div>
                        <div class="filter-field">
                            <label class="filter-label">Detector</label>
                            <select id="sf-detector"><option value="">All detectors</option></select>
                        </div>
                        <div class="filter-field">
                            <label class="filter-label">Status</label>
                            <select id="sf-verified">
                                <option value="false">All findings</option>
                                <option value="true">Confirmed active only</option>
                            </select>
                        </div>
                        <button class="btn btn-primary" id="sf-apply">Apply</button>
                    </div>
                </div>
                <div id="secretsfindings-results"></div>
            </div>

        </main>
    </div>

    <!-- Security assistant: floating launcher + slide-over panel, available on
         every page rather than occupying a nav slot. -->
    <div class="drawer-scrim" id="settings-scrim" hidden onclick="closeSettingsPanel()"></div>
    <aside class="drawer" id="settings-drawer" hidden aria-label="Settings and health">
        <div class="drawer-head">
            <div>
                <div class="drawer-title">Settings</div>
                <div class="drawer-sub">Dependency status and configuration</div>
            </div>
            <button class="icon-btn" onclick="closeSettingsPanel()" aria-label="Close settings">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>
        <div class="drawer-body" id="settings-body"></div>
    </aside>

    <button class="assistant-fab" id="assistant-fab" title="Ask the security assistant" aria-label="Open security assistant">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
    </button>

    <aside class="assistant-panel" id="assistant-panel" aria-label="Security assistant">
        <div class="assistant-head">
            <div class="assistant-head-mark">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
            </div>
            <div style="min-width:0;">
                <div class="assistant-head-title">Security Assistant</div>
                <div class="assistant-head-sub" id="assistant-model-label">Permissions, secrets, and audit activity</div>
            </div>
            <div class="assistant-head-actions">
            <button class="assistant-icon-btn" id="assistant-model-btn" title="Change model" aria-label="Change model">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
            </button>
            <button class="assistant-close" id="assistant-close" aria-label="Close">&times;</button>
            </div>
        </div>

        <!-- Model selector. Lists the chat endpoints available on this
             workspace's AI Gateway; the choice applies to the next message. -->
        <div class="assistant-models" id="assistant-models" style="display:none;">
            <div class="assistant-models-head">
                <span>Model</span>
                <span class="assistant-models-note">Served through the AI Gateway</span>
            </div>
            <select id="assistant-model-select"><option>Loading…</option></select>
            <div class="assistant-models-hint" id="assistant-model-hint"></div>
        </div>
        <div class="assistant-log" id="assistant-log"></div>
        <div class="assistant-compose">
            <textarea id="assistant-input" rows="1" placeholder="Ask a security question&hellip;"></textarea>
            <button class="btn btn-primary" id="assistant-send">Send</button>
            <button class="btn btn-stop" id="assistant-stop" hidden>Stop</button>
        </div>
        <div class="assistant-note">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            Read-only — the assistant can explain findings but cannot change permissions or data.
        </div>
    </aside>



    <script>
        // Current run_id state
        let currentRunId = null;

        // Track current page and loaded reports
        let currentPage = 'dashboard';
        const reportPages = ['isolated', 'orphaned', 'overprivileged', 'highprivilege', 'secretscopes', 'sharedtoaccount', 'privilegednonidp'];
        const analysisPages = ['principal', 'resource', 'paths', 'risk', 'impersonation', 'denylistbuilder'];

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

            // The global stats header describes the permissions graph collection run
            // (inventory counts and collector coverage, driven by the run selector).
            // Hide it on pages it does not describe: the intro page, the
            // account-level detection reports (own run_id and coverage block), the
            // secret scanning pages (different dataset entirely), and Data
            // Collection, which reports freshness for every job itself.
            const hideStatsBarPages = ['home', 'sharedtoaccount', 'privilegednonidp', 'denylistbuilder',
                                       'collection', 'secretsoverview', 'secretsfindings',
                                       'secretsalerts', 'codeoverview',
                                       'codefindings'];
            const statsBar = document.getElementById('stats-header-bar');
            if (statsBar) statsBar.style.display = hideStatsBarPages.includes(page) ? 'none' : '';

            // Auto-load reports when navigating to report pages
            if (page === 'isolated') loadIsolatedPrincipals();
            else if (page === 'orphaned') loadOrphanedResources();
            else if (page === 'overprivileged') loadOverPrivileged();
            else if (page === 'highprivilege') loadHighPrivilege();
            else if (page === 'secretscopes') loadSecretScopeAccess();
            else if (page === 'sharedtoaccount') loadSharedToAccount();
            else if (page === 'privilegednonidp') loadPrivilegedNonIdp();
            else if (page === 'denylistbuilder') loadDenylistBuilder();
            else if (page === 'collection') loadCollectionPanel();
            else if (page === 'secretsoverview') loadSecretsOverview();
            else if (page === 'secretsfindings') loadSecretsFindings();
            else if (page === 'secretsalerts') loadSecretsAlerts();
            else if (page === 'codeoverview') loadCodeOverview();
            else if (page === 'codefindings') loadCodeFindings();
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

        // HTML-escape any string before interpolating into an innerHTML
        // template. Defined early so every renderer below can use it.
        // Uses textContent assignment which is the canonical browser-safe
        // escape (handles <, >, &, ", ', NUL, etc. consistently).
        function escapeHtml(text) {
            if (text === null || text === undefined) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        }

        // Format principal name with identifier for uniqueness.
        // Shows "Display Name (email)" or "Display Name (name)" to
        // distinguish principals with same display name. Returns
        // HTML-escaped text safe to drop into an `${...}` interpolation
        // inside an innerHTML template.
        function formatPrincipalName(displayName, email, name, id) {
            const display = displayName || name || email || id || 'Unknown';
            const identifier = email || name || id;
            if (identifier && String(display).toLowerCase() !== String(identifier).toLowerCase()) {
                return `${escapeHtml(display)} (${escapeHtml(identifier)})`;
            }
            return escapeHtml(display);
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

        // ------------------------------------------------------------------
        // Secret scanning
        //
        // Findings come from the SAT secret scanner. "Confirmed active" means
        // TruffleHog validated the credential against the live service, so those
        // are ranked first everywhere — they are the ones that need rotating now.
        // ------------------------------------------------------------------

        // Rendered when the scanner has not populated its tables. Deliberately
        // distinct from an empty result: "no findings" and "never scanned" are
        // very different answers, and conflating them gives false assurance.
        function showSecretsNotReady(containerId, message) {
            document.getElementById(containerId).innerHTML = `
                <div class="results-container">
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                        <p style="font-weight:600;color:var(--text-primary);margin-bottom:6px;">No scan results yet</p>
                        <p>${escapeHtml(message || '')}</p>
                    </div>
                </div>`;
        }

        function secretStatBlock(label, value, color) {
            return `
                <div class="secret-stat">
                    <div class="secret-stat-value" style="color: ${color};">${value}</div>
                    <div class="secret-stat-label">${escapeHtml(label)}</div>
                </div>`;
        }

        // Horizontal distribution bar — avoids pulling in a charting library.
        function secretBar(label, value, max, color) {
            const pct = max > 0 ? (value / max) * 100 : 0;
            return `
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                    <div style="flex:0 0 190px;font-size:0.85em;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
                    <div style="flex:1;height:7px;background:var(--bg-input);border-radius:4px;overflow:hidden;">
                        <div style="height:100%;width:${pct}%;background:${color};border-radius:4px;"></div>
                    </div>
                    <div style="flex:0 0 48px;text-align:right;font-size:0.85em;font-variant-numeric:tabular-nums;">${value}</div>
                </div>`;
        }

        function secretStatusBadge(verified) {
            const active = verified === true || String(verified) === 'true';
            return active
                ? '<span class="badge" style="background:rgba(239,68,68,.15);color:#fca5a5;">ACTIVE</span>'
                : '<span class="badge" style="background:rgba(148,163,184,.15);color:#cbd5e1;">unverified</span>';
        }


        // ------------------------------------------------------------------
        // Security assistant (floating panel)
        // ------------------------------------------------------------------

        const assistantState = { session: null, busy: false, ready: null,
                                 controller: null, turnId: null };


        // Model selector — lists the gateway's chat endpoints and switches which
        // one answers the next message.
        let assistantModelsLoaded = false;

        function assistantShortModel(name) {
            // Endpoint names are long ("databricks-claude-opus-4-7"); the prefix is
            // noise once you know everything is served through the gateway.
            return String(name || '').replace(/^databricks-/, '');
        }

        async function assistantToggleModels() {
            const box = document.getElementById('assistant-models');
            const btn = document.getElementById('assistant-model-btn');
            const showing = box.style.display !== 'none';
            box.style.display = showing ? 'none' : 'block';
            btn.classList.toggle('is-open', !showing);
            if (!showing && !assistantModelsLoaded) await assistantLoadModels();
        }

        async function assistantLoadModels() {
            const select = document.getElementById('assistant-model-select');
            const hint = document.getElementById('assistant-model-hint');
            try {
                const data = await fetch('/api/assistant/models').then(r => r.json());
                if (data.error) {
                    select.innerHTML = '<option>Unavailable</option>';
                    hint.textContent = data.error;
                    return;
                }
                const models = data.models || [];
                select.innerHTML = models.map(m =>
                    `<option value="${escapeHtml(m.name)}" ${m.name === data.active ? 'selected' : ''}>${escapeHtml(assistantShortModel(m.name))}</option>`
                ).join('');
                hint.textContent = `${models.length} endpoints available`;
                assistantModelsLoaded = true;
                assistantSetModelLabel(data.active);

                select.onchange = async () => {
                    const endpoint = select.value;
                    hint.textContent = 'Switching…';
                    try {
                        const res = await fetch('/api/assistant/models', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ endpoint: endpoint }),
                        }).then(r => r.json());
                        if (res.error) { hint.textContent = res.error; return; }
                        assistantSetModelLabel(res.active);
                        hint.textContent = 'Applies to your next message.';
                    } catch (e) {
                        hint.textContent = e.message;
                    }
                };
            } catch (e) {
                select.innerHTML = '<option>Unavailable</option>';
                hint.textContent = e.message;
            }
        }

        function assistantSetModelLabel(name) {
            const label = document.getElementById('assistant-model-label');
            if (label && name) label.textContent = assistantShortModel(name);
        }

        function assistantOpen() {
            document.getElementById('assistant-panel').classList.add('open');
            document.getElementById('assistant-fab').classList.add('hidden');
            if (assistantState.ready === null) assistantInit();
            const input = document.getElementById('assistant-input');
            if (input) setTimeout(() => input.focus(), 220);
        }

        function assistantClose() {
            document.getElementById('assistant-panel').classList.remove('open');
            document.getElementById('assistant-fab').classList.remove('hidden');
        }

        async function assistantInit() {
            const log = document.getElementById('assistant-log');
            log.innerHTML = '<div class="loading"><div class="spinner"></div>Connecting&hellip;</div>';
            try {
                const cfg = await fetch('/api/assistant/config').then(r => r.json());
                assistantState.ready = !!cfg.ready;
                if (cfg.model) assistantSetModelLabel(cfg.model);
                if (!cfg.ready) {
                    log.innerHTML = `
                        <div class="empty-state" style="padding:24px 8px;">
                            <p style="font-weight:600;color:var(--text-primary);margin-bottom:6px;">Assistant unavailable</p>
                            <p style="font-size:.88em;">${escapeHtml(cfg.message || '')}</p>
                        </div>`;
                    return;
                }
                log.innerHTML = `
                    <div class="assistant-chips">
                        ${(cfg.suggestions || []).map(q =>
                            `<div class="assistant-chip" data-ask="${escapeHtml(q)}">${escapeHtml(q)}</div>`).join('')}
                    </div>
                    <div style="font-size:.85em;color:var(--text-muted);line-height:1.5;">
                        Ask about permissions, exposed credentials, or workspace activity.
                        Answers are grounded in the collected data — the assistant reads it
                        through a fixed set of tools and cannot modify anything.
                    </div>`;
                log.querySelectorAll('[data-ask]').forEach(chip => {
                    chip.addEventListener('click', () => {
                        document.getElementById('assistant-input').value = chip.dataset.ask;
                        assistantSend();
                    });
                });
            } catch (e) {
                assistantState.ready = false;
                log.innerHTML = `<div class="empty-state" style="padding:24px 8px;"><p>Could not reach the assistant: ${escapeHtml(e.message)}</p></div>`;
            }
        }

        // Minimal markdown: bold, inline code, and bullet lines. The assistant is
        // instructed to keep formatting simple, so a full parser is unnecessary.
        function assistantMarkdown(text) {
            const out = [];
            let inList = false;
            // Split on newlines using String.fromCharCode(10). A backslash escape
            // cannot be used here: this whole template is a Python f-string, so
            // Python would consume the escape and emit a literal line break,
            // which is a JavaScript syntax error.
            escapeHtml(text).split(String.fromCharCode(10)).forEach(raw => {
                const line = raw
                    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                    .replace(/`([^`]+)`/g, '<code>$1</code>');
                const bullet = line.match(/^\s*[-*]\s+(.*)$/);
                if (bullet) {
                    if (!inList) { out.push('<ul>'); inList = true; }
                    out.push(`<li>${bullet[1]}</li>`);
                } else {
                    if (inList) { out.push('</ul>'); inList = false; }
                    out.push(line.trim() ? `<div>${line}</div>` : '<div style="height:6px"></div>');
                }
            });
            if (inList) out.push('</ul>');
            return out.join('');
        }

        function assistantAppend(role, html) {
            const log = document.getElementById('assistant-log');
            // Clear the intro block on the first real exchange.
            const chips = log.querySelector('.assistant-chips');
            if (chips) log.innerHTML = '';
            const wrap = document.createElement('div');
            wrap.className = 'assistant-msg ' + (role === 'user' ? 'me' : 'ai');
            wrap.innerHTML = `
                <div class="assistant-av">${role === 'user' ? 'You' : 'AI'}</div>
                <div class="assistant-body">
                    <div class="assistant-who">${role === 'user' ? 'You' : 'Assistant'}</div>
                    <div class="assistant-text">${html}</div>
                </div>`;
            log.appendChild(wrap);
            log.scrollTop = log.scrollHeight;
            return wrap;
        }

        // Abort the in-flight turn. The fetch is cancelled locally and the server is
        // told to stop, so a long tool loop stops spending tokens rather than
        // running on invisibly after the user gave up on it.
        function assistantStop() {
            if (!assistantState.busy) return;
            const turn = assistantState.turnId;
            if (assistantState.controller) assistantState.controller.abort();
            if (turn) {
                fetch('/api/assistant/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ turn_id: turn }),
                }).catch(() => {});
            }
        }

        async function assistantSend() {
            if (assistantState.busy) return;
            const input = document.getElementById('assistant-input');
            const question = input.value.trim();
            if (!question) return;

            input.value = '';
            assistantState.busy = true;
            assistantState.controller = new AbortController();
            assistantState.turnId = 'turn-' + Date.now() + '-' +
                Math.random().toString(36).slice(2, 8);
            const sendBtn = document.getElementById('assistant-send');
            const stopBtn = document.getElementById('assistant-stop');
            sendBtn.disabled = true;
            sendBtn.hidden = true;
            stopBtn.hidden = false;
            assistantAppend('user', assistantMarkdown(question));
            const pending = assistantAppend('ai', '<div class="loading" style="padding:0;"><div class="spinner"></div>Investigating&hellip;</div>');

            try {
                const res = await fetch('/api/assistant/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: assistantState.controller.signal,
                    body: JSON.stringify({
                        message: question,
                        session_id: assistantState.session,
                        turn_id: assistantState.turnId,
                    }),
                });
                const result = await res.json();
                if (result.error) {
                    pending.querySelector('.assistant-text').innerHTML =
                        `<span style="color:#fca5a5;">${escapeHtml(result.error)}</span>`;
                } else {
                    assistantState.session = result.session_id;
                    let html = assistantMarkdown(result.answer || '(no answer)');
                    const calls = result.tool_calls || [];
                    if (calls.length) {
                        // String.fromCharCode(10) rather than a backslash escape: the
                        // enclosing Python f-string would consume '\\n' and emit a raw
                        // line break, which is a JavaScript syntax error.
                        const lines = calls.map(t =>
                            `${t.name || t.tool_name}(${JSON.stringify(t.args || t.tool_args || {})})`).join(String.fromCharCode(10));
                        html += `<details class="assistant-trace"><summary>${calls.length} data lookup${calls.length === 1 ? '' : 's'}</summary><pre>${escapeHtml(lines)}</pre></details>`;
                    }
                    pending.querySelector('.assistant-text').innerHTML = html;
                }
            } catch (e) {
                const stopped = e.name === 'AbortError';
                pending.querySelector('.assistant-text').innerHTML = stopped
                    ? '<span style="color:#94a3b8;">Stopped.</span>'
                    : `<span style="color:#fca5a5;">${escapeHtml(e.message)}</span>`;
            } finally {
                assistantState.busy = false;
                assistantState.controller = null;
                assistantState.turnId = null;
                const sendBtn = document.getElementById('assistant-send');
                const stopBtn = document.getElementById('assistant-stop');
                sendBtn.disabled = false;
                sendBtn.hidden = false;
                stopBtn.hidden = true;
                const log = document.getElementById('assistant-log');
                log.scrollTop = log.scrollHeight;
            }
        }

        // Wire the assistant once the DOM exists.
        (function wireAssistant() {
            function attach() {
                const fab = document.getElementById('assistant-fab');
                if (!fab) return;
                fab.addEventListener('click', assistantOpen);
                document.getElementById('assistant-model-btn')
                        .addEventListener('click', assistantToggleModels);
                document.getElementById('assistant-close').addEventListener('click', assistantClose);
                document.getElementById('assistant-send').addEventListener('click', assistantSend);
                document.getElementById('assistant-stop').addEventListener('click', assistantStop);
                const input = document.getElementById('assistant-input');
                input.addEventListener('keydown', ev => {
                    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); assistantSend(); }
                    // Escape stops a running turn, matching the Stop button.
                    if (ev.key === 'Escape' && assistantState.busy) { ev.preventDefault(); assistantStop(); }
                });
                document.addEventListener('keydown', ev => {
                    if (ev.key === 'Escape') assistantClose();
                });
            }
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', attach);
            } else {
                attach();
            }
        })();


        // ------------------------------------------------------------------
        // Data collection control
        //
        // Starts the SAT collection jobs and follows the run to completion, so a
        // refresh never requires leaving the app. Only the two jobs bound in the
        // app's configuration can be started.
        // ------------------------------------------------------------------

        let collectionPollTimers = {};
        let collectionElapsedTimer = null;
        const collectionRunStart = {};

        // A collection older than this is flagged stale — the data on screen may no
        // longer reflect the workspace.
        const COLLECT_STALE_HOURS = 36;

        function formatElapsed(ms) {
            if (!ms || ms < 0) return '0s';
            const total = Math.floor(ms / 1000);
            const h = Math.floor(total / 3600);
            const m = Math.floor((total % 3600) / 60);
            const sec = total % 60;
            if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
            if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`;
            return `${sec}s`;
        }

        function formatAgo(ms) {
            if (!ms) return null;
            const diff = Date.now() - Number(ms);
            if (diff < 60000) return 'just now';
            if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
            if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
            return `${Math.floor(diff / 86400000)}d ago`;
        }

        function collectionStageText(run) {
            const state = String(run.state || '').toUpperCase();
            if (state === 'PENDING' || state === 'QUEUED' || state === 'BLOCKED') {
                return 'Waiting for compute';
            }
            const total = Number(run.tasks_total) || 0;
            const done = Number(run.tasks_done) || 0;
            if (total > 1 && done > 0) return `Running · ${done} of ${total} steps complete`;
            return 'Running';
        }

        // Status is derived from the last run plus its age, so "succeeded three days
        // ago" reads as stale rather than healthy.
        function collectionHealth(run) {
            if (!run) return { tone: 'idle', text: 'Never collected' };
            if (run.active) return { tone: 'running', text: collectionStageText(run) };
            // A cancellation is a deliberate act, not a fault: it gets the neutral
            // idle treatment rather than the red that means something went wrong.
            // The API reports the termination code, which is USER_CANCELED for a
            // cancel from this UI and CANCELED for other cancellation paths.
            if (String(run.result || '').indexOf('CANCEL') !== -1) {
                return { tone: 'idle', text: 'Cancelled' };
            }
            if (run.result && run.result !== 'SUCCESS') {
                return { tone: 'failed', text: 'Failed' };
            }
            const ageH = run.start_time ? (Date.now() - Number(run.start_time)) / 3600000 : null;
            if (ageH !== null && ageH > COLLECT_STALE_HOURS) {
                return { tone: 'stale', text: 'Stale' };
            }
            return { tone: 'ok', text: 'Healthy' };
        }

        function collectionRow(job) {
            if (!job.configured) {
                return `
                    <div class="collect-row is-unconfigured">
                        <div class="collect-state">
                            <span class="collect-dot idle"></span>
                            <span>Not connected</span>
                        </div>
                        <div>
                            <div class="collect-name">${escapeHtml(job.label)}</div>
                            <div class="collect-desc">${escapeHtml(job.description)}</div>
                        </div>
                        <div class="collect-fresh-sub">Re-run the installer to manage this here.</div>
                        <div class="collect-actions"></div>
                    </div>`;
            }

            const run = job.latest_run;
            const health = collectionHealth(run);
            const active = run && run.active;
            if (active && run.start_time) collectionRunStart[job.kind] = Number(run.start_time);

            const rowClass = active ? ' is-running'
                : health.tone === 'stale' ? ' is-stale'
                : health.tone === 'failed' ? ' is-failed' : '';

            const substate = active
                ? `<div class="collect-substate" data-elapsed="${escapeHtml(job.kind)}">${formatElapsed(Date.now() - (Number(run.start_time) || Date.now()))} elapsed</div>`
                : '';

            let freshness = '<div class="collect-fresh-sub">No runs recorded</div>';
            if (run && run.start_time) {
                const duration = (run.end_time && run.start_time)
                    ? formatElapsed(Number(run.end_time) - Number(run.start_time)) : null;
                freshness = `
                    <div class="collect-fresh">${escapeHtml(formatAgo(run.start_time))}</div>
                    <div class="collect-fresh-sub">
                        ${duration ? 'Completed in ' + escapeHtml(duration) : 'In progress'}
                    </div>`;
            }

            const nameCell = job.job_url
                ? `<a class="collect-link" href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener"
                      title="Open in Workflows">${escapeHtml(job.label)}<svg class="collect-link-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/></svg></a>`
                : escapeHtml(job.label);

            return `
                <div class="collect-row${rowClass}" data-kind="${escapeHtml(job.kind)}">
                    <div>
                        <div class="collect-state">
                            <span class="collect-dot ${health.tone}"></span>
                            <span>${escapeHtml(health.text)}</span>
                        </div>
                        ${substate}
                    </div>
                    <div>
                        <div class="collect-name">${nameCell}</div>
                        <div class="collect-desc">${escapeHtml(job.description)}</div>
                        ${job.feeds ? `<div class="collect-feeds">Powers <span>${escapeHtml(job.feeds)}</span></div>` : ''}
                    </div>
                    <div>${freshness}</div>
                    <div class="collect-actions">
                        ${run && run.run_page_url
                            ? `<a class="btn btn-sm btn-ghost" href="${escapeHtml(run.run_page_url)}" target="_blank" rel="noopener">Last run</a>`
                            : ''}
                        <button class="btn btn-sm btn-ghost" onclick="toggleScheduleEditor('${escapeHtml(job.kind)}')">Schedule</button>
                        ${active
                            ? `<button class="btn btn-sm btn-stop" onclick="cancelCollection('${escapeHtml(job.kind)}')">Cancel run</button>`
                            : `<button class="btn btn-sm" onclick="startCollection('${escapeHtml(job.kind)}')">Run now</button>`}
                    </div>
                    ${active ? '<div class="collect-bar"><div class="collect-bar-fill"></div></div>' : ''}
                    <div class="collect-drawer" id="schedule-${escapeHtml(job.kind)}" style="display:none;"></div>
                </div>`;
        }

        function startElapsedTicker() {
            if (collectionElapsedTimer) clearInterval(collectionElapsedTimer);
            collectionElapsedTimer = setInterval(() => {
                let any = false;
                document.querySelectorAll('[data-elapsed]').forEach(node => {
                    const started = collectionRunStart[node.dataset.elapsed];
                    if (!started) return;
                    any = true;
                    node.textContent = formatElapsed(Date.now() - started) + ' elapsed';
                });
                if (!any) { clearInterval(collectionElapsedTimer); collectionElapsedTimer = null; }
            }, 1000);
        }

        async function loadCollectionPanel(options) {
            const panel = document.getElementById('collection-panel');
            const quiet = options && options.quiet;
            // Preserve any open schedule drawer across a quiet refresh.
            const openDrawers = quiet
                ? Array.from(document.querySelectorAll('.collect-drawer'))
                    .filter(d => d.style.display !== 'none').map(d => d.id.replace('schedule-', ''))
                : [];

            if (!quiet) {
                panel.innerHTML = '<div class="loading"><div class="spinner"></div>Checking collection status…</div>';
            }
            try {
                const result = await fetch('/api/collection/status').then(r => r.json());
                if (result.error) {
                    panel.innerHTML = `
                        <div class="card" style="padding:16px 18px;">
                            <div style="font-weight:600;margin-bottom:4px;">Couldn't check collection status</div>
                            <div style="font-size:.85em;color:var(--text-muted);">${escapeHtml(result.error)}</div>
                        </div>`;
                    return null;
                }
                const jobs = result.jobs || [];
                const groups = result.groups || [];
                const stale = jobs.filter(j => j.configured && collectionHealth(j.latest_run).tone === 'stale').length;
                const failed = jobs.filter(j => j.configured && collectionHealth(j.latest_run).tone === 'failed').length;

                let banner = '';
                if (failed > 0) {
                    banner = `<div class="alert" style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.3);border-radius:10px;padding:12px 15px;margin-bottom:18px;font-size:.87em;color:#fca5a5;">
                        ${failed} collection${failed === 1 ? '' : 's'} failed on the last run. Views that depend on them may be showing older data.
                    </div>`;
                } else if (stale > 0) {
                    banner = `<div class="alert" style="background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.3);border-radius:10px;padding:12px 15px;margin-bottom:18px;font-size:.87em;color:#fcd34d;">
                        ${stale} collection${stale === 1 ? '' : 's'} last ran more than ${COLLECT_STALE_HOURS} hours ago.
                    </div>`;
                }

                const sections = groups.map(group => {
                    const inGroup = jobs.filter(j => j.group === group);
                    if (!inGroup.length) return '';
                    return `
                        <div class="collect-group">
                            <div class="collect-group-head">
                                <span class="collect-group-title">${escapeHtml(group)}</span>
                                <span class="collect-group-rule"></span>
                            </div>
                            ${inGroup.map(collectionRow).join('')}
                        </div>`;
                }).join('');

                panel.innerHTML = banner + sections;
                if (jobs.some(j => j.latest_run && j.latest_run.active)) startElapsedTicker();
                openDrawers.forEach(kind => toggleScheduleEditor(kind));
                return jobs;
            } catch (e) {
                panel.innerHTML = `<div class="card" style="padding:16px;"><div style="color:#fca5a5;">${escapeHtml(e.message)}</div></div>`;
                return null;
            }
        }

        async function startCollection(kind) {
            try {
                const result = await fetch('/api/collection/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ kind: kind }),
                }).then(r => r.json());

                await loadCollectionPanel({ quiet: true });
                if (result.error) {
                    collectionRowNote(kind, result.error, 'error');
                    return;
                }
                collectionRunStart[kind] = Date.now();
                startElapsedTicker();
                pollCollectionRun(result.run_id, kind);
            } catch (e) {
                await loadCollectionPanel();
            }
        }

        // Show a message inside a collection row, for outcomes that belong next to
        // the job they concern rather than in a global banner.
        function collectionRowNote(kind, text, tone) {
            const row = document.querySelector(`.collect-row[data-kind="${kind}"]`);
            if (!row) return;
            const note = document.createElement('div');
            const color = tone === 'error' ? '#fca5a5' : '#94a3b8';
            note.style.cssText =
                `grid-column:1/-1;margin-top:9px;font-size:.83em;color:${color};`;
            note.textContent = text;
            row.appendChild(note);
        }

        async function cancelCollection(kind) {
            const row = document.querySelector(`.collect-row[data-kind="${kind}"]`);
            const btn = row && row.querySelector('.btn-stop');
            if (btn) { btn.disabled = true; btn.textContent = 'Cancelling…'; }
            try {
                const result = await fetch('/api/collection/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ kind: kind }),
                }).then(r => r.json());

                if (result.error) {
                    if (btn) { btn.disabled = false; btn.textContent = 'Cancel run'; }
                    await loadCollectionPanel({ quiet: true });
                    collectionRowNote(kind, result.error, 'error');
                    return;
                }
                if (!result.cancelled) {
                    if (collectionPollTimers[kind]) clearTimeout(collectionPollTimers[kind]);
                    delete collectionRunStart[kind];
                    await loadCollectionPanel({ quiet: true });
                    collectionRowNote(kind, result.message || 'That job was not running.', 'muted');
                    return;
                }

                // Jobs take several seconds to actually reach TERMINATED, so an
                // immediate refresh would still read RUNNING and leave the row stuck
                // on stale state. Keep polling the run until it settles.
                if (result.run_id) {
                    pollCollectionRun(result.run_id, kind);
                } else {
                    delete collectionRunStart[kind];
                    await loadCollectionPanel({ quiet: true });
                }
            } catch (e) {
                await loadCollectionPanel({ quiet: true });
                collectionRowNote(kind, e.message, 'error');
            }
        }

        function pollCollectionRun(runId, kind) {
            if (collectionPollTimers[kind]) clearTimeout(collectionPollTimers[kind]);
            let attempts = 0;
            const tick = async () => {
                attempts += 1;
                try {
                    const run = await fetch(`/api/collection/run/${runId}`).then(r => r.json());
                    await loadCollectionPanel({ quiet: true });
                    if (!run.active) {
                        delete collectionRunStart[kind];
                        const row = document.querySelector(`.collect-row[data-kind="${kind}"]`);
                        if (row && run.result === 'SUCCESS') row.classList.add('just-finished');
                        return;
                    }
                } catch (e) { /* transient; keep polling */ }
                // Fast early polling so short runs feel responsive, backing off so a
                // long collection doesn't hammer the API.
                const delay = attempts <= 6 ? 5000 : attempts <= 20 ? 15000 : 30000;
                if (attempts < 160) collectionPollTimers[kind] = setTimeout(tick, delay);
            };
            collectionPollTimers[kind] = setTimeout(tick, 3000);
        }

        const SCHEDULE_PRESETS = [
            { label: 'Every hour',           cron: '0 0 * * * ?' },
            { label: 'Daily at 02:00',       cron: '0 0 2 * * ?' },
            { label: 'Daily at 08:00',       cron: '0 0 8 * * ?' },
            { label: 'Weekdays at 08:00',    cron: '0 0 8 ? * MON-FRI' },
            { label: 'Weekly, Sunday 02:00', cron: '0 0 2 ? * SUN' },
        ];

        async function toggleScheduleEditor(kind) {
            const box = document.getElementById(`schedule-${kind}`);
            if (!box) return;
            if (box.style.display !== 'none' && box.dataset.loaded === '1') {
                box.style.display = 'none';
                box.dataset.loaded = '';
                return;
            }
            box.style.display = 'block';
            box.innerHTML = '<div class="loading" style="padding:6px 0;"><div class="spinner"></div>Loading schedule…</div>';
            try {
                const sched = await fetch(`/api/collection/schedule/${kind}`).then(r => r.json());
                if (sched.error) {
                    box.innerHTML = `<div style="font-size:.84em;color:#fca5a5;">${escapeHtml(sched.error)}</div>`;
                    box.dataset.loaded = '1';
                    return;
                }
                const current = sched.cron || '';
                const matched = SCHEDULE_PRESETS.find(p => p.cron === current);
                box.innerHTML = `
                    <div class="collect-drawer-grid">
                        <div class="collect-field">
                            <span class="collect-field-label">Automatic collection</span>
                            <label class="collect-switch">
                                <input type="checkbox" id="sched-on-${kind}" ${sched.paused ? '' : 'checked'}>
                                <span class="collect-switch-track"></span>
                                <span id="sched-on-label-${kind}">${sched.paused ? 'Off' : 'On'}</span>
                            </label>
                        </div>
                        <div class="collect-field">
                            <span class="collect-field-label">Frequency</span>
                            <select id="sched-preset-${kind}">
                                ${SCHEDULE_PRESETS.map(pr =>
                                    `<option value="${escapeHtml(pr.cron)}" ${pr.cron === current ? 'selected' : ''}>${escapeHtml(pr.label)}</option>`).join('')}
                                <option value="__custom" ${matched ? '' : 'selected'}>Custom schedule…</option>
                            </select>
                        </div>
                        <div class="collect-field">
                            <span class="collect-field-label">Time zone</span>
                            <input type="text" id="sched-tz-${kind}" value="${escapeHtml(sched.timezone || 'UTC')}">
                        </div>
                        <div class="collect-field" id="sched-custom-${kind}" style="${matched ? 'display:none;' : ''}">
                            <span class="collect-field-label">Cron expression</span>
                            <input type="text" id="sched-cron-${kind}" value="${escapeHtml(current)}" placeholder="0 0 8 ? * *">
                        </div>
                        <div class="collect-field" style="flex:0 0 auto;">
                            <span class="collect-field-label">&nbsp;</span>
                            <button class="btn btn-sm" onclick="saveSchedule('${escapeHtml(kind)}')">Save schedule</button>
                        </div>
                    </div>
                    <div class="collect-msg" id="sched-msg-${kind}"></div>`;
                box.dataset.loaded = '1';

                const preset = document.getElementById(`sched-preset-${kind}`);
                preset.addEventListener('change', () => {
                    const isCustom = preset.value === '__custom';
                    document.getElementById(`sched-custom-${kind}`).style.display = isCustom ? 'flex' : 'none';
                    if (!isCustom) document.getElementById(`sched-cron-${kind}`).value = preset.value;
                });
                const toggle = document.getElementById(`sched-on-${kind}`);
                toggle.addEventListener('change', () => {
                    document.getElementById(`sched-on-label-${kind}`).textContent = toggle.checked ? 'On' : 'Off';
                });
            } catch (e) {
                box.innerHTML = `<div style="font-size:.84em;color:#fca5a5;">${escapeHtml(e.message)}</div>`;
                box.dataset.loaded = '1';
            }
        }

        async function saveSchedule(kind) {
            const msg = document.getElementById(`sched-msg-${kind}`);
            const preset = document.getElementById(`sched-preset-${kind}`).value;
            const cron = preset === '__custom'
                ? document.getElementById(`sched-cron-${kind}`).value.trim()
                : preset;
            const timezone = document.getElementById(`sched-tz-${kind}`).value.trim() || 'UTC';
            const enabled = document.getElementById(`sched-on-${kind}`).checked;
            msg.innerHTML = '<span style="color:var(--text-muted);">Saving…</span>';
            try {
                const result = await fetch(`/api/collection/schedule/${kind}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cron: cron, timezone: timezone, paused: !enabled }),
                }).then(r => r.json());
                if (result.error) {
                    msg.innerHTML = `<span style="color:#fca5a5;">${escapeHtml(result.error)}</span>`;
                    return;
                }
                msg.innerHTML = enabled
                    ? '<span style="color:#86efac;">Saved — this collection will run on the new schedule.</span>'
                    : '<span style="color:#86efac;">Saved — automatic collection is off. You can still run it manually.</span>';
                loadCollectionPanel({ quiet: true });
            } catch (e) {
                msg.innerHTML = `<span style="color:#fca5a5;">${escapeHtml(e.message)}</span>`;
            }
        }

        async function loadSecretsOverview() {
            const container = document.getElementById('secretsoverview-results');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading scan results...</div>';

            try {
                const [sumRes, detRes, wsRes, topRes, sharedRes] = await Promise.all([
                    fetch('/api/secrets/summary').then(r => r.json()),
                    fetch('/api/secrets/by-detector').then(r => r.json()).catch(() => ({})),
                    fetch('/api/secrets/by-workspace').then(r => r.json()).catch(() => ({})),
                    fetch('/api/secrets/top-objects').then(r => r.json()).catch(() => ({})),
                    fetch('/api/secrets/shared').then(r => r.json()).catch(() => ({})),
                ]);

                if (sumRes.ready === false) {
                    showSecretsNotReady('secretsoverview-results', sumRes.message);
                    return;
                }
                if (sumRes.error) { showEmpty('secretsoverview-results', sumRes.error); return; }

                const s = sumRes.summary || {};
                const verified = Number(s.verified_findings || 0);
                const total = Number(s.total_findings || 0);

                let html = '';

                // Lead with the urgent case: confirmed-live credentials.
                if (verified > 0) {
                    html += `
                        <div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.3);border-radius:12px;padding:14px 18px;margin-bottom:16px;">
                            <div style="font-weight:600;color:#fca5a5;margin-bottom:3px;">${verified} confirmed active credential${verified === 1 ? '' : 's'} exposed</div>
                            <div style="font-size:0.87em;color:var(--text-secondary);">
                                These were validated against the live service and are working right now. Rotate them, then remove them from source.
                            </div>
                        </div>`;
                }

                html += `
                    <div class="card secret-summary">
                        <div class="secret-section-title">Exposure Summary</div>
                        <div class="secret-stat-grid">
                            ${secretStatBlock('Confirmed active', verified, verified > 0 ? '#ef4444' : '#22c55e')}
                            ${secretStatBlock('Total findings', total, total > 0 ? '#f59e0b' : '#22c55e')}
                            ${secretStatBlock('Distinct secrets', s.distinct_secrets || 0, '#3b82f6')}
                            ${secretStatBlock('Objects affected', s.affected_objects || 0, '#3b82f6')}
                            ${secretStatBlock('In notebooks', s.notebook_findings || 0, '#8b5cf6')}
                            ${secretStatBlock('In cluster configs', s.cluster_findings || 0, '#8b5cf6')}
                        </div>
                        <div class="secret-summary-foot">
                            ${s.workspaces_scanned || 0} workspace${Number(s.workspaces_scanned) === 1 ? '' : 's'} scanned
                            &middot; ${s.affected_workspaces || 0} with findings
                            ${s.last_scan_time ? '&middot; last scan ' + escapeHtml(String(s.last_scan_time).slice(0, 16).replace('T', ' ')) : ''}
                        </div>
                    </div>`;

                // Detector distribution and per-workspace exposure, side by side.
                const detRows = (detRes && detRes.rows) || [];
                const wsRows = (wsRes && wsRes.rows) || [];
                html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;margin-bottom:16px;">';

                if (detRows.length) {
                    const max = Math.max(...detRows.map(r => Number(r.findings) || 0), 1);
                    html += `
                        <div class="card secret-card">
                            <div class="secret-section-title">Findings by Detector</div>
                            ${detRows.map(r => secretBar(
                                r.detector_name,
                                Number(r.findings) || 0,
                                max,
                                Number(r.verified) > 0 ? '#ef4444' : '#f59e0b'
                            )).join('')}
                        </div>`;
                }

                if (wsRows.length) {
                    html += `
                        <div class="card secret-table-card">
                            <div class="secret-section-title">Exposure by Workspace</div>
                            <table class="data-table">
                                <thead><tr><th>Workspace</th><th style="text-align:right;">Findings</th><th style="text-align:right;">Active</th></tr></thead>
                                <tbody>
                                    ${wsRows.map(r => `
                                        <tr>
                                            <td>${escapeHtml(r.workspace_name || r.workspace_id)}</td>
                                            <td style="text-align:right;">${Number(r.findings) > 0
                                                ? `<span style="color:#f59e0b;font-weight:600;">${r.findings}</span>`
                                                : '<span style="color:#22c55e;">clean</span>'}</td>
                                            <td style="text-align:right;">${Number(r.verified) > 0
                                                ? `<span style="color:#ef4444;font-weight:600;">${r.verified}</span>`
                                                : '—'}</td>
                                        </tr>`).join('')}
                                </tbody>
                            </table>
                        </div>`;
                }
                html += '</div>';

                // A repeated hash means one credential was copied to several
                // places; every copy has to be found before rotation is complete.
                const sharedRows = (sharedRes && sharedRes.rows) || [];
                if (sharedRows.length) {
                    html += `
                        <div class="card secret-table-card" style="margin-bottom:16px;">
                            <div class="secret-section-title">Reused Credentials</div>
                            <div class="secret-card-sub">
                                The same secret found in more than one place. Rotating it means updating every copy.
                            </div>
                            <table class="data-table">
                                <thead><tr><th>Status</th><th>Detector</th><th>Hash</th><th style="text-align:right;">Copies</th><th style="text-align:right;">Workspaces</th><th>Example</th></tr></thead>
                                <tbody>
                                    ${sharedRows.map(r => `
                                        <tr>
                                            <td>${secretStatusBadge(Number(r.verified) > 0)}</td>
                                            <td>${escapeHtml(r.detector_name)}</td>
                                            <td class="mono">${escapeHtml(String(r.secret_sha256 || '').slice(0, 12))}…</td>
                                            <td style="text-align:right;font-weight:600;">${r.occurrences}</td>
                                            <td style="text-align:right;">${r.workspaces}</td>
                                            <td class="truncate">${escapeHtml(r.example_object)}</td>
                                        </tr>`).join('')}
                                </tbody>
                            </table>
                        </div>`;
                }

                // Where to start remediating.
                const topRows = (topRes && topRes.rows) || [];
                if (topRows.length) {
                    html += `
                        <div class="card secret-table-card">
                            <div class="secret-section-title">Most Exposed Objects</div>
                            <div class="secret-card-sub">
                                Notebooks and cluster configurations holding the most findings, confirmed-active first.
                            </div>
                            <table class="data-table">
                                <thead><tr><th>Source</th><th>Object</th><th>Location</th><th style="text-align:right;">Findings</th><th style="text-align:right;">Active</th><th style="text-align:right;">Detectors</th></tr></thead>
                                <tbody>
                                    ${topRows.map(r => `
                                        <tr>
                                            <td><span class="badge" style="background:rgba(148,163,184,.14);color:#cbd5e1;">${escapeHtml(r.source_type)}</span></td>
                                            <td class="truncate" style="max-width:230px;">${escapeHtml(r.object_name)}</td>
                                            <td class="mono truncate">${escapeHtml(r.object_path)}</td>
                                            <td style="text-align:right;font-weight:600;">${r.findings}</td>
                                            <td style="text-align:right;">${Number(r.verified) > 0
                                                ? `<span style="color:#ef4444;font-weight:600;">${r.verified}</span>` : '—'}</td>
                                            <td style="text-align:right;">${r.detectors}</td>
                                        </tr>`).join('')}
                                </tbody>
                            </table>
                        </div>`;
                }

                if (total === 0) {
                    html += `
                        <div class="card" style="padding:22px;text-align:center;">
                            <div style="font-weight:600;color:#22c55e;margin-bottom:4px;">No hardcoded credentials found</div>
                            <div style="font-size:0.88em;color:var(--text-muted);">
                                ${s.workspaces_scanned || 0} workspace(s) scanned clean in the latest run.
                            </div>
                        </div>`;
                }

                container.innerHTML = html;
            } catch (e) {
                showEmpty('secretsoverview-results', 'Failed to load scan results: ' + e.message);
            }
        }

        let secretsFiltersLoaded = false;

        // --- Code security ----------------------------------------------------
        const CODE_SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

        function codeSeverityPill(severity) {
            const s = String(severity || '').toUpperCase();
            const tone = s === 'CRITICAL' ? 'triggered'
                : s === 'HIGH' ? 'error'
                : s === 'MEDIUM' ? 'unknown' : 'paused';
            const label = s ? s.charAt(0) + s.slice(1).toLowerCase() : 'Unknown';
            return `<span class="alert-pill ${tone}">${label}</span>`;
        }

        function codeScannerLabel(scanner) {
            return scanner === 'trivy' ? 'Dependency' : 'Code pattern';
        }

        function showCodeNotReady(containerId, message) {
            document.getElementById(containerId).innerHTML = `
                <div class="alert-empty">
                    <div class="alert-empty-title">No code scan yet</div>
                    <div class="alert-empty-sub">${escapeHtml(message || 'Run the Code Scanner to analyse workspace code.')}</div>
                    <button class="btn btn-sm" onclick="document.querySelector('[data-page=&quot;collection&quot;]').click()">Open Data Collection</button>
                </div>`;
        }

        async function loadCodeOverview() {
            const container = document.getElementById('codeoverview-results');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading code scan results…</div>';
            try {
                const [summary, rules, objects, packages] = await Promise.all([
                    fetch('/api/code/summary').then(r => r.json()),
                    fetch('/api/code/by-rule').then(r => r.json()).catch(() => ({})),
                    fetch('/api/code/top-objects').then(r => r.json()).catch(() => ({})),
                    fetch('/api/code/vulnerable-packages').then(r => r.json()).catch(() => ({})),
                ]);
                if (summary.ready === false) { showCodeNotReady('codeoverview-results', summary.message); return; }
                if (summary.error) { showEmpty('codeoverview-results', summary.error); return; }
                renderCodeOverview(summary, rules, objects, packages);
            } catch (e) {
                showEmpty('codeoverview-results', 'Failed to load code scan results: ' + e.message);
            }
        }

        function renderCodeOverview(summary, rules, objects, packages) {
            const s = summary.summary || {};
            const run = summary.run || {};
            const total = Number(s.total_findings || 0);
            const critical = Number(s.critical || 0);
            const high = Number(s.high || 0);

            let html = '';

            // A scanner that could not run makes a low finding count misleading,
            // so its status is stated before any totals.
            const degraded = [];
            const semgrepStatus = String(run.semgrep_status || '');
            const trivyStatus = String(run.trivy_status || '');
            if (semgrepStatus && semgrepStatus !== 'ready') degraded.push('Code patterns: ' + semgrepStatus);
            if (trivyStatus && trivyStatus !== 'ready') degraded.push('Dependencies: ' + trivyStatus);
            if (degraded.length) {
                html += `
                    <div class="settings-banner bad">
                        <div>
                            <div class="settings-banner-title">Partial scan</div>
                            <div class="settings-banner-sub">
                                ${degraded.map(escapeHtml).join('<br>')}
                            </div>
                        </div>
                    </div>`;
            } else if (critical + high > 0) {
                html += `
                    <div class="settings-banner bad">
                        <div>
                            <div class="settings-banner-title">${critical + high} finding${critical + high === 1 ? '' : 's'} at high or critical severity</div>
                            <div class="settings-banner-sub">Review these first: they are exploitable or have a published fix available.</div>
                        </div>
                    </div>`;
            }

            html += `
                <div class="card secret-summary">
                    <div class="secret-section-title">Scan Summary</div>
                    <div class="secret-stat-grid">
                        ${secretStatBlock('Critical', critical, critical > 0 ? '#ef4444' : '#22c55e')}
                        ${secretStatBlock('High', high, high > 0 ? '#f59e0b' : '#22c55e')}
                        ${secretStatBlock('Medium', Number(s.medium || 0), '#3b82f6')}
                        ${secretStatBlock('Low', Number(s.low || 0), '#64748b')}
                        ${secretStatBlock('Code patterns', Number(s.code_findings || 0), '#8b5cf6')}
                        ${secretStatBlock('Vulnerable packages', Number(s.vulnerable_packages || 0), '#8b5cf6')}
                    </div>
                    <div class="secret-summary-foot">
                        ${Number(run.objects_scanned || 0)} object${Number(run.objects_scanned) === 1 ? '' : 's'} scanned
                        &middot; ${Number(run.pinned_packages || 0)} pinned package${Number(run.pinned_packages) === 1 ? '' : 's'} checked
                        ${s.last_scan_time ? '&middot; last scan ' + escapeHtml(String(s.last_scan_time).slice(0, 16).replace('T', ' ')) : ''}
                    </div>
                </div>`;

            if (run.notes) {
                html += `
                    <div class="settings-note" style="margin-bottom:16px;">
                        ${escapeHtml(run.notes)}. Pin these to an exact version to include them in vulnerability checks.
                    </div>`;
            }

            const ruleRows = (rules && rules.rows) || [];
            const packageRows = (packages && packages.rows) || [];
            html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px;margin-bottom:16px;">';

            if (ruleRows.length) {
                html += `
                    <div class="card secret-table-card">
                        <div class="secret-section-title">Findings by Rule</div>
                        <table class="data-table">
                            <thead><tr><th>Severity</th><th>Rule</th><th style="text-align:right;">Findings</th><th style="text-align:right;">Objects</th></tr></thead>
                            <tbody>
                                ${ruleRows.map(r => `
                                    <tr>
                                        <td>${codeSeverityPill(r.severity)}</td>
                                        <td class="truncate" style="max-width:260px;">${escapeHtml(r.rule_id)}</td>
                                        <td style="text-align:right;font-weight:600;">${r.findings}</td>
                                        <td style="text-align:right;">${r.objects}</td>
                                    </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>`;
            }

            if (packageRows.length) {
                html += `
                    <div class="card secret-table-card">
                        <div class="secret-section-title">Vulnerable Packages</div>
                        <div class="secret-card-sub">Upgrade to the fixed version to clear every CVE listed for that package.</div>
                        <table class="data-table">
                            <thead><tr><th>Package</th><th>Installed</th><th>Fixed in</th><th style="text-align:right;">CVEs</th></tr></thead>
                            <tbody>
                                ${packageRows.map(r => `
                                    <tr>
                                        <td>${escapeHtml(r.package_name)}</td>
                                        <td class="mono">${escapeHtml(r.installed_version)}</td>
                                        <td class="mono">${escapeHtml(r.fixed_version || '—')}</td>
                                        <td style="text-align:right;font-weight:600;">${r.cves}</td>
                                    </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>`;
            }
            html += '</div>';

            const objectRows = (objects && objects.rows) || [];
            if (objectRows.length) {
                html += `
                    <div class="card secret-table-card">
                        <div class="secret-section-title">Most Affected Objects</div>
                        <div class="secret-card-sub">Notebooks and files with the most code findings, highest severity first.</div>
                        <table class="data-table">
                            <thead><tr><th>Object</th><th style="text-align:right;">Findings</th><th style="text-align:right;">High or critical</th><th style="text-align:right;">Rules</th></tr></thead>
                            <tbody>
                                ${objectRows.map(r => `
                                    <tr>
                                        <td class="mono truncate">${escapeHtml(r.object_path)}</td>
                                        <td style="text-align:right;font-weight:600;">${r.findings}</td>
                                        <td style="text-align:right;">${Number(r.severe) > 0
                                            ? `<span style="color:#fca5a5;font-weight:600;">${r.severe}</span>` : '—'}</td>
                                        <td style="text-align:right;">${r.rules}</td>
                                    </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>`;
            }

            if (total === 0 && !degraded.length) {
                html += `
                    <div class="card" style="padding:22px;text-align:center;">
                        <div style="font-weight:600;color:#22c55e;margin-bottom:4px;">No code security findings</div>
                        <div style="font-size:.88em;color:var(--text-muted);">
                            ${Number(run.objects_scanned || 0)} object${Number(run.objects_scanned) === 1 ? '' : 's'} and
                            ${Number(run.pinned_packages || 0)} package${Number(run.pinned_packages) === 1 ? '' : 's'} scanned clean.
                        </div>
                    </div>`;
            }

            document.getElementById('codeoverview-results').innerHTML = html;
        }

        function loadCodeFindings() {
            runCodeFindings();
        }

        async function runCodeFindings() {
            const container = document.getElementById('codefindings-results');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading findings…</div>';

            const params = new URLSearchParams();
            const scanner = document.getElementById('cf-scanner').value;
            const severity = document.getElementById('cf-severity').value;
            const search = document.getElementById('cf-search').value.trim();
            if (scanner) params.set('scanner', scanner);
            if (severity) params.set('severity', severity);
            if (search) params.set('q', search);

            try {
                const result = await fetch('/api/code/findings?' + params.toString()).then(r => r.json());
                if (result.ready === false) { showCodeNotReady('codefindings-results', result.message); return; }
                if (result.error) { showEmpty('codefindings-results', result.error); return; }

                const rows = result.rows || [];
                if (!rows.length) { showEmpty('codefindings-results', 'No findings match these filters.'); return; }

                container.innerHTML = `
                    <div class="results-container">
                        <div class="results-header">
                            <div class="results-title">${result.count} finding${result.count === 1 ? '' : 's'}${result.truncated ? ' (showing the first 500)' : ''}</div>
                        </div>
                        <table class="data-table data-table-padded">
                            <thead><tr>
                                <th>Severity</th><th>Type</th><th>Rule</th><th>Object</th>
                                <th>Detail</th><th style="text-align:right;">Line</th>
                            </tr></thead>
                            <tbody>
                                ${rows.map(r => `
                                    <tr>
                                        <td>${codeSeverityPill(r.severity)}</td>
                                        <td style="white-space:nowrap;">${escapeHtml(codeScannerLabel(r.scanner))}</td>
                                        <td class="truncate" style="max-width:230px;">
                                            ${r.reference_url
                                                ? `<a href="${escapeHtml(r.reference_url)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;">${escapeHtml(r.rule_id)}</a>`
                                                : escapeHtml(r.rule_id)}
                                        </td>
                                        <td class="mono truncate" style="max-width:260px;">${escapeHtml(r.object_path)}</td>
                                        <td class="truncate" style="max-width:340px;">${escapeHtml(
                                            r.scanner === 'trivy'
                                                ? `${r.package_name} ${r.installed_version}` + (r.fixed_version ? ` → ${r.fixed_version}` : '')
                                                : (r.description || ''))}</td>
                                        <td style="text-align:right;">${r.line_start === null || r.line_start === undefined ? '—' : r.line_start}</td>
                                    </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>`;
            } catch (e) {
                showEmpty('codefindings-results', 'Failed to load findings: ' + e.message);
            }
        }

        // --- Settings panel -------------------------------------------------
        // Values that the app reads per request are editable here and take effect
        // immediately. Each is validated against the workspace before it is
        // applied, so a mistyped warehouse cannot break every page.

        const settingsState = { data: null, choices: null, dirty: {}, saving: false };

        function openSettingsPanel() {
            document.body.classList.add('drawer-open');
            document.getElementById('settings-scrim').hidden = false;
            document.getElementById('settings-drawer').hidden = false;
            document.getElementById('settings-body').innerHTML =
                '<div class="loading"><div class="spinner"></div>Checking your environment\u2026</div>';
            loadSettings();
        }

        function closeSettingsPanel() {
            document.body.classList.remove('drawer-open');
            document.getElementById('settings-scrim').hidden = true;
            document.getElementById('settings-drawer').hidden = true;
            settingsState.dirty = {};
        }

        document.addEventListener('keydown', ev => {
            const drawer = document.getElementById('settings-drawer');
            if (ev.key === 'Escape' && drawer && !drawer.hidden) closeSettingsPanel();
        });

        async function loadSettings() {
            try {
                const [data, choices] = await Promise.all([
                    fetch('/api/settings').then(r => r.json()),
                    fetch('/api/settings/choices').then(r => r.json()).catch(() => ({})),
                ]);
                if (data.error) {
                    document.getElementById('settings-body').innerHTML =
                        `<div class="health-summary bad">${escapeHtml(data.error)}</div>`;
                    return;
                }
                settingsState.data = data;
                settingsState.choices = choices || {};
                settingsState.dirty = {};
                renderSettings();
                updateSettingsIndicator(data.failing_count || 0);
            } catch (e) {
                document.getElementById('settings-body').innerHTML =
                    `<div class="health-summary bad">Could not load settings: ${escapeHtml(e.message)}</div>`;
            }
        }

        function updateSettingsIndicator(failing) {
            const dot = document.getElementById('settings-dot');
            if (dot) dot.hidden = failing === 0;
            const gear = document.getElementById('settings-gear');
            if (gear) {
                gear.title = failing
                    ? `${failing} item${failing === 1 ? '' : 's'} need attention`
                    : 'Settings';
            }
        }

        function markSettingDirty(key, value) {
            settingsState.dirty[key] = value;
            const bar = document.getElementById('settings-savebar');
            if (bar) bar.hidden = Object.keys(settingsState.dirty).length === 0;
        }

        function renderSettings() {
            const data = settingsState.data || {};
            const choices = settingsState.choices || {};
            const cfg = data.config || {};
            const checks = data.checks || [];
            const problems = checks.filter(c => !c.ok);

            let html = '';

            // Problems first, in plain language, with the fix. Healthy items are not
            // listed individually: a list of eight "Healthy" rows is noise.
            if (problems.length) {
                html += problems.map(c => `
                    <div class="issue">
                        <div class="issue-head">${escapeHtml(c.label)}</div>
                        <div class="issue-body">${escapeHtml(c.detail || '')}</div>
                        ${c.remedy ? `<div class="issue-fix">${escapeHtml(c.remedy)}</div>` : ''}
                    </div>`).join('');
            } else {
                html += `
                    <div class="all-clear">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>
                        <span>Everything is working</span>
                    </div>`;
            }

            const warehouses = choices.warehouses || [];
            const models = choices.model_endpoints || [];
            const spaces = choices.genie_spaces || [];

            html += '<div class="drawer-section-label">Configuration</div>';

            html += settingField('warehouse_id', 'SQL warehouse',
                'Runs every query and every alert.',
                selectMarkup('warehouse_id', cfg.warehouse_id,
                    warehouses.map(w => ({ value: w.id, label: `${w.name} (${w.state.toLowerCase()})` }))));

            html += settingField('schema', 'Results schema',
                'Where collection results are stored, as catalog.schema.',
                `<input class="field-input" id="set-schema" type="text"
                        value="${escapeHtml(cfg.schema || '')}"
                        onchange="markSettingDirty('schema', this.value)">`);

            html += settingField('model_endpoint', 'Assistant model',
                'Answers questions in the security assistant.',
                selectMarkup('model_endpoint', cfg.model_endpoint,
                    models.map(m => ({ value: m, label: m }))));

            html += settingField('genie_space_id', 'Genie space',
                'Optional. Lets the assistant answer from your Genie space.',
                selectMarkup('genie_space_id', cfg.genie_space_id,
                    spaces.map(sp => ({ value: sp.id, label: sp.name })), 'None'));

            html += `
                <div class="field">
                    <label class="switch-row" for="set-filtering">
                        <span>
                            <span class="field-label">Show each person only their own data</span>
                            <span class="field-help">Results are filtered by the viewer's own Unity Catalog permissions. Turning this off shows everyone the full dataset.</span>
                        </span>
                        <input id="set-filtering" type="checkbox" ${cfg.sp_fallback_allowed ? '' : 'checked'}
                               onchange="markSettingDirty('per_user_filtering', this.checked)">
                    </label>
                </div>`;

            const jobs = cfg.jobs || {};
            const missing = Object.keys(jobs).filter(k => !jobs[k].connected);
            html += '<div class="drawer-section-label">Analysis jobs</div>';
            html += `<div class="field-help" style="margin-bottom:10px;">
                ${Object.keys(jobs).length - missing.length} of ${Object.keys(jobs).length} deployed in this workspace.
                ${missing.length ? 'Not yet deployed: ' + missing.map(k => escapeHtml(jobs[k].label)).join(', ') + '.' : ''}
            </div>`;

            html += `
                <div class="drawer-savebar" id="settings-savebar" hidden>
                    <span class="savebar-text" id="settings-saveerr"></span>
                    <button class="btn btn-sm btn-ghost" onclick="loadSettings()">Discard</button>
                    <button class="btn btn-sm" id="settings-save" onclick="saveSettings()">Save</button>
                </div>
                <div class="drawer-note">
                    Changes apply immediately. If the app restarts, it returns to the values
                    set when it was installed.
                </div>`;

            document.getElementById('settings-body').innerHTML = html;
        }

        function settingField(key, label, help, control) {
            return `
                <div class="field">
                    <span class="field-label">${escapeHtml(label)}</span>
                    ${control}
                    <span class="field-help">${escapeHtml(help)}</span>
                </div>`;
        }

        function selectMarkup(key, current, options, emptyLabel) {
            // An unlisted current value is still offered, so opening the panel can
            // never silently change a setting that the workspace no longer lists.
            const known = options.some(o => o.value === current);
            const extra = (!known && current)
                ? `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>` : '';
            return `
                <select class="field-input" id="set-${escapeHtml(key)}"
                        onchange="markSettingDirty('${escapeHtml(key)}', this.value)">
                    ${emptyLabel ? `<option value=""${!current ? ' selected' : ''}>${escapeHtml(emptyLabel)}</option>` : ''}
                    ${extra}
                    ${options.map(o => `<option value="${escapeHtml(o.value)}"${o.value === current ? ' selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
                </select>`;
        }

        async function saveSettings() {
            if (settingsState.saving) return;
            const button = document.getElementById('settings-save');
            const status = document.getElementById('settings-saveerr');
            settingsState.saving = true;
            button.disabled = true;
            button.textContent = 'Saving\u2026';
            status.textContent = '';
            status.className = 'savebar-text';
            try {
                const result = await fetch('/api/settings', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settingsState.dirty),
                }).then(r => r.json());

                if (result.errors || result.error) {
                    const messages = result.errors
                        ? Object.values(result.errors) : [result.error];
                    status.textContent = messages.join(' ');
                    status.className = 'savebar-text is-error';
                    button.disabled = false;
                    button.textContent = 'Save';
                    settingsState.saving = false;
                    return;
                }
                settingsState.saving = false;
                await loadSettings();
            } catch (e) {
                status.textContent = e.message;
                status.className = 'savebar-text is-error';
                button.disabled = false;
                button.textContent = 'Save';
                settingsState.saving = false;
            }
        }

        (function probeSettings() {
            function run() {
                fetch('/api/settings')
                    .then(r => r.json())
                    .then(d => updateSettingsIndicator(d.failing_count || 0))
                    .catch(() => {});
            }
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', run);
            } else {
                run();
            }
        })();

        // --- Secret-scanning alerts ------------------------------------------
        // These wrap Databricks SQL alerts; the app supplies the query and
        // defaults so nobody has to write SQL against the scan tables.
        const alertState = { options: null, alerts: [], editing: null, selectedTemplate: null };

        function alertCronLabel(cron) {
            if (!cron) return 'No schedule';
            const preset = (alertState.options && alertState.options.schedule_presets || [])
                .find(p => p.cron === cron);
            return preset ? preset.label : cron;
        }

        function alertStatePill(a) {
            if (a.paused) return '<span class="alert-pill paused">Paused</span>';
            const st = String(a.state || 'UNKNOWN').toUpperCase();
            const tone = st === 'TRIGGERED' ? 'triggered'
                : st === 'OK' ? 'ok'
                : st === 'ERROR' ? 'error' : 'unknown';
            const text = st === 'TRIGGERED' ? 'Triggered'
                : st === 'OK' ? 'OK'
                : st === 'ERROR' ? 'Error' : 'Not yet run';
            return `<span class="alert-pill ${tone}">${text}</span>`;
        }

        function alertConditionText(a) {
            const opText = {
                GREATER_THAN: '>', GREATER_THAN_OR_EQUAL: '>=', LESS_THAN: '<',
                LESS_THAN_OR_EQUAL: '<=', EQUAL: '=', NOT_EQUAL: '!=',
            }[a.operator] || a.operator || '?';
            const t = a.threshold === null || a.threshold === undefined ? '?' : a.threshold;
            return `${a.column || 'value'} ${opText} ${t}`;
        }

        async function loadSecretsAlerts() {
            const container = document.getElementById('secretsalerts-results');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading alerts...</div>';
            try {
                const [options, list] = await Promise.all([
                    fetch('/api/secrets/alerts/options').then(r => r.json()),
                    fetch('/api/secrets/alerts').then(r => r.json()),
                ]);
                if (options.error) { showEmpty('secretsalerts-results', options.error); return; }
                if (list.error) { showEmpty('secretsalerts-results', list.error); return; }
                alertState.options = options;
                alertState.alerts = list.alerts || [];
                renderSecretsAlerts();
            } catch (e) {
                showEmpty('secretsalerts-results', 'Failed to load alerts: ' + e.message);
            }
        }

        function renderSecretsAlerts() {
            const container = document.getElementById('secretsalerts-results');
            const alerts = alertState.alerts;
            const options = alertState.options || {};

            if (!options.warehouse_configured) {
                container.innerHTML = `
                    <div class="alert-empty">
                        <div class="alert-empty-title">No SQL warehouse configured</div>
                        <div class="alert-empty-sub">Alerts run their query on a SQL warehouse. Re-run the SAT installer to bind one to this app.</div>
                    </div>`;
                return;
            }

            let html = `
                <div class="alert-toolbar">
                    <div class="alert-toolbar-note">
                        ${alerts.length
                            ? alerts.length + ' alert' + (alerts.length === 1 ? '' : 's') + ' configured'
                            : 'No alerts configured yet'}
                    </div>
                    <button class="btn btn-sm" onclick="openAlertEditor()">New alert</button>
                </div>
                <div id="alert-editor-slot"></div>`;

            if (!alerts.length) {
                html += `
                    <div class="alert-empty">
                        <div class="alert-empty-title">Nobody is being notified yet</div>
                        <div class="alert-empty-sub">
                            Create an alert to be emailed when the scanner finds exposed credentials.
                            Alerts are standard Databricks SQL alerts, so they also appear under
                            Alerts in the workspace and keep working if this app is removed.
                        </div>
                        <button class="btn btn-sm" onclick="openAlertEditor()">Create your first alert</button>
                    </div>`;
            } else {
                html += '<div class="alert-list">';
                alerts.forEach(a => {
                    const subs = (a.subscribers || []).length;
                    const dests = (a.destination_ids || []).length;
                    let recipients = [];
                    if (subs) recipients.push(subs + (subs === 1 ? ' recipient' : ' recipients'));
                    if (dests) recipients.push(dests + (dests === 1 ? ' destination' : ' destinations'));
                    html += `
                        <div class="alert-card${a.paused ? ' is-paused' : ''}">
                            <div class="alert-rail ${escapeHtml(a.severity || '')}"></div>
                            <div class="alert-body">
                                <div class="alert-name">
                                    ${escapeHtml(a.display_name || 'Untitled alert')}
                                    ${alertStatePill(a)}
                                </div>
                                <div class="alert-meta">
                                    <span>${escapeHtml(alertConditionText(a))}</span>
                                    <span class="sep">&middot;</span>
                                    <span>${escapeHtml(alertCronLabel(a.cron))}</span>
                                    ${recipients.length ? '<span class="sep">&middot;</span><span>' + escapeHtml(recipients.join(', ')) + '</span>' : ''}
                                    ${a.last_evaluated_at ? '<span class="sep">&middot;</span><span>checked ' + escapeHtml(String(a.last_evaluated_at).slice(0, 16).replace('T', ' ')) + '</span>' : ''}
                                </div>
                            </div>
                            <div class="alert-actions">
                                ${a.url ? `<a class="btn btn-sm btn-ghost" href="${escapeHtml(a.url)}" target="_blank" rel="noopener">Open</a>` : ''}
                                <button class="btn btn-sm btn-ghost" onclick="toggleAlertPause('${escapeHtml(a.id)}', ${a.paused ? 'false' : 'true'})">
                                    ${a.paused ? 'Resume' : 'Pause'}
                                </button>
                                <button class="btn btn-sm btn-ghost" onclick="openAlertEditor('${escapeHtml(a.id)}')">Edit</button>
                                <button class="btn btn-sm btn-stop" onclick="deleteAlert('${escapeHtml(a.id)}')">Delete</button>
                            </div>
                        </div>`;
                });
                html += '</div>';
            }
            container.innerHTML = html;
            if (alertState.editing !== null) renderAlertEditor();
        }

        function openAlertEditor(alertId) {
            const existing = alertId
                ? alertState.alerts.find(a => a.id === alertId) : null;
            alertState.editing = existing || {};
            alertState.selectedTemplate = existing
                ? existing.template_id
                : ((alertState.options.templates || [])[0] || {}).id;
            renderAlertEditor();
            const slot = document.getElementById('alert-editor-slot');
            if (slot) slot.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        function closeAlertEditor() {
            alertState.editing = null;
            alertState.selectedTemplate = null;
            renderSecretsAlerts();
        }

        function selectAlertTemplate(id) {
            alertState.selectedTemplate = id;
            renderAlertEditor();
        }

        function renderAlertEditor() {
            const slot = document.getElementById('alert-editor-slot');
            if (!slot) return;
            const e = alertState.editing || {};
            const isEdit = !!e.id;
            const options = alertState.options || {};
            const templates = options.templates || [];
            const tpl = templates.find(t => t.id === alertState.selectedTemplate) || templates[0] || {};

            const threshold = e.threshold !== undefined && e.threshold !== null && e.template_id === tpl.id
                ? e.threshold : tpl.default_threshold;
            const operator = (e.operator && e.template_id === tpl.id) ? e.operator : tpl.default_operator;
            const subscribers = (e.subscribers || []).join(', ')
                || (isEdit ? '' : (options.current_user || ''));
            const cron = e.cron || '0 0 8 * * ?';
            const retrigger = e.retrigger_seconds === undefined || e.retrigger_seconds === null
                ? 3600 : e.retrigger_seconds;

            const presets = options.schedule_presets || [];
            const cronKnown = presets.some(p => p.cron === cron);
            const destinations = options.destinations || [];

            slot.innerHTML = `
                <div class="alert-form">
                    <div class="alert-form-title">${isEdit ? 'Edit alert' : 'New alert'}</div>
                    <div class="alert-form-sub">
                        Creates a Databricks SQL alert. The query below is generated for you and runs on this app's warehouse.
                    </div>

                    <div class="alert-type-grid">
                        ${templates.map(t => `
                            <button type="button" class="alert-type${t.id === tpl.id ? ' selected' : ''}"
                                    onclick="selectAlertTemplate('${escapeHtml(t.id)}')">
                                <div class="alert-type-head">
                                    <span class="alert-type-label">${escapeHtml(t.label)}</span>
                                    <span class="alert-pill ${t.severity === 'critical' ? 'triggered' : t.severity === 'high' ? 'error' : 'unknown'}">${escapeHtml(t.severity)}</span>
                                </div>
                                <div class="alert-type-desc">${escapeHtml(t.description)}</div>
                            </button>`).join('')}
                    </div>

                    <div class="alert-field-grid">
                        <div class="alert-field wide">
                            <label for="al-name">Alert name</label>
                            <input id="al-name" type="text" value="${escapeHtml(e.display_name || ('SAT Secrets: ' + (tpl.label || '')))}" placeholder="Alert name">
                        </div>
                        <div class="alert-field">
                            <label for="al-operator">Trigger when</label>
                            <select id="al-operator">
                                <option value="GREATER_THAN"${operator === 'GREATER_THAN' ? ' selected' : ''}>is greater than</option>
                                <option value="GREATER_THAN_OR_EQUAL"${operator === 'GREATER_THAN_OR_EQUAL' ? ' selected' : ''}>is greater than or equal to</option>
                                <option value="EQUAL"${operator === 'EQUAL' ? ' selected' : ''}>equals</option>
                                <option value="LESS_THAN"${operator === 'LESS_THAN' ? ' selected' : ''}>is less than</option>
                                <option value="NOT_EQUAL"${operator === 'NOT_EQUAL' ? ' selected' : ''}>does not equal</option>
                            </select>
                            <div class="alert-field-hint">${escapeHtml(tpl.column || '')}</div>
                        </div>
                        <div class="alert-field">
                            <label for="al-threshold">Threshold</label>
                            <input id="al-threshold" type="number" step="any" value="${escapeHtml(String(threshold === undefined ? 0 : threshold))}">
                            <div class="alert-field-hint">${tpl.id === 'stale_scan' ? 'Hours since the last scan' : 'Number of findings'}</div>
                        </div>
                        <div class="alert-field">
                            <label for="al-schedule">Check</label>
                            <select id="al-schedule" onchange="onAlertScheduleChange()">
                                ${presets.map(p => `<option value="${escapeHtml(p.cron)}"${p.cron === cron ? ' selected' : ''}>${escapeHtml(p.label)}</option>`).join('')}
                                <option value="__custom"${cronKnown ? '' : ' selected'}>Custom cron...</option>
                            </select>
                        </div>
                        <div class="alert-field" id="al-cron-wrap" style="${cronKnown ? 'display:none;' : ''}">
                            <label for="al-cron">Quartz cron</label>
                            <input id="al-cron" type="text" value="${escapeHtml(cron)}" placeholder="0 0 8 * * ?">
                        </div>
                        <div class="alert-field wide">
                            <label for="al-subscribers">Email recipients</label>
                            <input id="al-subscribers" type="text" value="${escapeHtml(subscribers)}" placeholder="you@company.com, security@company.com">
                            <div class="alert-field-hint">Comma-separated.</div>
                        </div>
                        ${destinations.length ? `
                        <div class="alert-field wide">
                            <label for="al-destinations">Notification destinations</label>
                            <select id="al-destinations" multiple size="${Math.min(destinations.length, 4)}">
                                ${destinations.map(d => `<option value="${escapeHtml(d.id)}"${(e.destination_ids || []).includes(d.id) ? ' selected' : ''}>${escapeHtml(d.display_name)} (${escapeHtml(d.type)})</option>`).join('')}
                            </select>
                            <div class="alert-field-hint">Slack, PagerDuty or webhooks configured in this workspace.</div>
                        </div>` : ''}
                        <div class="alert-field">
                            <label for="al-retrigger">Re-notify after</label>
                            <select id="al-retrigger">
                                <option value="0"${retrigger === 0 ? ' selected' : ''}>Every check</option>
                                <option value="3600"${retrigger === 3600 ? ' selected' : ''}>1 hour</option>
                                <option value="21600"${retrigger === 21600 ? ' selected' : ''}>6 hours</option>
                                <option value="86400"${retrigger === 86400 ? ' selected' : ''}>24 hours</option>
                            </select>
                            <div class="alert-field-hint">Silences repeats while still triggered.</div>
                        </div>
                        <div class="alert-field" style="justify-content:flex-end;">
                            <label class="alert-check">
                                <input id="al-notify-ok" type="checkbox"${e.notify_on_ok ? ' checked' : ''}>
                                Also notify when resolved
                            </label>
                        </div>
                    </div>

                    <details>
                        <summary style="cursor:pointer;font-size:0.85em;color:var(--text-muted);">Query this alert runs</summary>
                        <div class="alert-sql">${escapeHtml(tpl.query || '')}</div>
                    </details>

                    <div class="alert-form-actions">
                        <span class="alert-form-error" id="al-error"></span>
                        <button class="btn btn-sm btn-ghost" onclick="closeAlertEditor()">Cancel</button>
                        <button class="btn btn-sm" id="al-save" onclick="saveAlert()">${isEdit ? 'Save changes' : 'Create alert'}</button>
                    </div>
                </div>`;
        }

        function onAlertScheduleChange() {
            const sel = document.getElementById('al-schedule');
            const wrap = document.getElementById('al-cron-wrap');
            const cronInput = document.getElementById('al-cron');
            if (!sel || !wrap) return;
            if (sel.value === '__custom') {
                wrap.style.display = '';
            } else {
                wrap.style.display = 'none';
                if (cronInput) cronInput.value = sel.value;
            }
        }

        function alertEditorPayload() {
            const sel = document.getElementById('al-schedule');
            const cronInput = document.getElementById('al-cron');
            const cron = (sel && sel.value !== '__custom') ? sel.value
                : (cronInput ? cronInput.value.trim() : '');
            const destSel = document.getElementById('al-destinations');
            return {
                template_id: alertState.selectedTemplate,
                display_name: document.getElementById('al-name').value.trim(),
                operator: document.getElementById('al-operator').value,
                threshold: document.getElementById('al-threshold').value,
                cron: cron,
                subscribers: document.getElementById('al-subscribers').value,
                destination_ids: destSel
                    ? Array.from(destSel.selectedOptions).map(o => o.value) : [],
                retrigger_seconds: document.getElementById('al-retrigger').value,
                notify_on_ok: document.getElementById('al-notify-ok').checked,
                paused: !!(alertState.editing && alertState.editing.paused),
            };
        }

        async function saveAlert() {
            const err = document.getElementById('al-error');
            const btn = document.getElementById('al-save');
            const editing = alertState.editing || {};
            const payload = alertEditorPayload();
            if (err) err.textContent = '';
            if (btn) { btn.disabled = true; btn.textContent = 'Saving...'; }
            try {
                const url = editing.id
                    ? '/api/secrets/alerts/' + encodeURIComponent(editing.id)
                    : '/api/secrets/alerts';
                const result = await fetch(url, {
                    method: editing.id ? 'PATCH' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                }).then(r => r.json());
                if (result.error) {
                    if (err) err.textContent = result.error;
                    if (btn) { btn.disabled = false; btn.textContent = editing.id ? 'Save changes' : 'Create alert'; }
                    return;
                }
                alertState.editing = null;
                alertState.selectedTemplate = null;
                await loadSecretsAlerts();
            } catch (e) {
                if (err) err.textContent = e.message;
                if (btn) { btn.disabled = false; btn.textContent = editing.id ? 'Save changes' : 'Create alert'; }
            }
        }

        async function toggleAlertPause(alertId, paused) {
            try {
                const result = await fetch('/api/secrets/alerts/' + encodeURIComponent(alertId), {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paused: paused }),
                }).then(r => r.json());
                if (result.error) { alert(result.error); return; }
                await loadSecretsAlerts();
            } catch (e) { alert(e.message); }
        }

        async function deleteAlert(alertId) {
            const found = alertState.alerts.find(a => a.id === alertId);
            const name = found ? found.display_name : 'this alert';
            if (!confirm('Delete "' + name + '"? It moves to trash and can be restored from the workspace.')) return;
            try {
                const result = await fetch('/api/secrets/alerts/' + encodeURIComponent(alertId), {
                    method: 'DELETE',
                }).then(r => r.json());
                if (result.error) { alert(result.error); return; }
                await loadSecretsAlerts();
            } catch (e) { alert(e.message); }
        }

        async function loadSecretsFindings() {
            if (!secretsFiltersLoaded) {
                // Populate filter dropdowns once from the aggregate endpoints.
                try {
                    const [ws, det] = await Promise.all([
                        fetch('/api/secrets/by-workspace').then(r => r.json()),
                        fetch('/api/secrets/by-detector').then(r => r.json()),
                    ]);
                    const wsSel = document.getElementById('sf-workspace');
                    ((ws && ws.rows) || []).forEach(r => {
                        const o = document.createElement('option');
                        o.value = r.workspace_id;
                        o.textContent = r.workspace_name || r.workspace_id;
                        wsSel.appendChild(o);
                    });
                    const detSel = document.getElementById('sf-detector');
                    ((det && det.rows) || []).forEach(r => {
                        const o = document.createElement('option');
                        o.value = r.detector_name;
                        o.textContent = r.detector_name;
                        detSel.appendChild(o);
                    });
                } catch (e) { /* filters degrade to defaults; the table still loads */ }
                const applyBtn = document.getElementById('sf-apply');
                if (applyBtn) applyBtn.addEventListener('click', runSecretsFindings);
                ['sf-workspace', 'sf-source', 'sf-detector', 'sf-verified'].forEach(id => {
                    const sel = document.getElementById(id);
                    if (sel) sel.addEventListener('change', runSecretsFindings);
                });
                secretsFiltersLoaded = true;
            }
            runSecretsFindings();
        }

        async function runSecretsFindings() {
            const container = document.getElementById('secretsfindings-results');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Loading findings...</div>';

            const p = new URLSearchParams();
            const ws = document.getElementById('sf-workspace').value;
            const src = document.getElementById('sf-source').value;
            const det = document.getElementById('sf-detector').value;
            const ver = document.getElementById('sf-verified').value;
            if (ws) p.set('workspace_id', ws);
            if (src) p.set('source_type', src);
            if (det) p.set('detector', det);
            if (ver === 'true') p.set('verified_only', 'true');

            try {
                const res = await fetch('/api/secrets/findings?' + p.toString());
                const result = await res.json();
                if (result.ready === false) {
                    showSecretsNotReady('secretsfindings-results', result.message);
                    return;
                }
                if (result.error) { showEmpty('secretsfindings-results', result.error); return; }

                const rows = result.rows || [];
                if (!rows.length) {
                    showEmpty('secretsfindings-results', 'No findings match these filters.');
                    return;
                }

                container.innerHTML = `
                    <div class="results-container">
                        <div class="results-header">
                            <div class="results-title">${result.count} finding${result.count === 1 ? '' : 's'}${result.truncated ? ' (truncated)' : ''}</div>
                            <div style="font-size:0.8em;color:var(--text-muted);">Secrets shown as SHA-256 prefixes, never plaintext</div>
                        </div>
                        <table class="data-table data-table-padded">
                            <thead><tr>
                                <th>Status</th><th>Source</th><th>Object</th><th>Location</th>
                                <th>Detector</th><th>Hash</th><th>Workspace</th><th>Scanned</th>
                            </tr></thead>
                            <tbody>
                                ${rows.map(r => `
                                    <tr>
                                        <td>${secretStatusBadge(r.verified)}</td>
                                        <td><span class="badge" style="background:rgba(148,163,184,.14);color:#cbd5e1;">${escapeHtml(r.source_type)}</span></td>
                                        <td class="truncate" style="max-width:210px;">${escapeHtml(r.object_name)}</td>
                                        <td class="mono truncate" style="max-width:290px;">${escapeHtml(r.object_path)}</td>
                                        <td style="white-space:nowrap;">${escapeHtml(r.detector_name)}</td>
                                        <td class="mono">${escapeHtml(String(r.secret_sha256 || '').slice(0, 12))}…</td>
                                        <td class="mono">${escapeHtml(r.workspace_id)}</td>
                                        <td class="nowrap-muted">${escapeHtml(String(r.scan_time || '').slice(0, 16).replace('T', ' '))}</td>
                                    </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>`;
            } catch (e) {
                showEmpty('secretsfindings-results', 'Failed to load findings: ' + e.message);
            }
        }

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

        // ── Account Denylist Builder ──────────────────────────────────────
        async function loadDenylistBuilder() {
            renderEntraRuleBuilder();       // static; no data dependency
            await loadDenylistCandidates(); // data-backed table
        }

        async function loadDenylistCandidates() {
            const container = document.getElementById('denylist-candidates-results');
            container.innerHTML = '<div class="loading">Loading inactive-user group candidates...</div>';
            try {
                const res = await fetch('/api/report/denylist-candidates');
                const result = await res.json();
                if (result.error) { showEmpty('denylist-candidates-results', result.error); return; }

                const data = result.data || [];
                if (data.length === 0) {
                    showEmpty('denylist-candidates-results',
                        'No candidate IdP groups found in the latest run. Note: with Automatic Identity Management (AIM), ' +
                        'external group memberships are resolved just-in-time and are not returned by the account SCIM API, ' +
                        'so member-based ranking may be empty even for populated groups. Use the Entra ID dynamic-group ' +
                        'rule helper below to build denylist groups.');
                    return;
                }
                const detTs = result.detection_timestamp
                    ? escapeHtml(String(result.detection_timestamp).replace('T', ' ').slice(0, 19)) + ' UTC' : 'Unknown';
                const days = result.inactive_days || '?';
                const acctScope = (result.metastores || []).map(m => ({name: m, reason: 'ok'}));
                // renderCoverageBlock escapes chip text, so pass it raw here.
                const acctLabel = result.account_id
                    ? 'Account ' + result.account_id + ' (all IdP groups)'
                    : 'Account-wide (all IdP groups)';

                let html = `
                    ${renderCoverageBlock({
                        dateTs: detTs,
                        scopeLabel: 'Accounts',
                        scopeIcon: '🏛️',
                        scanned: acctScope,
                        failed: [],
                        inReport: [acctLabel],
                        note: 'Denylist analysis is account-level over account SCIM groups. Inactive = no system.access.audit activity in ' + escapeHtml(String(days)) + ' days. Metastore shown for environment context.'
                    })}
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Candidate Groups</span>
                            <span class="results-count">${data.length} group${data.length === 1 ? '' : 's'}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">
                            <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1.4fr; gap: 8px; padding: 10px 24px; font-size: 0.75em; text-transform: uppercase; color: var(--text-muted); border-bottom: 1px solid var(--border);">
                                <div>Group</div><div>Inactive</div><div>Active</div><div>Total</div><div>Inactive %</div><div>Reason</div>
                            </div>`;
                data.forEach((c, idx) => {
                    const isLast = idx === data.length - 1;
                    const pct = (c.inactive_pct != null) ? c.inactive_pct + '%' : '';
                    const gname = escapeHtml(c.group_name || c.group_id);
                    // Group name links to the account-console group detail page.
                    const nameHtml = c.console_url
                        ? `<a href="${escapeHtml(c.console_url)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent); text-decoration: none; font-weight: 500;">${gname}</a>`
                        : `<span style="font-weight:500;">${gname}</span>`;
                    const reason = escapeHtml(c.candidate_reason || '');
                    html += `
                        <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1.4fr; gap: 8px; padding: 12px 24px; align-items: center; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                            <div style="min-width:0;"><span style="font-size:18px;">👥</span> ${nameHtml} <span style="color:#10b981;font-size:0.8em;">IdP</span></div>
                            <div style="color:#ef4444;font-weight:600;">${c.inactive_members ?? 0}</div>
                            <div style="color:#10b981;">${c.active_members ?? 0}</div>
                            <div>${c.total_members ?? 0}</div>
                            <div>${pct}</div>
                            <div style="font-size:0.8em;color:var(--text-muted);">${reason}</div>
                        </div>`;
                });
                html += `</div></div>`;
                container.innerHTML = html;
            } catch (e) {
                showEmpty('denylist-candidates-results', 'Error: ' + e.message);
            }
        }

        // Entra ID dynamic membership rule scenarios. Each builds a single
        // parenthesized clause; multiple clauses combine via a chosen operator.
        // `needs`: '' (no input), 'value' (single), or 'list' (comma-separated).
        // Escape regex-special chars in a domain for use in an Entra -match rule.
        // Domains only contain '.' as a regex metacharacter; escape it to '\.'.
        // Built via fromCharCode(92) to avoid backslash literals (which the Python
        // string layer serving this HTML would otherwise mangle).
        const _bs = String.fromCharCode(92);
        const _nl = String.fromCharCode(10);  // newline without a backslash escape (Python-string safe)
        const _escRe = s => s.split('.').join(_bs + '.');
        const ENTRA_SCENARIOS = {
            guests:         { label: 'Is a guest user', needs: '',
                              rule: () => '(user.userType -eq "Guest")' },
            members_only:   { label: 'Is a member (not guest)', needs: '',
                              rule: () => '(user.userType -eq "Member")' },
            disabled:       { label: 'Account is disabled', needs: '',
                              rule: () => '(user.accountEnabled -eq false)' },
            upn_domain:     { label: 'UPN ends with domain(s)', needs: 'list',
                              rule: v => '(' + v.map(d => `user.userPrincipalName -match ".*@${_escRe(d)}$"`).join(' -or ') + ')' },
            upn_not_domain: { label: 'UPN does NOT end with domain(s)', needs: 'list',
                              rule: v => '(' + v.map(d => `user.userPrincipalName -notMatch ".*@${_escRe(d)}$"`).join(' -and ') + ')' },
            mail_domain:    { label: 'Mail ends with domain(s)', needs: 'list',
                              rule: v => '(' + v.map(d => `user.mail -match ".*@${_escRe(d)}$"`).join(' -or ') + ')' },
            mail_not_domain:{ label: 'Mail does NOT end with domain(s)', needs: 'list',
                              rule: v => '(' + v.map(d => `user.mail -notMatch ".*@${_escRe(d)}$"`).join(' -and ') + ')' },
            dept_eq:        { label: 'Department equals', needs: 'value',
                              rule: v => `(user.department -eq "${v}")` },
            dept_ne:        { label: 'Department not equals', needs: 'value',
                              rule: v => `(user.department -ne "${v}")` },
            dept_in:        { label: 'Department in list', needs: 'list',
                              rule: v => `(user.department -in [${v.map(x => `"${x}"`).join(', ')}])` },
            company_eq:     { label: 'Company name equals', needs: 'value',
                              rule: v => `(user.companyName -eq "${v}")` },
            company_ne:     { label: 'Company name not equals', needs: 'value',
                              rule: v => `(user.companyName -ne "${v}")` },
            company_in:     { label: 'Company name in list', needs: 'list',
                              rule: v => `(user.companyName -in [${v.map(x => `"${x}"`).join(', ')}])` },
        };

        // Working set of condition rows for the builder.
        let _entraConditions = [];
        let _entraJoin = '-and';

        function renderEntraRuleBuilder() {
            _entraConditions = [{ scenario: 'guests', value: '' }];
            _entraJoin = '-and';
            const el = document.getElementById('entra-rule-builder');
            el.innerHTML = `
                <div style="background: var(--bg-input); border-radius: 12px; padding: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <span style="font-size: 0.8em; color: var(--text-secondary); text-transform: uppercase;">Combine conditions with</span>
                        <select id="entra-join" onchange="onEntraJoinChange()" style="padding: 6px 10px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.9em;">
                            <option value="-and">AND (match all)</option>
                            <option value="-or">OR (match any)</option>
                        </select>
                    </div>
                    <div id="entra-conditions"></div>
                    <button onclick="addEntraCondition()" style="margin-top: 10px; padding: 6px 12px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: var(--accent); cursor: pointer; font-size: 0.85em;">+ Add condition</button>
                    <div style="margin-top: 16px;">
                        <label style="font-size: 0.8em; color: var(--text-secondary); text-transform: uppercase;">Membership rule (paste into Entra "Dynamic membership rules")</label>
                        <div style="position: relative; margin-top: 6px;">
                            <pre id="entra-rule-output" style="background: var(--bg-dark); border: 1px solid var(--border); border-radius: 8px; padding: 14px; white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 0.9em; min-height: 48px;"></pre>
                            <button onclick="copyEntraRule()" style="position: absolute; top: 8px; right: 8px; padding: 4px 10px; background: var(--accent); border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 0.8em;">Copy</button>
                        </div>
                        <div style="font-size: 0.8em; color: var(--text-muted); margin-top: 8px;">
                            Docs: <a href="https://learn.microsoft.com/en-us/entra/identity/users/groups-dynamic-membership" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">dynamic membership rules</a> ·
                            <a href="https://learn.microsoft.com/en-us/entra/identity/users/groups-dynamic-rule-more-efficient" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">efficient rules</a>
                        </div>
                    </div>
                </div>`;
            renderEntraConditions();
        }

        function renderEntraConditions() {
            const wrap = document.getElementById('entra-conditions');
            const scenarioOpts = (sel) => Object.entries(ENTRA_SCENARIOS)
                .map(([k, s]) => `<option value="${k}" ${k === sel ? 'selected' : ''}>${s.label}</option>`).join('');
            wrap.innerHTML = _entraConditions.map((c, i) => {
                const spec = ENTRA_SCENARIOS[c.scenario];
                const needsInput = spec.needs !== '';
                const placeholder = spec.needs === 'list' ? 'comma-separated, e.g. contoso.com, fabrikam.com' : 'value';
                return `
                    <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
                        <span style="color: var(--text-muted); font-size: 0.85em; width: 44px;">${i === 0 ? 'Where' : (_entraJoin === '-and' ? 'AND' : 'OR')}</span>
                        <select onchange="updateEntraCondition(${i}, 'scenario', this.value)" style="flex: 1; min-width: 200px; padding: 8px 10px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.88em;">
                            ${scenarioOpts(c.scenario)}
                        </select>
                        <input type="text" value="${escapeHtml(c.value || '')}" oninput="updateEntraCondition(${i}, 'value', this.value)" placeholder="${placeholder}" style="flex: 2; min-width: 200px; padding: 8px 10px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.88em; ${needsInput ? '' : 'visibility: hidden;'}">
                        <button onclick="removeEntraCondition(${i})" title="Remove" style="padding: 6px 10px; background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: #ef4444; cursor: pointer; ${_entraConditions.length === 1 ? 'visibility: hidden;' : ''}">✕</button>
                    </div>`;
            }).join('');
            regenEntraRule();
        }

        function addEntraCondition() { _entraConditions.push({ scenario: 'guests', value: '' }); renderEntraConditions(); }
        function removeEntraCondition(i) { _entraConditions.splice(i, 1); renderEntraConditions(); }
        function updateEntraCondition(i, field, val) {
            _entraConditions[i][field] = val;
            if (field === 'scenario') renderEntraConditions();  // input visibility may change
            else regenEntraRule();
        }
        function onEntraJoinChange() {
            _entraJoin = document.getElementById('entra-join').value;
            renderEntraConditions();
        }

        function regenEntraRule() {
            const clauses = [];
            let incomplete = false;
            for (const c of _entraConditions) {
                const spec = ENTRA_SCENARIOS[c.scenario];
                try {
                    if (spec.needs === '') { clauses.push(spec.rule()); }
                    else {
                        const raw = (c.value || '').trim();
                        if (!raw) { incomplete = true; continue; }
                        if (spec.needs === 'list') {
                            const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
                            if (!parts.length) { incomplete = true; continue; }
                            clauses.push(spec.rule(parts));
                        } else {
                            clauses.push(spec.rule(raw));
                        }
                    }
                } catch (e) { /* skip malformed */ }
            }
            let rule;
            if (!clauses.length) rule = '// add at least one complete condition';
            else {
                rule = clauses.length === 1 ? clauses[0] : clauses.join(` ${_entraJoin} `);
                if (incomplete) rule += _nl + '// note: some conditions are missing values and were skipped';
            }
            const out = document.getElementById('entra-rule-output');
            if (out) out.textContent = rule;
        }

        function copyEntraRule() {
            const txt = document.getElementById('entra-rule-output').textContent
                .split(_nl).filter(l => !l.trim().startsWith('//')).join(_nl).trim();
            navigator.clipboard.writeText(txt).catch(() => {});
        }

        // Scope-adaptive coverage block for the SAT audit-log/SCIM tabs (Shared
        // to All Users, Privileged Non-IdP, Denylist). Rendered in the tab BODY —
        // never touches the global graph-collection header.
        //
        // cfg = {
        //   dateTs:   detection timestamp string (shown "Data Collection Date & Time"),
        //   scopeLabel: 'Accounts' | 'Metastores' | 'Workspaces' (drives the box title),
        //   scopeIcon:  emoji for the scope entities,
        //   scanned:  [{workspace/name, reason}]  (per-entity coverage; optional),
        //   failed:   [{workspace/name, reason}]  (coverage gaps w/ reason; optional),
        //   inReport: [names]                      (entities whose data appears),
        //   note:     extra one-line context (optional)
        // }
        // Collapse a long list of rendered items behind a "Show N more" toggle so
        // reports covering hundreds of workspaces don't render as a giant wall.
        function collapsibleList(items, renderItem, limit) {
            if (!items.length) return '';
            if (items.length <= limit) return items.map(renderItem).join('');
            const id = 'covmore-' + (collapsibleList._n = (collapsibleList._n || 0) + 1);
            const shown = items.slice(0, limit).map(renderItem).join('');
            const rest = items.slice(limit).map(renderItem).join('');
            const remaining = items.length - limit;
            return `${shown}`
                + `<span id="${id}" style="display:none;">${rest}</span>`
                + `<a href="javascript:void(0)" onclick="const r=document.getElementById('${id}');`
                + `const on=r.style.display==='none';r.style.display=on?'inline':'none';`
                + `this.textContent=on?'Show less':'Show ${remaining} more';" `
                + `style="display:inline-block; margin:2px 4px; font-size:0.85em; color:var(--accent);">`
                + `Show ${remaining} more</a>`;
        }

        function renderCoverageBlock(cfg) {
            const icon = cfg.scopeIcon || '🏢';
            const CHIP_LIMIT = 12;   // chips shown before collapsing the remainder
            const FAIL_LIMIT = 8;    // failed entries shown before collapsing
            const nameOf = (x) => (x && typeof x === 'object') ? (x.workspace || x.name || '') : x;
            const okChip = (x) => `<span style="display:inline-block; background:var(--bg-dark); border:1px solid var(--border); border-radius:6px; padding:2px 8px; margin:2px; font-size:0.85em;">${icon} ${escapeHtml(nameOf(x))}</span>`;
            // Failed entries render the reason inline (not hover-only) so it's fully visible.
            const failItem = (x) => `<div style="padding:4px 0; font-size:0.85em;"><span style="color:#ef4444;">${icon} ${escapeHtml(nameOf(x))}</span><span style="color:var(--text-muted);"> — ${escapeHtml(x.reason || 'not scanned')}</span></div>`;

            const scanned = cfg.scanned || [];
            const failed = cfg.failed || [];
            const inReport = cfg.inReport || [];

            // Coverage summary line — only meaningful when we have a per-entity scan.
            let coverageHtml = '';
            if (scanned.length || failed.length) {
                const okLine = `<span style="color:#10b981; font-weight:600;">✓ ${scanned.length} scanned</span>`;
                const failLine = failed.length ? ` · <span style="color:#ef4444; font-weight:600;">✗ ${failed.length} not scanned</span>` : '';
                coverageHtml = `<div style="margin-top:6px; font-size:0.9em;">${okLine}${failLine}</div>`
                    + (failed.length ? `<div style="margin-top:8px; border-top:1px solid var(--border); padding-top:6px;">${collapsibleList(failed, failItem, FAIL_LIMIT)}</div>` : '');
            }
            const inReportHtml = inReport.length
                ? `<div style="margin-top:6px;">${collapsibleList(inReport, okChip, CHIP_LIMIT)}</div>`
                : '<div style="margin-top:6px; color: var(--text-muted); font-size:0.9em;">None</div>';
            const noteHtml = cfg.note ? `<div style="margin-top:8px; font-size:0.78em; color:var(--text-muted);">${escapeHtml(cfg.note)}</div>` : '';
            const dateHtml = cfg.dateTs
                ? `<div class="stats-header-label" style="color: var(--text-secondary); font-size: 0.8em; text-transform: uppercase;">Data Collection Date &amp; Time</div>
                   <div style="margin-top:6px; font-size:0.95em;">🕒 ${escapeHtml(cfg.dateTs)}</div>` : '';

            return `
                <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; flex: 1; min-width: 240px;">
                        ${dateHtml}
                    </div>
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; flex: 2; min-width: 300px;">
                        <div class="stats-header-label" style="color: var(--text-secondary); font-size: 0.8em; text-transform: uppercase;">${escapeHtml(cfg.scopeLabel || 'Workspaces')} in this Report</div>
                        ${coverageHtml}
                        <div style="font-size:0.78em; color:var(--text-muted); margin-top:${coverageHtml ? '10px' : '6px'};">In this report${inReport.length ? ` (${inReport.length})` : ''}:</div>
                        ${inReportHtml}
                        ${noteHtml}
                    </div>
                </div>`;
        }

        async function loadPrivilegedNonIdp() {
            const container = document.getElementById('privilegednonidp-results');
            container.innerHTML = '<div class="loading">Loading privileged non-IdP identities...</div>';

            try {
                const res = await fetch('/api/report/privileged-non-idp');
                const result = await res.json();

                if (result.error) {
                    showEmpty('privilegednonidp-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                if (data.length === 0) {
                    showEmpty('privilegednonidp-results', 'No privileged non-IdP-managed identities found in the latest detection run.');
                    return;
                }

                const detTs = result.detection_timestamp
                    ? escapeHtml(String(result.detection_timestamp).replace('T', ' ').slice(0, 19)) + ' UTC'
                    : 'Unknown';

                const typeLabels = { account_admin: 'Account Admin', workspace_admin: 'Workspace Admin' };

                // Group by finding_type
                const byType = {};
                data.forEach(d => {
                    const t = d.finding_type || 'unknown';
                    if (!byType[t]) byType[t] = [];
                    byType[t].push(d);
                });

                let html = `
                    ${renderCoverageBlock({
                        dateTs: detTs,
                        scopeLabel: 'Workspaces',
                        scopeIcon: '🏢',
                        scanned: result.workspaces_scanned || [],
                        failed: result.workspaces_failed || [],
                        inReport: result.workspaces_in_report || [],
                        note: 'Account Admin is detected account-wide; Workspace Admin is resolved per-workspace via the account workspace-assignment API (coverage above).'
                    })}
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Privileged Non-IdP Summary</div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 12px; text-align: center;">
                            <div><div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${summary.total || 0}</div><div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div></div>
                            <div><div style="font-size: 1.8em; font-weight: 700; color: var(--warning);">${summary.account_admin || 0}</div><div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Acct Admin</div></div>
                            <div><div style="font-size: 1.8em; font-weight: 700; color: var(--warning);">${summary.workspace_admin || 0}</div><div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">WS Admin</div></div>
                            <div><div style="font-size: 1.8em; font-weight: 700; color: #10b981;">${summary.remediated || 0}</div><div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Remediated</div></div>
                            <div><div style="font-size: 1.8em; font-weight: 700; color: #ef4444;">${(summary.total || 0) - (summary.remediated || 0)}</div><div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Not Remediated</div></div>
                        </div>
                    </div>
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Privileged Identities</span>
                            <span class="results-count">${data.length} finding${data.length === 1 ? '' : 's'}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                // Categorize a principal_type into a display bucket.
                const categoryOf = (pt) => (pt || '').includes('Group') ? 'Groups'
                                         : (pt || '').includes('ServicePrincipal') ? 'Service Principals'
                                         : 'Users';
                const categoryEmoji = { 'Users': '👤', 'Groups': '👥', 'Service Principals': '🤖' };
                const categoryOrder = ['Users', 'Groups', 'Service Principals'];

                ['account_admin', 'workspace_admin'].forEach((type) => {
                    const items = byType[type];
                    if (!items || !items.length) return;
                    const roleLabel = typeLabels[type] || type;

                    // Role header
                    html += `
                        <div class="tree-type-group">
                            <div style="display: flex; align-items: center; gap: 12px; padding: 14px 24px; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span style="font-size: 20px;">🛡️</span>
                                <span style="font-weight: 700; flex: 1;">${roleLabel} (${items.length})</span>
                            </div>`;

                    // Split into Users / Groups / Service Principals subsections
                    const byCat = { 'Users': [], 'Groups': [], 'Service Principals': [] };
                    items.forEach(it => byCat[categoryOf(it.principal_type)].push(it));

                    categoryOrder.forEach((cat) => {
                        const catItems = byCat[cat];
                        if (!catItems.length) return;
                        const secId = 'privnonidp-' + type + '-' + cat.replace(/\s+/g, '');
                        html += `
                            <div class="tree-type-header" onclick="toggleTreeSection('${secId}')" style="display: flex; align-items: center; gap: 12px; padding: 12px 24px 12px 40px; cursor: pointer; border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${secId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 16px;">${categoryEmoji[cat]}</span>
                                <span style="font-weight: 600; flex: 1;">${cat} (${catItems.length})</span>
                            </div>
                            <div class="tree-type-content" id="${secId}-content" style="display: none;">`;

                        catItems.forEach((item, idx) => {
                            const isLast = idx === catItems.length - 1;
                            const who = formatPrincipalName(item.principal_name, item.principal_email || item.application_id, null, item.principal_id);
                            // Link the name to the account console for investigation.
                            const nameHtml = item.console_url
                                ? `<a href="${escapeHtml(item.console_url)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent); text-decoration: none;">${who}</a>`
                                : who;
                            const roleBadge = `<span style="color: var(--warning); font-weight: 600;">${roleLabel}</span>`;
                            const idpBadge = item.is_idp_managed
                                ? ' <span style="color: #10b981;">· IdP-managed</span>'
                                : ' <span style="color: #ef4444;">· ⚠ Non-IdP</span>';
                            const remBadge = item.auto_remediated
                                ? ' <span style="color: #10b981;">· ✓ Remediated</span>'
                                : ' <span style="color: #ef4444;">· Not Remediated</span>';
                            const wsHtml = (item.workspace_name || item.workspace_id)
                                ? `<span style="margin-left: 10px;">🏢 Workspace: ${escapeHtml(item.workspace_name || item.workspace_id)}</span>` : '';

                            html += `
                                <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 64px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                    <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                    <div style="flex: 1; min-width: 0;">
                                        <div style="font-weight: 500; word-break: break-all;">${categoryEmoji[cat]} ${nameHtml}</div>
                                        <div style="font-size: 0.8em; color: var(--text-muted); margin-top: 4px;">${wsHtml}</div>
                                    </div>
                                    <div style="font-size: 0.8em; white-space: nowrap;">${roleBadge}${idpBadge}${remBadge}</div>
                                </div>`;
                        });
                        html += `</div>`;
                    });

                    html += `</div>`;
                });

                html += `</div></div>`;
                container.innerHTML = html;
            } catch (e) {
                showEmpty('privilegednonidp-results', 'Error: ' + e.message);
            }
        }

        // Load Orphaned Resources Report
        async function loadSharedToAccount() {
            const container = document.getElementById('sharedtoaccount-results');
            container.innerHTML = '<div class="loading">Loading shared-to-account-users findings...</div>';

            try {
                const res = await fetch('/api/report/shared-to-account');
                const result = await res.json();

                if (result.error) {
                    showEmpty('sharedtoaccount-results', result.error);
                    return;
                }

                const data = result.data || [];
                const summary = result.summary || {};

                if (data.length === 0) {
                    showEmpty('sharedtoaccount-results', 'No resources shared to all account users were found in the latest detection run.');
                    return;
                }

                const typeLabels = { dashboards: 'Dashboards', genie: 'Genie Agents', apps: 'Apps' };
                const typeEmoji  = { dashboards: '📊', genie: '💬', apps: '🧩' };

                // Group by resource_type
                const byType = {};
                data.forEach(d => {
                    const t = d.resource_type || 'unknown';
                    if (!byType[t]) byType[t] = [];
                    byType[t].push(d);
                });

                // Header: detection run date/time + metastore scope + workspaces where shares were found.
                const detTs = result.detection_timestamp
                    ? escapeHtml(String(result.detection_timestamp).replace('T', ' ').slice(0, 19)) + ' UTC'
                    : 'Unknown';
                const metastores = (result.metastores || []).map(m => ({name: m, reason: 'ok'}));

                let html = `
                    ${renderCoverageBlock({
                        dateTs: detTs,
                        scopeLabel: 'Metastores',
                        scopeIcon: '🗄️',
                        scanned: metastores,
                        failed: [],
                        inReport: result.workspaces || [],
                        note: 'Detection is account-wide over the audit log (system.access.audit) of the metastore above; the entities in this report are the workspaces where shares were found.'
                    })}
                    <div style="background: var(--bg-input); border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;">
                        <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-secondary);">Shared to All Account Users</div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 12px; text-align: center;">
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: var(--accent);">${summary.total || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Total</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #ef4444;">${summary.outstanding || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Not Remediated</div>
                            </div>
                            <div>
                                <div style="font-size: 1.8em; font-weight: 700; color: #10b981;">${summary.remediated || 0}</div>
                                <div style="font-size: 0.75em; color: var(--text-muted); text-transform: uppercase;">Remediated</div>
                            </div>
                        </div>
                    </div>
                    <div class="results-container">
                        <div class="results-header">
                            <span class="results-title">Shared Resources</span>
                            <span class="results-count">${data.length} finding${data.length === 1 ? '' : 's'}</span>
                        </div>
                        <div class="results-body" style="padding: 0;">`;

                const typeOrder = ['dashboards', 'genie', 'apps'];
                const sortedTypes = Object.keys(byType).sort((a, b) => {
                    const aIdx = typeOrder.indexOf(a), bIdx = typeOrder.indexOf(b);
                    if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
                    if (aIdx === -1) return 1;
                    if (bIdx === -1) return -1;
                    return aIdx - bIdx;
                });

                sortedTypes.forEach((type) => {
                    const items = byType[type];
                    const typeId = 'sharedtoaccount-type-' + type.replace(/[^a-zA-Z]/g, '');
                    const label = typeLabels[type] || type;

                    html += `
                        <div class="tree-type-group">
                            <div class="tree-type-header" onclick="toggleTreeSection('${typeId}')" style="display: flex; align-items: center; gap: 12px; padding: 16px 24px; cursor: pointer; background: var(--bg-input); border-bottom: 1px solid var(--border);">
                                <span class="tree-toggle" id="${typeId}-toggle" style="color: var(--text-muted); font-size: 12px;">▶</span>
                                <span style="font-size: 20px;">${typeEmoji[type] || '📄'}</span>
                                <span style="font-weight: 600; flex: 1;">${label} (${items.length})</span>
                            </div>
                            <div class="tree-type-content" id="${typeId}-content" style="display: none;">`;

                    items.forEach((item, idx) => {
                        const isLast = idx === items.length - 1;
                        const name = escapeHtml(item.resource_id || 'unknown');
                        // Format sharer like other tabs: 👤 Full Name (email)
                        const sharedBy = formatPrincipalName(item.shared_by_display_name, item.shared_by, null, null);
                        const wsName = item.workspace_name || item.workspace_id || '';
                        const when = escapeHtml((item.event_time || '').replace('T', ' ').slice(0, 19));
                        const url = item.resource_url || '';

                        const statusBadge = item.auto_remediated
                            ? '<span style="color: #10b981; font-weight: 600;">✓ Remediated</span>'
                            : '<span style="color: #ef4444; font-weight: 600;">⚠ Not Remediated</span>';

                        const nameHtml = url
                            ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="color: var(--accent); text-decoration: none;">${name}</a>`
                            : name;

                        const wsHtml = wsName
                            ? `<span style="margin-left: 10px;">🏢 Workspace: ${escapeHtml(wsName)}</span>` : '';
                        const whenHtml = when ? `<span style="margin-left: 10px;">🕒 ${when}</span>` : '';
                        const sharedToHtml = item.group_name
                            ? `<span style="margin-left: 10px;">👥 Shared to: ${escapeHtml(item.group_name)}</span>` : '';

                        html += `
                            <div class="tree-resource" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px 24px 12px 56px; border-bottom: ${isLast ? 'none' : '1px solid var(--border)'};">
                                <span style="color: var(--text-muted);">${isLast ? '└─' : '├─'}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="font-weight: 500; word-break: break-all;">${nameHtml}</div>
                                    <div style="font-size: 0.8em; color: var(--text-muted); margin-top: 4px;">
                                        <span>👤 Shared by ${sharedBy}</span>${sharedToHtml}${wsHtml}${whenHtml}
                                    </div>
                                </div>
                                <div style="font-size: 0.8em; white-space: nowrap;">${statusBadge}</div>
                            </div>`;
                    });

                    html += `</div></div>`;
                });

                html += `</div></div>`;
                container.innerHTML = html;
            } catch (e) {
                showEmpty('sharedtoaccount-results', 'Error: ' + e.message);
            }
        }

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
                        // displayName is already HTML-escaped via formatPrincipalName.
                        // Escape the option value separately to prevent attribute injection.
                        html += `<option value="${escapeHtml(p.email || p.name || p.id)}">${displayName}</option>`;
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

        // escapeHtml is defined earlier — see top of inline <script>.

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
    return '{"status":"healthy","service":"security-analysis-tool"}'


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
        logger.debug(f"/api/runs called")
        logger.debug(f"CATALOG={CATALOG}, SCHEMA={SCHEMA}")
        logger.debug(f"METADATA_TABLE={METADATA_TABLE}")

        runs = get_available_runs(limit=10)
        logger.debug(f"get_available_runs returned {len(runs) if runs else 0} runs")

        latest_run = get_latest_run_id()
        logger.debug(f"latest_run_id={latest_run}")

        return jsonify({
            'success': True,
            'runs': runs,
            'current_run_id': latest_run
        })
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'success': False, 'error': 'internal error',
                        'request_id': req_id, 'runs': []}), 500


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
        
        # Build LIKE patterns from user input. `query` is bound via params
        # below — string interpolation only happens server-side, against
        # the bound value, so the user can't inject SQL.
        search_pattern = f"%{query}%"
        starts_with_pattern = f"{query}%"

        # Search - filter to only principals and current run_id
        # Prioritize results that START with the query
        sql = f"""
            SELECT DISTINCT id, name, node_type, display_name, email
            FROM {VERTICES_TABLE}
            WHERE run_id = :run_id
            AND node_type IN ('User', 'Group', 'ServicePrincipal', 'AccountUser', 'AccountGroup', 'AccountServicePrincipal')
            AND (
                LOWER(COALESCE(name, '')) LIKE LOWER(:search_pattern)
                OR LOWER(COALESCE(display_name, '')) LIKE LOWER(:search_pattern)
                OR LOWER(COALESCE(email, '')) LIKE LOWER(:search_pattern)
            )
            ORDER BY
                CASE
                    WHEN LOWER(name) LIKE LOWER(:starts_with_pattern) THEN 1
                    WHEN LOWER(display_name) LIKE LOWER(:starts_with_pattern) THEN 2
                    WHEN LOWER(email) LIKE LOWER(:starts_with_pattern) THEN 3
                    ELSE 4
                END,
                name
            LIMIT {limit}
        """

        results = exec_query_df(sql, params={
            "run_id": run_id,
            "search_pattern": search_pattern,
            "starts_with_pattern": starts_with_pattern,
        })
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
        
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'error': 'internal error', 'request_id': req_id}), 500


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
        
        search_pattern = f"%{query}%"
        starts_with_pattern = f"{query}%"

        # Search - filter to only resources and current run_id
        # Prioritize results that START with the query
        sql = f"""
            SELECT DISTINCT id, name, node_type
            FROM {VERTICES_TABLE}
            WHERE run_id = :run_id
            AND node_type IN ('Catalog', 'Schema', 'Table', 'View', 'Volume', 'Function',
                              'Cluster', 'ClusterPolicy', 'Job', 'Warehouse', 'ServingEndpoint',
                              'SecretScope', 'Metastore')
            AND LOWER(COALESCE(name, '')) LIKE LOWER(:search_pattern)
            ORDER BY
                CASE
                    WHEN LOWER(name) LIKE LOWER(:starts_with_pattern) THEN 1
                    ELSE 2
                END,
                node_type,
                name
            LIMIT {limit}
        """

        results = exec_query_df(sql, params={
            "run_id": run_id,
            "search_pattern": search_pattern,
            "starts_with_pattern": starts_with_pattern,
        })
        resources = []
        
        for row in results:
            resource = {
                'identifier': row.get('id', ''),  # Use ID as identifier for exact matching
                'name': row.get('name', ''),
                'type': row.get('node_type', '')
            }
            resources.append(resource)
        
        return jsonify({'resources': resources})
        
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'error': 'internal error', 'request_id': req_id}), 500


@app.route('/api/browse-resources-by-type', methods=['POST'])
def api_browse_resources_by_type():
    """Get all resources of a specific type"""
    try:
        data = request.get_json() or {}
        resource_type = data.get('resource_type', '')
        run_id = get_current_run_id()
        
        if not resource_type:
            return jsonify({'success': False, 'message': 'Resource type is required'})
        
        if not run_id:
            return jsonify({'success': False, 'message': 'No data collection runs available'})

        # Query all resources of the specified type — bound parameters only,
        # no string interpolation of user input.
        sql = f"""
            SELECT id, name, owner
            FROM {VERTICES_TABLE}
            WHERE run_id = :run_id
            AND node_type = :resource_type
            ORDER BY name
        """

        results = exec_query_df(sql, params={
            "run_id": run_id,
            "resource_type": resource_type,
        })
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
        
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'success': False, 'message': 'internal error',
                        'request_id': req_id}), 500


@app.route('/api/browse-principals-by-type', methods=['POST'])
def api_browse_principals_by_type():
    """Get all principals of a specific type"""
    try:
        data = request.get_json() or {}
        principal_type = data.get('principal_type', '')
        run_id = get_current_run_id()
        
        if not principal_type:
            return jsonify({'success': False, 'message': 'Principal type is required'})
        
        if not run_id:
            return jsonify({'success': False, 'message': 'No data collection runs available'})

        # Map to include both Account and non-Account types
        if principal_type == 'User':
            type_filter = ['User', 'AccountUser']
        elif principal_type == 'Group':
            type_filter = ['Group', 'AccountGroup']
        elif principal_type == 'ServicePrincipal':
            type_filter = ['ServicePrincipal', 'AccountServicePrincipal']
        else:
            type_filter = [principal_type]

        # Build a bound IN list — one named param per element, no string
        # interpolation of user input.
        placeholders = ", ".join(f":t{i}" for i in range(len(type_filter)))
        sql_params = {"run_id": run_id}
        for i, t in enumerate(type_filter):
            sql_params[f"t{i}"] = t

        sql = f"""
            SELECT id, name, display_name, email
            FROM {VERTICES_TABLE}
            WHERE run_id = :run_id
            AND node_type IN ({placeholders})
            ORDER BY COALESCE(display_name, name, email, id)
        """

        results = exec_query_df(sql, params=sql_params)
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
        
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'success': False, 'message': 'internal error',
                        'request_id': req_id}), 500


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
        except NoAccessError:
            raise
        except Exception as e:
            logger.exception("loading collection metadata")
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
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'error': 'internal error', 'request_id': req_id}), 500


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
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({'success': False, 'error': 'internal error',
                        'request_id': req_id}), 500


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
    implicit_grants AS (
        -- Grants whose grantee has no vertex row. Databricks implicit groups
        -- ('account users', '_workspace_users_<workspace_id>') are only ever edge
        -- sources, yet they include every user in the account or workspace — so a
        -- grant to one is effectively public. The other CTEs inner-join the
        -- grantee to a vertex and therefore miss these entirely.
        SELECT
            e.src as principal_id,
            e.src as principal_name,
            'ImplicitGroup' as principal_type,
            CAST(NULL AS STRING) as principal_email,
            e.permission_level,
            'Direct' as grant_type,
            CAST(NULL AS STRING) as inheritance_path
        FROM {EDGES_TABLE} e
        LEFT JOIN {VERTICES_TABLE} v
               ON (e.src = v.id OR e.src = v.email OR e.src = v.name)
              AND v.run_id = '{run_id}'
        WHERE e.run_id = '{run_id}'
          AND e.dst = '{sanitize(r_id)}'
          AND e.permission_level IS NOT NULL
          AND v.id IS NULL
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
        SELECT * FROM implicit_grants
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

    logger.debug(f"Principal found: id={p_id}, email={p_email}, name={p_name}")
    logger.debug(f"ID variants to search: {p_id_variants}")

    # Bind resource_type as a named SQL parameter rather than interpolating
    # the user-supplied value — eliminates the only direct-POST-input
    # site in this handler that would otherwise hit a sanitize-only path.
    type_filter = "AND v.node_type = :resource_type" if resource_type and resource_type != 'All' else ""

    # Build SQL condition for all principal ID variants
    id_conditions = ' OR '.join([f"e.src = '{sanitize(vid)}'" for vid in p_id_variants])
    if p_email:
        id_conditions += f" OR e.src = '{sanitize(p_email)}'"
    if p_name:
        id_conditions += f" OR e.src = '{sanitize(p_name)}'"

    logger.debug(f"ID conditions for groups query: {id_conditions}")

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

    logger.debug(f"Found {len(group_ids)} groups for principal {p_id}: {group_names}")
    logger.debug(f"Groups query returned {len(groups_result)} rows")

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

    logger.debug(f"path_cases_list has {len(path_cases_list)} entries")

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

    logger.debug(f"Executing main query...")
    main_query_params = {}
    if resource_type and resource_type != 'All':
        main_query_params["resource_type"] = resource_type
    results = exec_query_df(query, params=main_query_params or None)
    logger.debug(f"Main query returned {len(results)} results")

    # Debug: Print first few results if any
    if results:
        logger.debug(f"First result: {results[0]}")
    else:
        logger.debug(f"No results! Trying simplified direct_access query...")
        # Try a simple query to test
        test_query = f"""
        SELECT COUNT(*) as cnt FROM {EDGES_TABLE} e
        WHERE (e.src = '{sanitize(p_id)}' OR e.src = '{sanitize(p_email)}' OR e.src = '{sanitize(p_name)}')
          AND e.permission_level IS NOT NULL
        """
        test_result = exec_query_df(test_query)
        logger.debug(f"Test query (edges with permission): {test_result}")

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
    except NoAccessError:
        raise
    except Exception as e:
        logger.debug(f"  Warning: Error finding indirect paths: {e}")
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

    logger.debug(f"  Found {len(indirect_paths)} indirect escalation paths")
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

    logger.debug("=" * 60)
    logger.debug(f"Finding escalation paths for: {p_name}")
    logger.debug(f"Principal ID: {p_id}")
    logger.debug(f"Principal email: {principal.get('email')}")

    # Build graph
    graph, node_info, edge_info = build_graph_from_db(run_id)
    total_edges = sum(len(v) for v in graph.values())
    logger.debug(f"Built graph with {len(graph)} nodes and {total_edges} edges")

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
            logger.debug(f"Found additional node with same email: {nid} ({ndata.get('node_type')})")
            continue
        # Match by name/display_name (for users with same identity)
        node_name = ndata.get('name', '').lower()
        node_display = (ndata.get('display_name') or '').lower()
        if ndata.get('node_type') in ('User', 'AccountUser') and p_email:
            # Check if name matches email prefix
            email_prefix = p_email.split('@')[0].lower() if '@' in p_email else ''
            if email_prefix and (email_prefix in node_name or email_prefix in node_display):
                all_principal_ids.append(nid)
                logger.debug(f"Found additional node with matching name: {nid} ({ndata.get('node_type')}) - name: {ndata.get('name')}")

    logger.debug(f"All principal IDs to search from: {all_principal_ids}")

    # Check neighbors for all principal IDs
    total_neighbors = []
    for pid in all_principal_ids:
        if pid in graph:
            neighbors = graph[pid]
            logger.debug(f"Principal {pid} has {len(neighbors)} direct neighbors")
            for n in neighbors[:3]:
                n_info = node_info.get(n, {})
                e_info = edge_info.get((pid, n), {})
                logger.debug(f"  -> {n}: {n_info.get('name')} ({n_info.get('node_type')}) via {e_info.get('relationship')}")
            total_neighbors.extend(neighbors)

    # Debug: Show some MemberOf edges
    logger.debug(f"Sample MemberOf edges:")
    memberof_count = 0
    for (src, dst), edata in edge_info.items():
        if edata.get('relationship') == 'MemberOf':
            memberof_count += 1
            if memberof_count <= 3:
                src_info = node_info.get(src, {})
                dst_info = node_info.get(dst, {})
                logger.debug(f"  {src} ({src_info.get('node_type')}) -> {dst} ({dst_info.get('node_type')})")
    logger.debug(f"Total MemberOf edges: {memberof_count}")

    # Get privileged targets (admin groups, catalogs, schemas, metastores)
    privileged_df = identify_privileged_targets_query(run_id)
    logger.debug(f"Found {len(privileged_df)} privileged target rows")

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
    logger.debug(f"Unique privileged target IDs: {len(privileged_ids)}")

    # Check if any targets are in graph
    targets_in_graph = [t for t in privileged_ids if t in graph]
    logger.debug(f"Targets that exist in graph: {len(targets_in_graph)}")

    # Show admin groups specifically
    logger.debug(f"Admin group targets:")
    for tid, roles in privileged_map.items():
        if any('Admin' in r.get('role', '') for r in roles):
            t_info = node_info.get(tid, {})
            in_graph = "YES" if tid in graph else "NO"
            logger.debug(f"  {tid}: {t_info.get('name')} - in graph: {in_graph}")
            if tid in graph:
                # Check if reachable from principal
                logger.debug(f"    Neighbors of this target: {len(graph.get(tid, []))}")

    logger.debug("=" * 60)

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
                logger.debug(f"Found direct AccountAdmin edge: {pid} -> {dst}")
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

    logger.debug(f"Found {len(direct_admin_paths)} direct Account Admin paths")

    # Find all GROUP MEMBERSHIP paths from ALL principal IDs
    raw_paths = []
    for pid in all_principal_ids:
        logger.debug(f"Searching group membership paths from: {pid}")
        paths_from_pid = find_all_paths_bfs(graph, node_info, edge_info, pid, privileged_ids, max_depth, membership_only=True)
        logger.debug(f"  Found {len(paths_from_pid)} paths from {pid}")
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
    logger.debug("Searching for indirect escalation paths...")
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
        run_id = get_current_run_id()
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

        logger.debug("=" * 60)
        logger.debug(f"Finding impersonation paths")
        logger.debug(f"Source: {source_name} ({source_principal.get('node_type')})")
        logger.debug(f"Target: {target_name} ({target_principal.get('node_type')})")

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

        logger.debug(f"Source IDs: {source_ids}")
        logger.debug(f"Target IDs: {target_ids}")

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

        logger.debug(f"Found {len(all_paths)} paths")

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

    except NoAccessError:
        raise
    except NoAccessError:
        # Surface to the Flask errorhandler as the friendly 403 banner.
        raise
    except Exception:
        req_id = uuid.uuid4().hex[:8]
        logger.exception("%s failed (req=%s)", request.path, req_id)
        return jsonify({
            'success': False,
            'message': 'internal error',
            'request_id': req_id,
            'paths': []
        }), 500


@app.route('/api/principals-list')
def api_principals_list():
    """Get list of principals for dropdown selection"""
    run_id = get_current_run_id()
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
    run_id = get_current_run_id()
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
    run_id = get_current_run_id()
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


@app.route('/api/report/shared-to-account')
def report_shared_to_account():
    """Resources shared with the built-in 'account users' group.

    Reads the latest snapshot from brickhound_shared_to_account, which is
    populated by the SAT shared-to-account-users detection notebook/job
    (notebooks/brickhound/05_share_to_account.py). This endpoint is read-only;
    remediation happens only in the notebook/job which holds SP credentials.
    """
    # This report has its own run_id (per detection run), independent of the
    # graph collection run_id. Query runs as the calling user (OBO), so Unity
    # Catalog enforces their grants on the findings table.
    query = f"""
    WITH latest AS (
        SELECT MAX(run_id) AS run_id FROM {SHARED_TO_ACCOUNT_TABLE}
    )
    SELECT
        s.resource_type,
        s.resource_id,
        s.workspace_id,
        s.workspace_name,
        s.resource_url,
        s.shared_by,
        s.shared_by_display_name,
        s.permission,
        s.group_name,
        CAST(s.event_time AS STRING)          AS event_time,
        CAST(s.detection_timestamp AS STRING) AS detection_timestamp,
        s.auto_remediated
    FROM {SHARED_TO_ACCOUNT_TABLE} s
    JOIN latest l ON s.run_id = l.run_id
    ORDER BY s.event_time DESC
    """

    try:
        results = exec_query_df(query)
    except Exception as e:
        # Table absent (job never run) or no read grant — surface a friendly hint.
        logger.warning("shared-to-account report query failed: %s", e)
        return jsonify({
            'error': (
                'No shared-to-account-users data available yet. Run the '
                '"SAT Permissions Analysis - Shared to Account Users" job (or the '
                'notebooks/brickhound/05_share_to_account.py notebook) to populate it.'
            )
        })

    # Statement Execution returns booleans as strings ('true'/'false'); normalize.
    for r in results:
        r['auto_remediated'] = _truthy(r.get('auto_remediated'))
    remediated = sum(1 for r in results if r['auto_remediated'])
    outstanding = len(results) - remediated

    # Header context: detection run timestamp + the distinct workspaces where
    # shares were found (in-report). Scope = the metastore the system tables
    # (system.access.audit) are read from, since detection is account-wide over
    # that metastore rather than a per-workspace scan.
    detection_timestamp = results[0]['detection_timestamp'] if results else None
    workspaces = sorted({
        (r.get('workspace_name') or r.get('workspace_id') or '')
        for r in results if (r.get('workspace_name') or r.get('workspace_id'))
    })
    metastores = []
    try:
        rows = exec_query_df("SELECT current_metastore() AS m")
        if rows and rows[0].get('m'):
            metastores = [rows[0]['m']]
    except Exception:
        metastores = []

    return jsonify({
        'success': True,
        'summary': {
            'total': len(results),
            'outstanding': outstanding,
            'remediated': remediated,
        },
        'metastores': metastores,
        'detection_timestamp': detection_timestamp,
        'workspaces': workspaces,
        'data': results,
    })


@app.route('/api/report/privileged-non-idp')
def report_privileged_non_idp():
    """Privileged identities that are not IdP-managed.

    Reads the latest snapshot from brickhound_privileged_non_idp, populated by
    notebooks/brickhound/06_privileged_non_idp_identities.py. Read-only;
    remediation happens in the notebook/job (which holds SP credentials).
    """
    query = f"""
    WITH latest AS (
        SELECT MAX(run_id) AS run_id FROM {PRIVILEGED_NON_IDP_TABLE}
    )
    SELECT
        p.finding_type,
        p.principal_type,
        p.principal_id,
        p.principal_name,
        p.principal_email,
        p.application_id,
        p.is_idp_managed,
        p.scope,
        p.workspace_id,
        p.workspace_name,
        p.console_url,
        CAST(p.detection_timestamp AS STRING) AS detection_timestamp,
        p.auto_remediated
    FROM {PRIVILEGED_NON_IDP_TABLE} p
    JOIN latest l ON p.run_id = l.run_id
    ORDER BY p.finding_type, p.is_idp_managed, p.principal_name
    """

    try:
        results = exec_query_df(query)
    except Exception as e:
        logger.warning("privileged-non-idp report query failed: %s", e)
        return jsonify({
            'error': (
                'No privileged-non-IdP data available yet. Run the '
                '"SAT Permissions Analysis - Privileged Non-IdP Identities" job (or the '
                'notebooks/brickhound/06_privileged_non_idp_identities.py notebook) to populate it.'
            )
        })

    # Normalize boolean-ish string cells to real bools for the JS layer too,
    # so client-side conditionals (item.is_idp_managed) behave correctly.
    for r in results:
        r['is_idp_managed'] = _truthy(r.get('is_idp_managed'))
        r['auto_remediated'] = _truthy(r.get('auto_remediated'))

    non_idp = sum(1 for r in results if not r['is_idp_managed'])
    account_admin = sum(1 for r in results if r.get('finding_type') == 'account_admin')
    workspace_admin = sum(1 for r in results if r.get('finding_type') == 'workspace_admin')
    remediated = sum(1 for r in results if r['auto_remediated'])

    detection_timestamp = results[0]['detection_timestamp'] if results else None

    # workspaces_scanned / workspaces_failed are large JSON blobs stored
    # identically on every row (workspace-admin coverage), so we fetch them from
    # a single row separately. Selecting them in the main query would multiply
    # the blob by the row count and blow past the Statement Execution 25 MB
    # inline result limit, which the endpoint would surface as a false "no data".
    cov_rows = exec_query_df(f"""
        WITH latest AS (
            SELECT MAX(run_id) AS run_id FROM {PRIVILEGED_NON_IDP_TABLE}
        )
        SELECT p.workspaces_scanned, p.workspaces_failed
        FROM {PRIVILEGED_NON_IDP_TABLE} p
        JOIN latest l ON p.run_id = l.run_id
        LIMIT 1
    """)

    def _cov(col):
        if cov_rows and cov_rows[0].get(col):
            try:
                items = json.loads(cov_rows[0][col])
                # tolerate legacy plain-string entries
                return [x if isinstance(x, dict) else {'workspace': str(x), 'reason': 'ok'} for x in items]
            except Exception:
                return []
        return []
    scanned = _cov('workspaces_scanned')
    failed = _cov('workspaces_failed')

    # "Workspaces in this report" = distinct workspaces whose findings appear
    # (workspace-admin findings carry a workspace_name; account-level ones don't).
    in_report = sorted({r['workspace_name'] for r in results
                        if r.get('workspace_name')})

    return jsonify({
        'success': True,
        'summary': {
            'total': len(results),
            'non_idp': non_idp,
            'account_admin': account_admin,
            'workspace_admin': workspace_admin,
            'remediated': remediated,
        },
        'detection_timestamp': detection_timestamp,
        'workspaces_scanned': scanned,
        'workspaces_failed': failed,
        'workspaces_in_report': in_report,
        'data': results,
    })


@app.route('/api/report/denylist-candidates')
def report_denylist_candidates():
    """Account groups ranked by inactive-member count (denylist candidates).

    Reads the latest snapshot from brickhound_denylist_candidates, populated by
    notebooks/brickhound/07_denylist_candidates.py. Read-only.
    """
    query = f"""
    WITH latest AS (
        SELECT MAX(run_id) AS run_id FROM {DENYLIST_CANDIDATES_TABLE}
    )
    SELECT
        c.group_id,
        c.group_name,
        c.is_idp_managed,
        c.total_members,
        c.inactive_members,
        c.active_members,
        c.inactive_pct,
        c.inactive_days,
        c.candidate_reason,
        c.console_url,
        CAST(c.detection_timestamp AS STRING) AS detection_timestamp
    FROM {DENYLIST_CANDIDATES_TABLE} c
    JOIN latest l ON c.run_id = l.run_id
    ORDER BY c.inactive_members DESC, c.inactive_pct DESC
    """

    try:
        results = exec_query_df(query)
    except Exception as e:
        logger.warning("denylist-candidates report query failed: %s", e)
        return jsonify({
            'error': (
                'No denylist-candidate data available yet. Run the '
                '"SAT Permissions Analysis - Denylist Candidates" job (or the '
                'notebooks/brickhound/07_denylist_candidates.py notebook) to populate it.'
            )
        })

    # Statement Execution returns everything as strings; normalize for the JS layer.
    for r in results:
        r['is_idp_managed'] = _truthy(r.get('is_idp_managed'))

    detection_timestamp = results[0]['detection_timestamp'] if results else None
    inactive_days = results[0]['inactive_days'] if results else None
    # Denylist analysis is account-level (account SCIM groups). Surface the
    # metastore for environment context.
    metastores = []
    try:
        rows = exec_query_df("SELECT current_metastore() AS m")
        if rows and rows[0].get('m'):
            metastores = [rows[0]['m']]
    except Exception:
        metastores = []

    # The account id is embedded in each group's console deep link
    # (…/user-management/groups/{id}?account_id={acct}); pull it from the first
    # row so the coverage block can name the account this report covers.
    account_id = None
    if results and results[0].get('console_url'):
        try:
            from urllib.parse import urlparse, parse_qs
            account_id = parse_qs(urlparse(results[0]['console_url']).query).get('account_id', [None])[0]
        except Exception:
            account_id = None

    return jsonify({
        'success': True,
        'summary': {
            'total_groups': len(results),
            'total_inactive': sum(int(r.get('inactive_members') or 0) for r in results),
        },
        'detection_timestamp': detection_timestamp,
        'inactive_days': inactive_days,
        'metastores': metastores,
        'account_id': account_id,
        'data': results,
    })


@app.route('/api/report/overprivileged')
def report_overprivileged_principals():
    """
    Find principals with excessive permissions.
    Identifies users with ALL PRIVILEGES on multiple catalogs or MANAGE on many resources.
    """
    run_id = get_current_run_id()
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
    run_id = get_current_run_id()
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
    run_id = get_current_run_id()
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
    run_id = get_current_run_id()
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
    except NoAccessError:
        raise
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


# ---------------------------------------------------------------------------
# Secret scanning
#
# Reads notebooks_secret_scan_results and clusters_secret_scan_results, written
# by the SAT secret scanner job. Each scan gets a run_id; these views report the
# latest completed run per workspace.
#
# A row with secret_sha256 IS NULL and secrets_found = 0 is a tracking marker
# meaning "this workspace was scanned and was clean" — not a finding. Every
# query filters those out of finding counts while still using them to tell
# "scanned clean" apart from "never scanned".
#
# secrets_found is deliberately never SUMmed: it repeats the per-object count on
# every row for that object, so summing over-counts. Rows are counted instead.
# ---------------------------------------------------------------------------

NOTEBOOK_SECRETS_TABLE = f"`{CATALOG}`.`{SCHEMA}`.notebooks_secret_scan_results"
CLUSTER_SECRETS_TABLE = f"`{CATALOG}`.`{SCHEMA}`.clusters_secret_scan_results"

_SECRETS_NOT_READY = (
    'No secret scan results yet. The SAT Secrets Scanner job populates these '
    'tables — it runs on a schedule after installation, and can also be '
    'triggered from the Jobs UI.'
)


def _secrets_table_present(table_name):
    """True if a scan table exists in the SAT schema.

    Checked per request rather than cached at import so a first scan becomes
    visible without restarting the app.
    """
    try:
        rows = exec_query_df(
            f"SHOW TABLES IN `{CATALOG}`.`{SCHEMA}` LIKE '{table_name}'"
        )
        return bool(rows)
    except NoAccessError:
        raise
    except Exception:
        logger.info("secret scan table check failed for %s", table_name, exc_info=True)
        return False


def _secrets_sources():
    """Which scan tables exist: (notebooks, clusters)."""
    return (
        _secrets_table_present('notebooks_secret_scan_results'),
        _secrets_table_present('clusters_secret_scan_results'),
    )


def _latest_runs_cte(has_nb, has_cl):
    """Newest run_id per workspace across whichever scan tables exist."""
    parts = []
    if has_nb:
        parts.append(f"SELECT workspace_id, run_id FROM {NOTEBOOK_SECRETS_TABLE}")
    if has_cl:
        parts.append(f"SELECT workspace_id, run_id FROM {CLUSTER_SECRETS_TABLE}")
    union = "\n        UNION ALL\n        ".join(parts)
    return f"""latest_runs AS (
        SELECT workspace_id, MAX(run_id) AS latest_run_id
        FROM (
        {union}
        )
        GROUP BY workspace_id
    )"""


def _findings_cte(has_nb, has_cl):
    """Normalise both scan tables into one shape so views treat them alike."""
    parts = []
    if has_nb:
        parts.append(f"""
        SELECT 'notebook' AS source_type, s.workspace_id, s.run_id,
               s.notebook_id AS object_id, s.notebook_name AS object_name,
               s.notebook_path AS object_path,
               s.detector_name, s.secret_sha256, s.verified, s.scan_time
        FROM {NOTEBOOK_SECRETS_TABLE} s
        JOIN latest_runs r ON s.workspace_id = r.workspace_id
                          AND s.run_id = r.latest_run_id
        WHERE s.secret_sha256 IS NOT NULL""")
    if has_cl:
        parts.append(f"""
        SELECT 'cluster' AS source_type, s.workspace_id, s.run_id,
               s.cluster_id AS object_id, s.cluster_name AS object_name,
               CONCAT(s.config_field, COALESCE(CONCAT('.', s.config_key), '')) AS object_path,
               s.detector_name, s.secret_sha256, s.verified, s.scan_time
        FROM {CLUSTER_SECRETS_TABLE} s
        JOIN latest_runs r ON s.workspace_id = r.workspace_id
                          AND s.run_id = r.latest_run_id
        WHERE s.secret_sha256 IS NOT NULL""")
    return "findings AS (" + "\n        UNION ALL".join(parts) + "\n    )"


@app.route('/api/secrets/summary')
def api_secrets_summary():
    """Headline exposure counts across the fleet."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})

    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT
      COUNT(*)                                          AS total_findings,
      COUNT(DISTINCT secret_sha256)                     AS distinct_secrets,
      COUNT(DISTINCT CONCAT(source_type, ':', COALESCE(object_id, ''))) AS affected_objects,
      COUNT(DISTINCT workspace_id)                      AS affected_workspaces,
      SUM(CASE WHEN verified THEN 1 ELSE 0 END)         AS verified_findings,
      SUM(CASE WHEN source_type = 'notebook' THEN 1 ELSE 0 END) AS notebook_findings,
      SUM(CASE WHEN source_type = 'cluster'  THEN 1 ELSE 0 END) AS cluster_findings,
      MAX(scan_time)                                    AS last_scan_time
    FROM findings
    """)
    summary = rows[0] if rows else {}

    scanned = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)}
    SELECT COUNT(*) AS workspaces_scanned FROM latest_runs
    """)
    workspaces_scanned = (scanned[0].get('workspaces_scanned') if scanned else 0) or 0

    # Tables can exist while holding no rows — created by an earlier install and
    # never populated. That is "not scanned", not "scanned clean"; reporting zero
    # findings for it would be false assurance.
    try:
        if int(workspaces_scanned) == 0:
            return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})
    except (TypeError, ValueError):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})

    summary['workspaces_scanned'] = workspaces_scanned
    return jsonify({'ready': True, 'summary': summary})


@app.route('/api/secrets/by-detector')
def api_secrets_by_detector():
    """Findings grouped by detector type."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})
    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT detector_name,
           COUNT(*) AS findings,
           COUNT(DISTINCT secret_sha256) AS distinct_secrets,
           SUM(CASE WHEN verified THEN 1 ELSE 0 END) AS verified
    FROM findings
    GROUP BY detector_name
    ORDER BY findings DESC
    """)
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/secrets/by-workspace')
def api_secrets_by_workspace():
    """Per-workspace rollup, including workspaces that scanned clean."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})

    has_names = _secrets_table_present('account_workspaces')
    name_col = ("COALESCE(w.workspace_name, l.workspace_id)"
                if has_names else "l.workspace_id")
    name_join = (f"LEFT JOIN `{CATALOG}`.`{SCHEMA}`.account_workspaces w "
                 f"ON w.workspace_id = l.workspace_id" if has_names else "")
    group_extra = ", w.workspace_name" if has_names else ""

    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT l.workspace_id,
           {name_col} AS workspace_name,
           l.latest_run_id AS run_id,
           COUNT(f.secret_sha256) AS findings,
           COUNT(DISTINCT f.secret_sha256) AS distinct_secrets,
           SUM(CASE WHEN f.verified THEN 1 ELSE 0 END) AS verified,
           SUM(CASE WHEN f.source_type = 'notebook' THEN 1 ELSE 0 END) AS notebook_findings,
           SUM(CASE WHEN f.source_type = 'cluster'  THEN 1 ELSE 0 END) AS cluster_findings,
           MAX(f.scan_time) AS last_scan_time
    FROM latest_runs l
    LEFT JOIN findings f ON f.workspace_id = l.workspace_id
    {name_join}
    GROUP BY l.workspace_id, l.latest_run_id{group_extra}
    ORDER BY findings DESC, l.workspace_id
    """)
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/secrets/top-objects')
def api_secrets_top_objects():
    """Objects holding the most findings — where remediation starts."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})
    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT source_type, workspace_id, object_name, object_path,
           COUNT(*) AS findings,
           SUM(CASE WHEN verified THEN 1 ELSE 0 END) AS verified,
           COUNT(DISTINCT detector_name) AS detectors
    FROM findings
    GROUP BY source_type, workspace_id, object_name, object_path
    ORDER BY verified DESC, findings DESC
    LIMIT 25
    """)
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/secrets/shared')
def api_secrets_shared():
    """One credential appearing in several places.

    A repeated hash means the same secret was copied; rotating it requires
    finding every copy, so these are grouped rather than listed individually.
    """
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})
    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT secret_sha256,
           detector_name,
           MAX(CASE WHEN verified THEN 1 ELSE 0 END) AS verified,
           COUNT(*) AS occurrences,
           COUNT(DISTINCT workspace_id) AS workspaces,
           MIN(object_name) AS example_object
    FROM findings
    GROUP BY secret_sha256, detector_name
    HAVING COUNT(*) > 1
    ORDER BY occurrences DESC
    LIMIT 25
    """)
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/secrets/trend')
def api_secrets_trend():
    """Findings per scan run, so regressions are visible over time."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})
    parts = []
    if has_nb:
        parts.append(f"SELECT run_id, 'notebook' AS source_type, secret_sha256, scan_time FROM {NOTEBOOK_SECRETS_TABLE}")
    if has_cl:
        parts.append(f"SELECT run_id, 'cluster' AS source_type, secret_sha256, scan_time FROM {CLUSTER_SECRETS_TABLE}")
    union = "\n        UNION ALL\n        ".join(parts)
    rows = exec_query_df(f"""
    WITH all_rows AS ({union})
    SELECT run_id,
           MIN(scan_time) AS run_time,
           COUNT(secret_sha256) AS findings,
           SUM(CASE WHEN source_type = 'notebook' THEN 1 ELSE 0 END) AS notebook_findings,
           SUM(CASE WHEN source_type = 'cluster'  THEN 1 ELSE 0 END) AS cluster_findings
    FROM all_rows
    GROUP BY run_id
    ORDER BY run_id DESC
    LIMIT 20
    """)
    return jsonify({'ready': True, 'rows': list(reversed(rows))})


@app.route('/api/secrets/findings')
def api_secrets_findings():
    """Detail table. Filters: workspace_id, source_type, detector, verified_only."""
    has_nb, has_cl = _secrets_sources()
    if not (has_nb or has_cl):
        return jsonify({'ready': False, 'message': _SECRETS_NOT_READY})

    try:
        limit = max(1, min(2000, int(request.args.get('limit', 500))))
    except (TypeError, ValueError):
        limit = 500

    where = []
    params = {}
    workspace_id = request.args.get('workspace_id')
    if workspace_id:
        where.append("workspace_id = :workspace_id")
        params['workspace_id'] = workspace_id
    source_type = request.args.get('source_type')
    if source_type in ('notebook', 'cluster'):
        where.append("source_type = :source_type")
        params['source_type'] = source_type
    detector = request.args.get('detector')
    if detector:
        where.append("detector_name = :detector")
        params['detector'] = detector
    if request.args.get('verified_only', 'false').lower() == 'true':
        where.append("verified")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = exec_query_df(f"""
    WITH {_latest_runs_cte(has_nb, has_cl)},
    {_findings_cte(has_nb, has_cl)}
    SELECT source_type, workspace_id, run_id, object_name, object_path,
           detector_name, secret_sha256, verified, scan_time
    FROM findings
    {where_sql}
    ORDER BY verified DESC, workspace_id, source_type, object_name
    LIMIT {limit}
    """, params or None)
    return jsonify({
        'ready': True,
        'rows': rows,
        'count': len(rows),
        'truncated': len(rows) >= limit,
    })


# ---------------------------------------------------------------------------
# Security assistant
#
# Answers questions about the permissions graph, secret scan results, and the
# audit log. The assistant reaches data only through registered tools — it cannot
# issue SQL of its own, and no tool writes to the security tables or triggers a
# job. Its only writes are conversation history and its own tool-call audit trail,
# both allowlisted in agent/sql_client.py.
# ---------------------------------------------------------------------------

# Seed prompts for an empty conversation, chosen to span both datasets and to
# show the cross-dataset chaining the assistant is good at.
ASSISTANT_SUGGESTIONS = [
    "Which service principals hold admin or ownership rights?",
    "What is exposed to everyone in the account?",
    "Who can read the production secret scopes?",
    "What can the SAT service principal access?",
    "Are there hardcoded credentials confirmed active right now?",
]

_agent_tools_registered = False


def _ensure_agent_ready():
    """Import and register the assistant's tools on first use.

    Deferred rather than done at import time so a missing optional dependency
    degrades the assistant alone instead of preventing the app from booting.
    """
    global _agent_tools_registered
    if _agent_tools_registered:
        return True, None
    try:
        from agent.tools import register_all
        register_all()
        _agent_tools_registered = True
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("assistant tools failed to register")
        return False, str(exc)


def _assistant_user():
    """Best-effort identity of the signed-in user, for session ownership."""
    forwarded = (request.headers.get('X-Forwarded-Email')
                 or request.headers.get('X-Forwarded-Preferred-Username'))
    if forwarded:
        return forwarded
    try:
        workspace_client, _ = get_connection()
        me = workspace_client.current_user.me()
        return me.user_name or me.display_name or 'unknown'
    except Exception:  # noqa: BLE001
        return 'unknown'


def _model_endpoint_available(endpoint_name):
    """Check that the configured serving endpoint exists in this workspace.

    Databricks Foundation Model endpoints are not present in every workspace, and
    an absent one otherwise fails with an opaque RESOURCE_DOES_NOT_EXIST on the
    first question. Returns (available, message).
    """
    try:
        workspace_client, _ = get_connection()
        names = {e.name for e in workspace_client.serving_endpoints.list() if e.name}
    except Exception as exc:  # noqa: BLE001
        # If the check itself fails, don't block the assistant — let the call try.
        logger.info("serving endpoint check failed: %s", exc)
        return True, None

    if endpoint_name in names:
        return True, None

    if names:
        listed = ", ".join(sorted(names)[:6])
        return False, (
            f"Model serving endpoint '{endpoint_name}' was not found in this "
            f"workspace. Available endpoints: {listed}. Update MODEL_ENDPOINT and "
            f"redeploy."
        )
    return False, (
        f"Model serving endpoint '{endpoint_name}' was not found, and this "
        f"workspace has no serving endpoints available. Enable Foundation Model "
        f"APIs or point MODEL_ENDPOINT at an existing endpoint, then redeploy."
    )



# ---------------------------------------------------------------------------
# Code security
#
# Findings from the code scanner job: Semgrep for insecure patterns in notebook
# and file source, Trivy for known vulnerabilities in the packages that code
# declares. Each scan writes one row per finding plus a run record; these
# endpoints read the newest run per workspace.
# ---------------------------------------------------------------------------

CODE_FINDINGS_TABLE = f"`{CATALOG}`.`{SCHEMA}`.code_scan_findings"
CODE_RUNS_TABLE = f"`{CATALOG}`.`{SCHEMA}`.code_scan_runs"

SEVERITY_ORDER = "CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END"


def _code_scan_ready():
    """(ready, message) for the code scanner's tables.

    A missing table means the job has not run, which is reported as a state
    rather than an error: the page explains how to start a scan instead of
    showing a failure.
    """
    if not _secrets_table_present('code_scan_findings'):
        return False, ('No code scan has run yet. Start the Code Scanner from '
                       'Data Collection to analyse notebook source and declared '
                       'dependencies.')
    return True, None


def _latest_code_runs():
    return f"""latest AS (
        SELECT workspace_id, MAX(run_id) AS run_id
        FROM {CODE_FINDINGS_TABLE}
        GROUP BY workspace_id
    )"""


@app.route('/api/code/summary')
def api_code_summary():
    ready, message = _code_scan_ready()
    if not ready:
        return jsonify({'ready': False, 'message': message})

    try:
        rows = exec_query_df(f"""
            WITH {_latest_code_runs()}
            SELECT
              COUNT(*) AS total_findings,
              COUNT(DISTINCT f.object_path) AS affected_objects,
              SUM(CASE WHEN f.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS critical,
              SUM(CASE WHEN f.severity = 'HIGH' THEN 1 ELSE 0 END) AS high,
              SUM(CASE WHEN f.severity = 'MEDIUM' THEN 1 ELSE 0 END) AS medium,
              SUM(CASE WHEN f.severity = 'LOW' THEN 1 ELSE 0 END) AS low,
              SUM(CASE WHEN f.scanner = 'semgrep' THEN 1 ELSE 0 END) AS code_findings,
              SUM(CASE WHEN f.scanner = 'trivy' THEN 1 ELSE 0 END) AS dependency_findings,
              COUNT(DISTINCT CASE WHEN f.scanner = 'trivy' THEN f.package_name END) AS vulnerable_packages,
              MAX(f.scan_time) AS last_scan_time
            FROM {CODE_FINDINGS_TABLE} f
            JOIN latest l ON l.workspace_id = f.workspace_id AND l.run_id = f.run_id
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception('code summary failed')
        return jsonify({'error': str(exc)}), 500

    summary = rows[0] if rows else {}

    # The run record carries scanner status, which is how a scan that completed
    # without one of its tools is distinguished from a genuinely clean workspace.
    run = {}
    try:
        run_rows = exec_query_df(f"""
            SELECT semgrep_status, trivy_status, objects_scanned,
                   pinned_packages, unpinned_packages, notes, finished_at
            FROM {CODE_RUNS_TABLE}
            ORDER BY run_id DESC
            LIMIT 1
        """)
        run = run_rows[0] if run_rows else {}
    except Exception:  # noqa: BLE001 - the run table is supplementary
        logger.info('code scan run record unavailable', exc_info=True)

    return jsonify({'ready': True, 'summary': summary, 'run': run})


@app.route('/api/code/by-rule')
def api_code_by_rule():
    ready, message = _code_scan_ready()
    if not ready:
        return jsonify({'ready': False, 'message': message})
    try:
        rows = exec_query_df(f"""
            WITH {_latest_code_runs()}
            SELECT f.scanner, f.rule_id, f.severity, MAX(f.title) AS title,
                   COUNT(*) AS findings,
                   COUNT(DISTINCT f.object_path) AS objects
            FROM {CODE_FINDINGS_TABLE} f
            JOIN latest l ON l.workspace_id = f.workspace_id AND l.run_id = f.run_id
            GROUP BY f.scanner, f.rule_id, f.severity
            ORDER BY {SEVERITY_ORDER}, findings DESC
            LIMIT 100
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/code/top-objects')
def api_code_top_objects():
    ready, message = _code_scan_ready()
    if not ready:
        return jsonify({'ready': False, 'message': message})
    try:
        rows = exec_query_df(f"""
            WITH {_latest_code_runs()}
            SELECT f.object_path,
                   COUNT(*) AS findings,
                   SUM(CASE WHEN f.severity IN ('CRITICAL', 'HIGH') THEN 1 ELSE 0 END) AS severe,
                   COUNT(DISTINCT f.rule_id) AS rules
            FROM {CODE_FINDINGS_TABLE} f
            JOIN latest l ON l.workspace_id = f.workspace_id AND l.run_id = f.run_id
            WHERE f.scanner = 'semgrep'
            GROUP BY f.object_path
            ORDER BY severe DESC, findings DESC
            LIMIT 25
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/code/vulnerable-packages')
def api_code_vulnerable_packages():
    ready, message = _code_scan_ready()
    if not ready:
        return jsonify({'ready': False, 'message': message})
    try:
        rows = exec_query_df(f"""
            WITH {_latest_code_runs()}
            SELECT f.package_name, f.installed_version,
                   MAX(f.fixed_version) AS fixed_version,
                   COUNT(*) AS cves,
                   SUM(CASE WHEN f.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS critical,
                   SUM(CASE WHEN f.severity = 'HIGH' THEN 1 ELSE 0 END) AS high
            FROM {CODE_FINDINGS_TABLE} f
            JOIN latest l ON l.workspace_id = f.workspace_id AND l.run_id = f.run_id
            WHERE f.scanner = 'trivy' AND f.package_name <> ''
            GROUP BY f.package_name, f.installed_version
            ORDER BY critical DESC, high DESC, cves DESC
            LIMIT 50
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500
    return jsonify({'ready': True, 'rows': rows})


@app.route('/api/code/findings')
def api_code_findings():
    ready, message = _code_scan_ready()
    if not ready:
        return jsonify({'ready': False, 'message': message})

    scanner = (request.args.get('scanner') or '').strip().lower()
    severity = (request.args.get('severity') or '').strip().upper()
    search = (request.args.get('q') or '').strip()

    filters = []
    if scanner in ('semgrep', 'trivy'):
        filters.append(f"f.scanner = '{scanner}'")
    if severity in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'):
        filters.append(f"f.severity = '{severity}'")
    if search:
        safe = search.replace("'", "''").replace('%', r'\%').replace('_', r'\_')
        filters.append(
            f"(lower(f.object_path) LIKE lower('%{safe}%') ESCAPE '\\' "
            f"OR lower(f.rule_id) LIKE lower('%{safe}%') ESCAPE '\\' "
            f"OR lower(f.package_name) LIKE lower('%{safe}%') ESCAPE '\\')"
        )
    where = ('AND ' + ' AND '.join(filters)) if filters else ''

    limit = 500
    try:
        rows = exec_query_df(f"""
            WITH {_latest_code_runs()}
            SELECT f.scanner, f.rule_id, f.severity, f.title, f.description,
                   f.object_path, f.line_start, f.package_name,
                   f.installed_version, f.fixed_version, f.reference_url,
                   f.scan_time
            FROM {CODE_FINDINGS_TABLE} f
            JOIN latest l ON l.workspace_id = f.workspace_id AND l.run_id = f.run_id
            WHERE 1 = 1 {where}
            ORDER BY {SEVERITY_ORDER}, f.object_path
            LIMIT {limit + 1}
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception('code findings failed')
        return jsonify({'error': str(exc)}), 500

    truncated = len(rows) > limit
    return jsonify({
        'ready': True,
        'rows': rows[:limit],
        'count': min(len(rows), limit),
        'truncated': truncated,
    })


# ---------------------------------------------------------------------------
# Settings and health
#
# Reports whether every dependency the app needs is actually reachable, and where
# to fix each one that is not. This exists because the failure modes are hard to
# tell apart from a normal page: an expired service principal secret, a revoked
# UC grant and an empty scan table all render as "no data".
#
# Configuration is READ here, never written. The app's secret bindings are
# READ-only by design, and the values it depends on -- warehouse, schema, job
# ids, OAuth scopes -- are bound to the app resource at deploy time. Editing them
# from inside the app would either not take effect until a redeploy or require
# granting the app write access to its own credentials, which would make the app
# a means of privilege escalation. So this page diagnoses precisely and links out
# to the right place to fix.
# ---------------------------------------------------------------------------

def _settings_probe(label, fn, remedy):
    """Run one dependency check, capturing failure rather than raising.

    Each probe returns (ok, detail). A probe that raises is reported as failing
    with its error text, so one broken dependency cannot hide the state of the
    others.
    """
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, str(exc)[:400]
    entry = {'label': label, 'ok': bool(ok), 'detail': detail}
    if not ok:
        entry['remedy'] = remedy
    return entry


# Settings changed from the app. Held in memory and applied over the deployed
# configuration, so a change takes effect on the next request without a redeploy.
# A restart falls back to the values the installer bound, which stay the source of
# truth; every setting here is read per request rather than cached at import.
_SETTING_SPECS = {
    'warehouse_id': {
        'env': 'WAREHOUSE_ID',
        'label': 'SQL warehouse',
        'help': 'Runs every query and every alert.',
    },
    'schema': {
        'env': 'SAT_SCHEMA',
        'label': 'Results schema',
        'help': 'Unity Catalog schema holding collection results, as catalog.schema.',
    },
    'model_endpoint': {
        'env': 'MODEL_ENDPOINT',
        'label': 'Assistant model',
        'help': 'Serving endpoint that answers questions in the assistant.',
    },
    'genie_space_id': {
        'env': 'GENIE_SPACE_ID',
        'label': 'Genie space',
        'help': 'Optional. Leave empty to disable the Genie tool.',
    },
    'per_user_filtering': {
        'env': 'ALLOW_SERVICE_PRINCIPAL_FALLBACK',
        'label': 'Per-user data filtering',
        'help': 'When on, each person sees only what their own Unity Catalog grants allow.',
        'type': 'boolean',
        'inverted': True,
    },
}


def _apply_setting(key, value):
    """Write one setting into the process environment.

    Booleans are stored inverted where the underlying variable is a negative
    (ALLOW_SERVICE_PRINCIPAL_FALLBACK disables filtering), so the UI can offer the
    positive statement without the operator having to reason about the negation.
    """
    spec = _SETTING_SPECS[key]
    if spec.get('type') == 'boolean':
        enabled = bool(value)
        # ALLOW_SERVICE_PRINCIPAL_FALLBACK disables filtering, so the stored value
        # is the negation of what the panel offers.
        stored = (not enabled) if spec.get('inverted') else enabled
        os.environ[spec['env']] = 'true' if stored else 'false'
        return
    os.environ[spec['env']] = str(value or '').strip()


def _validate_setting(key, value):
    """Return an error string, or None when the value is usable.

    Values are checked against the workspace before being applied: a mistyped
    warehouse or schema would otherwise turn every page into an error, from a
    panel whose whole purpose is telling the operator what is wrong.
    """
    if key == 'per_user_filtering':
        return None

    text = str(value or '').strip()

    if key == 'schema':
        parts = [p.strip().strip('`').strip('"') for p in text.split('.') if p.strip()]
        if len(parts) != 2:
            return "Enter the schema as catalog.schema."
        try:
            exec_query_df(f"SELECT 1 FROM `{parts[0]}`.`{parts[1]}`.brickhound_vertices LIMIT 1")
        except NoAccessError:
            raise
        except Exception as exc:  # noqa: BLE001
            return f"Could not read that schema: {str(exc)[:200]}"
        return None

    if key == 'warehouse_id':
        if not text:
            return "A SQL warehouse is required."
        try:
            _sp_workspace_client().warehouses.get(id=text)
        except Exception as exc:  # noqa: BLE001
            return f"No warehouse with that id: {str(exc)[:160]}"
        return None

    if key == 'model_endpoint':
        if not text:
            return "An assistant model is required."
        try:
            names = {e.name for e in _sp_workspace_client().serving_endpoints.list() if e.name}
        except Exception as exc:  # noqa: BLE001
            return f"Could not list serving endpoints: {str(exc)[:160]}"
        if text not in names:
            return f"'{text}' is not a serving endpoint in this workspace."
        return None

    if key == 'genie_space_id':
        if not text:
            return None
        try:
            _sp_workspace_client().genie.get_space(space_id=text)
        except Exception as exc:  # noqa: BLE001
            return f"Could not open that Genie space: {str(exc)[:160]}"
        return None

    return None


@app.route('/api/settings', methods=['PATCH'])
def api_settings_update():
    """Change one or more settings, validating each against the workspace."""
    payload = request.get_json(silent=True) or {}
    unknown = [k for k in payload if k not in _SETTING_SPECS]
    if unknown:
        return jsonify({'error': f"Unknown setting: {', '.join(sorted(unknown))}"}), 400
    if not payload:
        return jsonify({'error': 'Nothing to change.'}), 400

    errors = {}
    for key, value in payload.items():
        message = _validate_setting(key, value)
        if message:
            errors[key] = message
    if errors:
        return jsonify({'errors': errors}), 400

    for key, value in payload.items():
        _apply_setting(key, value)

    # A new warehouse or schema invalidates cached run state and the selected
    # model, so those caches are dropped rather than serving stale answers.
    if 'warehouse_id' in payload or 'schema' in payload:
        _invalidate_collection_cache()
    if 'model_endpoint' in payload:
        _selected_model['endpoint'] = None

    logger.info("settings changed by %s: %s", _assistant_user(), sorted(payload))
    return jsonify({'saved': True, 'changed': sorted(payload)})


@app.route('/api/settings/choices')
def api_settings_choices():
    """Values the settings panel offers in its selects."""
    warehouses, endpoints, spaces = [], [], []
    client = None
    try:
        client = _sp_workspace_client()
    except Exception:  # noqa: BLE001
        logger.info('settings choices unavailable', exc_info=True)

    if client is not None:
        try:
            warehouses = [
                {'id': w.id, 'name': w.name,
                 'state': str(getattr(w, 'state', '') or '').split('.')[-1]}
                for w in client.warehouses.list() if w.id
            ]
        except Exception:  # noqa: BLE001
            logger.info('could not list warehouses', exc_info=True)
        try:
            from agent.supervisor import list_chat_endpoints
            endpoints = [e['name'] for e in list_chat_endpoints()]
        except Exception:  # noqa: BLE001
            logger.info('could not list chat endpoints', exc_info=True)
        try:
            spaces = [
                {'id': sp.space_id, 'name': sp.title or sp.space_id}
                for sp in client.genie.list_spaces().spaces or []
            ]
        except Exception:  # noqa: BLE001
            logger.info('could not list genie spaces', exc_info=True)

    return jsonify({
        'warehouses': sorted(warehouses, key=lambda w: (w['name'] or '').lower()),
        'model_endpoints': endpoints,
        'genie_spaces': sorted(spaces, key=lambda s: (s['name'] or '').lower()),
    })


@app.route('/api/settings')
def api_settings():
    """Configuration and a live health check of every dependency."""
    host = (os.getenv('DATABRICKS_HOST') or '').rstrip('/')
    if host and not host.startswith('http'):
        host = f'https://{host}'
    warehouse_id = os.getenv('WAREHOUSE_ID') or os.getenv('DATABRICKS_WAREHOUSE_ID') or ''
    schema = os.getenv('SAT_SCHEMA') or os.getenv('BRICKHOUND_SCHEMA') or ''

    checks = []

    # 1. User identity / OBO. Checked from the request itself rather than config,
    # because an app can advertise a scope its forwarded token does not carry.
    def check_obo():
        token = request.headers.get('x-forwarded-access-token')
        if not token:
            return False, ('No user token is being forwarded, so queries cannot run '
                           'as the signed-in user.')
        if not _token_has_sql_scope(token):
            return False, ("The forwarded token is missing the 'sql' scope, which "
                           "the Statement Execution API requires.")
        return True, 'Queries run as the signed-in user; Unity Catalog enforces their grants.'

    checks.append(_settings_probe(
        'User authorization (OBO)', check_obo,
        ("Scopes bind when the app is created, so they cannot be added to a running "
         "app. Redeploy with user_api_scopes: [sql, serving.serving-endpoints] "
         "declared on the app resource.")))

    # 2. The app's own identity. This is what fails when a service principal
    # secret is rotated or the principal is deleted.
    def check_sp():
        me = _sp_workspace_client().current_user.me()
        name = getattr(me, 'user_name', None) or getattr(me, 'display_name', None)
        return True, f'Authenticated as {name}.'

    checks.append(_settings_probe(
        'App service principal', check_sp,
        ('The app cannot authenticate as itself. Its service principal may have been '
         'deleted or had its secret rotated. Redeploy the app so the platform issues '
         'fresh credentials.')))

    # 3. Warehouse reachability, which every read and every alert depends on.
    def check_warehouse():
        if not warehouse_id:
            return False, 'No warehouse is configured.'
        wh = _sp_workspace_client().warehouses.get(id=warehouse_id)
        state = str(getattr(wh, 'state', '') or '').split('.')[-1]
        return True, f'{getattr(wh, "name", warehouse_id)} ({state}).'

    checks.append(_settings_probe(
        'SQL warehouse', check_warehouse,
        ('Bind a warehouse to the app with CAN_USE. Re-run the installer if the '
         'binding is missing.')))

    # 4. Can the configured schema actually be read, as the calling user?
    def check_schema():
        if not schema:
            return False, 'No SAT schema is configured.'
        # SELECT 1 must return exactly one row when the warehouse and grants are
        # working. An empty result therefore means the query did not run, which is
        # not distinguishable from "no data" if the probe counts rows in a table.
        probe = exec_query_df('SELECT 1 AS ok')
        if not probe:
            return False, ('The warehouse did not return a result, so the schema '
                           'could not be read. This is a connectivity or grants '
                           'problem, not an absence of data.')
        rows = exec_query_df(f'SELECT COUNT(*) AS n FROM {VERTICES_TABLE}')
        if not rows:
            return False, (f'Connected, but {schema} could not be read. Check '
                           f'USE SCHEMA and SELECT on that schema.')
        n = rows[0].get('n') or 0
        return True, (f'{schema} is readable ({n} rows in the permissions graph).'
                      if n else
                      f'{schema} is readable, but the permissions graph is empty. '
                      f'Run the Permissions Graph collection.')

    checks.append(_settings_probe(
        'Unity Catalog access', check_schema,
        (f'Grant the signed-in user USE CATALOG on the catalog, plus USE SCHEMA and '
         f'SELECT on {schema or "the SAT schema"}. The app service principal needs '
         f'the same, plus CREATE TABLE and MODIFY for its own audit tables.')))

    # 5. Collection jobs: bound, and startable.
    def check_jobs():
        configured = {k: _collection_job_id(k) for k in COLLECTION_JOBS}
        missing = [k for k, v in configured.items() if not v]
        if missing:
            return False, ('Not connected: ' + ', '.join(
                COLLECTION_JOBS[k]['label'] for k in missing))
        return True, f'All {len(configured)} collection jobs are connected.'

    checks.append(_settings_probe(
        'Collection jobs', check_jobs,
        ('These jobs are discovered by name in this workspace. Anything listed as '
         'not deployed has no matching job yet; deploy it with the installer and it '
         'appears here without restarting the app.')))

    # 6. The assistant's model endpoint on the AI Gateway.
    def check_model():
        endpoint = _active_model()
        if not endpoint:
            return False, 'No model endpoint is configured.'
        # _model_endpoint_available deliberately fails open so a failed check does
        # not block the assistant, which means it cannot prove reachability. List
        # the endpoints here so an auth failure is reported rather than hidden.
        client, _ = get_connection()
        names = {e.name for e in client.serving_endpoints.list() if e.name}
        if endpoint not in names:
            return False, (f"'{endpoint}' is not a serving endpoint in this "
                           f"workspace ({len(names)} available).")
        return True, f'{endpoint} is serving.'

    checks.append(_settings_probe(
        'Security assistant model', check_model,
        ('Set MODEL_ENDPOINT to a chat-capable serving endpoint, or pick a different '
         'model from the assistant panel.')))

    # 7. Alerts, which need both a recent SDK and permission to manage alerts.
    def check_alerts():
        client = _sp_workspace_client()
        if not hasattr(client, 'alerts_v2'):
            return False, ('This deployment ships a databricks-sdk older than 0.51, '
                           'which has no alerts API.')
        managed = 0
        known = {spec['column'] for spec in _alert_templates().values()}
        for alert in client.alerts_v2.list_alerts():
            if str(getattr(alert, 'lifecycle_state', '') or '').split('.')[-1] == 'DELETED':
                continue
            entry = _serialise_alert(alert)
            if entry['column'] in known or (entry['display_name'] or '').startswith(
                    ALERT_NAME_PREFIX):
                managed += 1
        return True, (f'{managed} secret-scanning alert(s) configured.' if managed
                      else 'Alerts API reachable; none configured yet.')

    checks.append(_settings_probe(
        'Secret-scanning alerts', check_alerts,
        ('The app service principal needs permission to manage SQL alerts in this '
         'workspace, and databricks-sdk 0.51 or newer.')))

    # 8. Genie, which is optional by design.
    genie_space = (os.getenv('GENIE_SPACE_ID') or '').strip()
    checks.append({
        'label': 'Genie space (optional)',
        'ok': True,
        'detail': (f'Configured ({genie_space}).' if genie_space
                   else 'Not configured. The assistant reports that tool as '
                        'unavailable and keeps working.'),
        'optional': True,
    })

    failing = [c for c in checks if not c['ok']]
    return jsonify({
        'healthy': not failing,
        'failing_count': len(failing),
        'checks': checks,
        'config': {
            'workspace_host': host,
            'workspace_id': (os.getenv('WORKSPACE_ID') or '').strip(),
            'schema': schema,
            'warehouse_id': warehouse_id,
            'model_endpoint': _active_model(),
            'genie_space_id': genie_space,
            'sp_fallback_allowed': (
                os.getenv('ALLOW_SERVICE_PRINCIPAL_FALLBACK', 'false').strip().lower()
                == 'true'),
            'jobs': {
                kind: {'label': spec['label'], 'connected': bool(_collection_job_id(kind))}
                for kind, spec in COLLECTION_JOBS.items()
            },
        },
        'links': {
            'app_settings': f'{host}/apps' if host else None,
            'warehouse': (f'{host}/sql/warehouses/{warehouse_id}'
                          if host and warehouse_id else None),
            'alerts': f'{host}/sql/alerts' if host else None,
            'secret_scope': f'{host}/#secrets' if host else None,
        },
    })


# ---------------------------------------------------------------------------
# Secret-scanning alerts
#
# These are ordinary Databricks SQL alerts (the alerts/v2 API), created and
# managed through the app rather than reimplemented in it. That means the
# schedule, evaluation, notification destinations and history all behave exactly
# as they do for any hand-built alert, and an alert made here remains fully
# editable in the workspace UI. The app supplies the query and sensible defaults
# so an operator does not have to write SQL against the scan tables.
# ---------------------------------------------------------------------------

# Marks alerts this app created, so the list view can show only SAT's own without
# touching a user's unrelated alerts.
ALERT_NAME_PREFIX = "SAT Secrets"


def _alert_templates():
    """Alert definitions offered in the UI, keyed by template id.

    ``column`` must match the alias the query returns: the alerts API evaluates a
    named column, not the first column by position.
    """
    return {
        'verified_findings': {
            'label': 'Confirmed active credentials',
            'description': (
                'Fires when the scanner confirms a credential is live by validating '
                'it against the service. The highest-severity signal available.'
            ),
            'column': 'verified_findings',
            'default_threshold': 0,
            'default_operator': 'GREATER_THAN',
            'severity': 'critical',
            'query': f"""SELECT COUNT(*) AS verified_findings
FROM {NOTEBOOK_SECRETS_TABLE}
WHERE verified = true
  AND secret_sha256 IS NOT NULL
  AND run_id = (SELECT MAX(run_id) FROM {NOTEBOOK_SECRETS_TABLE})""",
        },
        'total_findings': {
            'label': 'Any hardcoded secret found',
            'description': (
                'Fires when the most recent scan finds any hardcoded secret, '
                'whether or not it was validated as live.'
            ),
            'column': 'total_findings',
            'default_threshold': 0,
            'default_operator': 'GREATER_THAN',
            'severity': 'high',
            'query': f"""SELECT COUNT(*) AS total_findings
FROM {NOTEBOOK_SECRETS_TABLE}
WHERE secret_sha256 IS NOT NULL
  AND run_id = (SELECT MAX(run_id) FROM {NOTEBOOK_SECRETS_TABLE})""",
        },
        'new_findings': {
            'label': 'Findings increased since previous scan',
            'description': (
                'Fires only when the newest scan found more secrets than the one '
                'before it, so a known backlog does not alert every day.'
            ),
            'column': 'new_findings',
            'default_threshold': 0,
            'default_operator': 'GREATER_THAN',
            'severity': 'high',
            'query': f"""WITH runs AS (
  SELECT run_id, ROW_NUMBER() OVER (ORDER BY run_id DESC) AS rn
  FROM (SELECT DISTINCT run_id FROM {NOTEBOOK_SECRETS_TABLE})
),
counts AS (
  SELECT r.rn, COUNT(*) AS findings
  FROM {NOTEBOOK_SECRETS_TABLE} s
  JOIN runs r ON r.run_id = s.run_id
  WHERE s.secret_sha256 IS NOT NULL AND r.rn <= 2
  GROUP BY r.rn
)
SELECT COALESCE(MAX(CASE WHEN rn = 1 THEN findings END), 0)
     - COALESCE(MAX(CASE WHEN rn = 2 THEN findings END), 0) AS new_findings
FROM counts""",
        },
        'stale_scan': {
            'label': 'Scanner has not run recently',
            'description': (
                'Fires when the last completed scan is older than the threshold in '
                'hours. Catches a silently broken schedule, where no findings is '
                'indistinguishable from no scanning.'
            ),
            'column': 'hours_since_scan',
            'default_threshold': 48,
            'default_operator': 'GREATER_THAN',
            'severity': 'medium',
            'query': f"""SELECT COALESCE(
         CAST((unix_timestamp(current_timestamp())
               - unix_timestamp(MAX(scan_time))) / 3600 AS DOUBLE), 999999
       ) AS hours_since_scan
FROM {NOTEBOOK_SECRETS_TABLE}""",
        },
    }


def _alert_schedule_presets():
    return [
        {'label': 'Every hour', 'cron': '0 0 * * * ?'},
        {'label': 'Every 6 hours', 'cron': '0 0 0/6 * * ?'},
        {'label': 'Daily at 08:00', 'cron': '0 0 8 * * ?'},
        {'label': 'Daily at 18:00', 'cron': '0 0 18 * * ?'},
        {'label': 'Weekly, Monday 08:00', 'cron': '0 0 8 ? * MON'},
    ]


def _serialise_alert(alert, templates=None):
    """Flatten an AlertV2 into the shape the UI renders."""
    templates = templates or _alert_templates()
    evaluation = getattr(alert, 'evaluation', None)
    notification = getattr(evaluation, 'notification', None) if evaluation else None
    schedule = getattr(alert, 'schedule', None)

    def enum_name(value):
        return str(value).split('.')[-1] if value is not None else None

    threshold = None
    operand = getattr(evaluation, 'threshold', None) if evaluation else None
    value = getattr(operand, 'value', None) if operand else None
    if value is not None:
        for attr in ('double_value', 'string_value', 'bool_value'):
            got = getattr(value, attr, None)
            if got is not None:
                threshold = got
                break

    # The template is recovered from the evaluated column name, which is stable;
    # the display name is user-editable and cannot be relied on.
    column = getattr(getattr(evaluation, 'source', None), 'name', None)
    template_id = next(
        (tid for tid, spec in templates.items() if spec['column'] == column), None)

    pause_status = enum_name(
        getattr(schedule, 'pause_status', None)
        or getattr(schedule, 'effective_pause_status', None))

    return {
        'id': alert.id,
        'display_name': alert.display_name,
        'template_id': template_id,
        'severity': (templates.get(template_id) or {}).get('severity'),
        'column': column,
        'operator': enum_name(getattr(evaluation, 'comparison_operator', None)),
        'threshold': threshold,
        'state': enum_name(getattr(evaluation, 'state', None)),
        'lifecycle_state': enum_name(getattr(alert, 'lifecycle_state', None)),
        'last_evaluated_at': getattr(evaluation, 'last_evaluated_at', None),
        'cron': getattr(schedule, 'quartz_cron_schedule', None),
        'timezone_id': getattr(schedule, 'timezone_id', None),
        'paused': pause_status == 'PAUSED',
        'notify_on_ok': bool(getattr(notification, 'notify_on_ok', False)),
        'retrigger_seconds': getattr(notification, 'retrigger_seconds', None),
        'subscribers': [
            s.user_email for s in (getattr(notification, 'subscriptions', None) or [])
            if getattr(s, 'user_email', None)
        ],
        'destination_ids': [
            s.destination_id for s in (getattr(notification, 'subscriptions', None) or [])
            if getattr(s, 'destination_id', None)
        ],
        'owner': getattr(alert, 'owner_user_name', None),
        'url': _alert_url(alert.id),
    }


def _alert_url(alert_id):
    host = (os.getenv('DATABRICKS_HOST') or '').rstrip('/')
    if not host or not alert_id:
        return None
    if not host.startswith('http'):
        host = f"https://{host}"
    return f"{host}/sql/alerts/{alert_id}"


def _build_alert_object(payload, template, existing=None):
    """Construct an AlertV2 from a UI payload.

    Raises ValueError with a user-facing message on invalid input, so the caller
    can return 400 rather than surfacing an SDK error.
    """
    from databricks.sdk.service import sql as sql_service

    warehouse_id = os.getenv('WAREHOUSE_ID') or os.getenv('DATABRICKS_WAREHOUSE_ID')
    if not warehouse_id:
        raise ValueError('No SQL warehouse is configured for this app.')

    name = (payload.get('display_name') or '').strip()
    if not name:
        name = f"{ALERT_NAME_PREFIX}: {template['label']}"
    if len(name) > 200:
        raise ValueError('Name is too long (200 character limit).')

    operator = (payload.get('operator') or template['default_operator']).strip().upper()
    valid_operators = {o.name for o in sql_service.ComparisonOperator}
    if operator not in valid_operators:
        raise ValueError(f"Unsupported comparison '{operator}'.")

    raw_threshold = payload.get('threshold')
    if raw_threshold is None or raw_threshold == '':
        raw_threshold = template['default_threshold']
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        raise ValueError('Threshold must be a number.')

    subscribers = payload.get('subscribers') or []
    if isinstance(subscribers, str):
        subscribers = re.split(r'[,;\s]+', subscribers)
    emails = [e.strip() for e in subscribers if e and e.strip()]
    for email in emails:
        if '@' not in email or len(email) > 320:
            raise ValueError(f"'{email}' is not a valid email address.")

    destination_ids = [
        d.strip() for d in (payload.get('destination_ids') or []) if d and d.strip()
    ]
    if not emails and not destination_ids:
        raise ValueError(
            'Add at least one email address or notification destination, '
            'otherwise the alert has nobody to notify.')

    subscriptions = [
        sql_service.AlertV2Subscription(user_email=email) for email in emails
    ] + [
        sql_service.AlertV2Subscription(destination_id=d) for d in destination_ids
    ]

    cron = (payload.get('cron') or '0 0 8 * * ?').strip()
    timezone_id = (payload.get('timezone_id') or 'UTC').strip()

    try:
        retrigger = int(payload.get('retrigger_seconds') or 3600)
    except (TypeError, ValueError):
        raise ValueError('Re-notify interval must be a whole number of seconds.')
    retrigger = max(0, min(retrigger, 86400 * 7))

    pause = bool(payload.get('paused'))

    return sql_service.AlertV2(
        display_name=name,
        query_text=template['query'],
        warehouse_id=warehouse_id,
        custom_description=template['description'],
        evaluation=sql_service.AlertV2Evaluation(
            source=sql_service.AlertV2OperandColumn(name=template['column']),
            comparison_operator=getattr(sql_service.ComparisonOperator, operator),
            # An empty result means the scan tables hold no matching rows, which is
            # the healthy case for every template here.
            empty_result_state=sql_service.AlertEvaluationState.OK,
            threshold=sql_service.AlertV2Operand(
                value=sql_service.AlertV2OperandValue(double_value=threshold)),
            notification=sql_service.AlertV2Notification(
                notify_on_ok=bool(payload.get('notify_on_ok')),
                retrigger_seconds=retrigger,
                subscriptions=subscriptions,
            ),
        ),
        schedule=sql_service.CronSchedule(
            quartz_cron_schedule=cron,
            timezone_id=timezone_id,
            pause_status=(sql_service.SchedulePauseStatus.PAUSED if pause
                          else sql_service.SchedulePauseStatus.UNPAUSED),
        ),
    )


def _alert_error_message(exc):
    """Turn an alerts API error into something a user can act on.

    The API rejects a subscriber who is not a member of the workspace, but says
    so as "Failed to get user id for email: ...", which reads like an internal
    fault rather than the input problem it is.
    """
    raw = str(exc)
    match = re.search(r'Failed to get user id for email:\s*([^\s]+)', raw)
    if match:
        return (f"{match.group(1)} is not a member of this workspace. Databricks "
                f"alerts can only notify existing workspace users -- add them to "
                f"the workspace first, or use a notification destination such as "
                f"Slack or a webhook for external recipients.")
    if 'PERMISSION_DENIED' in raw or 'does not have' in raw:
        return (f"Not permitted to manage alerts in this workspace: {raw}")
    return f"Could not save the alert: {raw}"


@app.route('/api/secrets/alerts/options')
def api_secrets_alert_options():
    """Templates, schedule presets and destinations for the alert editor."""
    templates = [
        {
            'id': tid,
            'label': spec['label'],
            'description': spec['description'],
            'severity': spec['severity'],
            'default_threshold': spec['default_threshold'],
            'default_operator': spec['default_operator'],
            'column': spec['column'],
            'query': spec['query'],
        }
        for tid, spec in _alert_templates().items()
    ]

    # Notification destinations (Slack, PagerDuty, webhooks) are workspace-level
    # objects. Listing them is best-effort: email subscriptions work regardless.
    destinations = []
    try:
        client = _sp_workspace_client()
        for dest in client.notification_destinations.list():
            destinations.append({
                'id': dest.id,
                'display_name': dest.display_name,
                'type': str(getattr(dest, 'destination_type', '') or '').split('.')[-1],
            })
    except Exception:  # noqa: BLE001
        logger.info('could not list notification destinations', exc_info=True)

    # Only a real address is offered as the default recipient. _assistant_user()
    # falls back to a service principal id when no user identity is forwarded,
    # and prefilling that would create an alert that notifies nobody.
    user = _assistant_user()
    default_recipient = user if user and '@' in user else ''

    return jsonify({
        'templates': templates,
        'schedule_presets': _alert_schedule_presets(),
        'destinations': destinations,
        'current_user': default_recipient,
        'warehouse_configured': bool(
            os.getenv('WAREHOUSE_ID') or os.getenv('DATABRICKS_WAREHOUSE_ID')),
    })


@app.route('/api/secrets/alerts')
def api_secrets_alerts_list():
    """Alerts this app manages, newest first."""
    try:
        client = _sp_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    templates = _alert_templates()
    known_columns = {spec['column'] for spec in templates.values()}
    alerts = []
    try:
        for alert in client.alerts_v2.list_alerts():
            lifecycle = str(getattr(alert, 'lifecycle_state', '') or '').split('.')[-1]
            if lifecycle == 'DELETED':
                continue
            entry = _serialise_alert(alert, templates)
            # Show only secret-scanning alerts: either created from a template
            # (recognised by evaluated column) or named as one.
            if entry['column'] in known_columns or (
                    entry['display_name'] or '').startswith(ALERT_NAME_PREFIX):
                alerts.append(entry)
    except Exception as exc:  # noqa: BLE001
        logger.exception('listing alerts failed')
        return jsonify({'error': str(exc)}), 500

    alerts.sort(key=lambda a: (a['paused'], a['display_name'] or ''))
    return jsonify({'alerts': alerts, 'count': len(alerts)})


@app.route('/api/secrets/alerts', methods=['POST'])
def api_secrets_alerts_create():
    """Create a Databricks SQL alert from one of the secret-scanning templates."""
    payload = request.get_json(silent=True) or {}
    template_id = (payload.get('template_id') or '').strip()
    templates = _alert_templates()
    if template_id not in templates:
        return jsonify({'error': f"Unknown alert type '{template_id}'."}), 400

    try:
        alert = _build_alert_object(payload, templates[template_id])
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        client = _sp_workspace_client()
        created = client.alerts_v2.create_alert(alert=alert)
    except Exception as exc:  # noqa: BLE001
        logger.exception('alert creation failed')
        return jsonify({'error': _alert_error_message(exc)}), 400

    logger.info('created secrets alert %s (%s) by %s',
                created.id, template_id, _assistant_user())
    return jsonify({'alert': _serialise_alert(created, templates), 'created': True})


@app.route('/api/secrets/alerts/<alert_id>', methods=['PATCH'])
def api_secrets_alerts_update(alert_id):
    """Update an alert, or pause/resume it.

    A body of {"paused": true|false} alone toggles the schedule and leaves
    everything else untouched, so the list view's switch does not have to
    round-trip the whole definition.
    """
    payload = request.get_json(silent=True) or {}
    try:
        client = _sp_workspace_client()
        current = client.alerts_v2.get_alert(id=alert_id)
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    from databricks.sdk.service import sql as sql_service

    pause_only = set(payload.keys()) <= {'paused'}
    if pause_only:
        if 'paused' not in payload:
            return jsonify({'error': 'Nothing to update.'}), 400
        if current.schedule is None:
            return jsonify({'error': 'This alert has no schedule to pause.'}), 400
        current.schedule.pause_status = (
            sql_service.SchedulePauseStatus.PAUSED if payload['paused']
            else sql_service.SchedulePauseStatus.UNPAUSED)
        try:
            updated = client.alerts_v2.update_alert(
                id=alert_id, alert=current, update_mask='schedule')
        except Exception as exc:  # noqa: BLE001
            logger.exception('alert pause toggle failed')
            return jsonify({'error': str(exc)}), 500
        return jsonify({'alert': _serialise_alert(updated), 'updated': True})

    templates = _alert_templates()
    template_id = (payload.get('template_id') or '').strip()
    if template_id not in templates:
        # Fall back to the template the alert was built from, so a partial edit
        # does not need to restate its type.
        template_id = _serialise_alert(current, templates).get('template_id')
    if template_id not in templates:
        return jsonify({'error': 'This alert is not managed by SAT.'}), 400

    try:
        rebuilt = _build_alert_object(payload, templates[template_id], existing=current)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        updated = client.alerts_v2.update_alert(
            id=alert_id, alert=rebuilt,
            update_mask='display_name,query_text,evaluation,schedule,custom_description')
    except Exception as exc:  # noqa: BLE001
        logger.exception('alert update failed')
        return jsonify({'error': _alert_error_message(exc)}), 400

    logger.info('updated secrets alert %s by %s', alert_id, _assistant_user())
    return jsonify({'alert': _serialise_alert(updated, templates), 'updated': True})


@app.route('/api/secrets/alerts/<alert_id>', methods=['DELETE'])
def api_secrets_alerts_delete(alert_id):
    """Move an alert to trash. Recoverable in the workspace UI."""
    try:
        client = _sp_workspace_client()
        client.alerts_v2.trash_alert(id=alert_id)
    except Exception as exc:  # noqa: BLE001
        # Already trashed is the outcome the caller asked for, so it is reported as
        # success rather than an error the user can do nothing about.
        if 'already trashed' in str(exc).lower():
            return jsonify({'deleted': True, 'id': alert_id, 'already_deleted': True})
        logger.exception('alert delete failed')
        return jsonify({'error': _alert_error_message(exc)}), 400
    logger.info('trashed secrets alert %s by %s', alert_id, _assistant_user())
    return jsonify({'deleted': True, 'id': alert_id})


# ---------------------------------------------------------------------------
# AI Gateway integration
#
# Model calls, model selection, and usage reporting all go through the
# workspace's AI Gateway. Requests carry a usage_context map that the gateway
# persists to system.serving.endpoint_usage, so this app's traffic is separable
# for tracing and cost attribution.
# ---------------------------------------------------------------------------

# Endpoint chosen in the UI, held in memory. A restart falls back to
# MODEL_ENDPOINT, which is the installer-managed default.
_selected_model = {'endpoint': None}


def _active_model():
    return _selected_model['endpoint'] or os.getenv('MODEL_ENDPOINT') or 'databricks-claude-opus-4-7'


@app.route('/api/assistant/models')
def api_assistant_models():
    """Chat endpoints available on the gateway, and which one is in use.

    ``?refresh=1`` re-probes rather than using the cached result, for when the
    gateway's model line-up changes mid-session.
    """
    refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    try:
        from agent.supervisor import list_chat_endpoints
        endpoints = list_chat_endpoints(refresh=refresh)
    except Exception as exc:  # noqa: BLE001
        logger.exception("listing gateway endpoints failed")
        return jsonify({'error': str(exc), 'models': [], 'active': _active_model()}), 500

    return jsonify({
        'models': endpoints,
        'active': _active_model(),
        'default': os.getenv('MODEL_ENDPOINT'),
        'gateway': (os.getenv('AI_GATEWAY_BASE_URL')
                    or f"{(os.getenv('DATABRICKS_HOST') or '').rstrip('/')}/serving-endpoints"),
    })


@app.route('/api/assistant/models', methods=['POST'])
def api_assistant_models_select():
    """Switch the assistant's model.

    Validated against the gateway's own list so a selection cannot point at an
    endpoint that does not exist or is not chat-capable.
    """
    payload = request.get_json(silent=True) or {}
    endpoint = (payload.get('endpoint') or '').strip()
    if not endpoint:
        return jsonify({'error': 'An endpoint name is required.'}), 400

    try:
        from agent.supervisor import list_chat_endpoints
        available = {e['name'] for e in list_chat_endpoints()}
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    if endpoint not in available:
        return jsonify({
            'error': (f"'{endpoint}' is not an available chat endpoint on this "
                      f"workspace's AI Gateway.")
        }), 400

    _selected_model['endpoint'] = endpoint
    logger.info("assistant model set to %s by %s", endpoint, _assistant_user())
    return jsonify({'active': endpoint, 'saved': True})


@app.route('/api/assistant/usage')
def api_assistant_usage():
    """Token usage and request counts for this app, from the gateway's own records.

    Reads system.serving.endpoint_usage, filtered on the usage_context this app
    stamps on every request, so the figures cover assistant traffic only rather
    than everything sharing the endpoint.
    """
    try:
        days = max(1, min(90, int(request.args.get('days', 7))))
    except (TypeError, ValueError):
        days = 7

    try:
        rows = exec_query_df(f"""
            SELECT
              e.served_entity_id,
              COALESCE(se.endpoint_name, e.served_entity_id) AS endpoint,
              COUNT(*)                        AS requests,
              SUM(e.input_token_count)        AS input_tokens,
              SUM(e.output_token_count)       AS output_tokens,
              COUNT(DISTINCT e.usage_context['end_user'])  AS users,
              COUNT(DISTINCT e.usage_context['session'])   AS sessions,
              SUM(CASE WHEN e.status_code >= 400 THEN 1 ELSE 0 END) AS errors,
              MAX(e.request_time)             AS last_request
            FROM system.serving.endpoint_usage e
            LEFT JOIN system.serving.served_entities se
                   ON se.served_entity_id = e.served_entity_id
            WHERE e.request_time >= current_timestamp() - INTERVAL {days} DAYS
              AND e.usage_context['application'] = 'security-analysis-tool'
            GROUP BY e.served_entity_id, COALESCE(se.endpoint_name, e.served_entity_id)
            ORDER BY requests DESC
        """)
    except NoAccessError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("gateway usage query failed: %s", exc)
        return jsonify({
            'available': False,
            'message': ('Usage records are not readable from this app. Access to '
                        'system.serving.endpoint_usage is required to report token '
                        'consumption.'),
        })

    # The system table is populated on a delay, so an empty result for a recent
    # window is expected rather than a fault. Report the freshness alongside the
    # figures so a reader can tell "no usage" from "not yet ingested".
    latest = None
    try:
        freshness = exec_query_df(
            "SELECT MAX(request_time) AS latest FROM system.serving.endpoint_usage")
        if freshness:
            latest = freshness[0].get('latest')
    except Exception:  # noqa: BLE001
        pass

    return jsonify({
        'available': True,
        'days': days,
        'rows': rows,
        'records_through': latest,
        'note': ('Usage records are ingested by the platform on a delay, so very '
                 'recent activity may not appear yet.') if not rows else None,
    })


@app.route('/api/assistant/config')
def api_assistant_config():
    """Whether the assistant can answer, plus suggested prompts."""
    endpoint = _active_model()
    if not endpoint:
        return jsonify({
            'ready': False,
            'message': ('The security assistant is not configured. Set MODEL_ENDPOINT '
                        'to a model serving endpoint and redeploy.'),
        })
    ok, err = _ensure_agent_ready()
    if not ok:
        return jsonify({'ready': False, 'message': f'Assistant unavailable: {err}'})

    available, detail = _model_endpoint_available(endpoint)
    if not available:
        return jsonify({'ready': False, 'message': detail})

    return jsonify({
        'ready': True,
        'suggestions': ASSISTANT_SUGGESTIONS,
        'genie_configured': bool(os.getenv('GENIE_SPACE_ID')),
        'read_only': True,
        'model': endpoint,
    })


@app.route('/api/assistant/chat', methods=['POST'])
def api_assistant_chat():
    """Answer one conversational turn."""
    if not os.getenv('MODEL_ENDPOINT'):
        return jsonify({'error': 'The security assistant is not configured.'}), 503
    ok, err = _ensure_agent_ready()
    if not ok:
        return jsonify({'error': f'Assistant unavailable: {err}'}), 503

    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    session_id = payload.get('session_id')
    turn_id = (payload.get('turn_id') or '').strip() or None
    if not message:
        return jsonify({'error': 'message is required'}), 400
    if len(message) > 4000:
        return jsonify({'error': 'message is too long (4000 character limit)'}), 400

    try:
        from agent import sessions
        from agent.logging_util import new_session_id
        from agent.supervisor import get_supervisor
    except Exception as exc:  # noqa: BLE001
        logger.exception("assistant import failed")
        return jsonify({'error': f'Assistant unavailable: {exc}'}), 503

    session_id = session_id or new_session_id()
    user = _assistant_user()

    # History is a convenience, not a correctness requirement — answer even if the
    # sessions table is unreachable.
    try:
        history = sessions.load(session_id)
    except Exception:  # noqa: BLE001
        logger.warning("session load failed; continuing without history", exc_info=True)
        history = []

    if turn_id:
        _register_turn(turn_id)

    def run_turn(endpoint):
        return get_supervisor().chat(
            session_id=session_id,
            user=user,
            history=history,
            new_message=message,
            model=endpoint,
            is_cancelled=(lambda: _turn_cancelled(turn_id)) if turn_id else None,
        )

    try:
        try:
            result = run_turn(_active_model())
        except Exception as exc:  # noqa: BLE001
            # A model can be retired between being picked and being used. Rather than
            # dead-ending the conversation, drop the stale choice, re-probe the gateway
            # and answer on the default endpoint.
            if 'deprecated' in str(exc).lower():
                logger.warning("selected model %s is deprecated; falling back", _active_model())
                _selected_model['endpoint'] = None
                try:
                    from agent.supervisor import list_chat_endpoints
                    list_chat_endpoints(refresh=True)
                    result = run_turn(_active_model())
                except Exception as retry_exc:  # noqa: BLE001
                    logger.exception("fallback after deprecation also failed")
                    return jsonify({'error': str(retry_exc), 'session_id': session_id}), 500
            else:
                logger.exception("assistant turn failed")
                return jsonify({'error': str(exc), 'session_id': session_id}), 500
    finally:
        if turn_id:
            _release_turn(turn_id)

    # A cancelled turn is not persisted: it holds a partial exchange the user
    # abandoned, and saving it would carry that into the next question's context.
    if not result.get('cancelled'):
        # A persistence failure must not lose the answer the user already waited for.
        try:
            sessions.save(session_id, user, result.get('messages', []))
        except Exception:  # noqa: BLE001
            logger.warning("session save failed", exc_info=True)

    return jsonify({
        'session_id': session_id,
        'answer': result.get('reply', ''),
        'tool_calls': result.get('tool_calls', []),
        'cancelled': bool(result.get('cancelled')),
        # Which gateway endpoint answered, so the UI can show it per message.
        'model': result.get('model') or _active_model(),
    })


# In-flight assistant turns, so a Stop from the browser can halt the tool loop
# server-side. Without this the fetch is abandoned but the loop keeps calling the
# model and running tools, spending tokens on an answer nobody will read.
_active_turns = {}
_turns_lock = threading.Lock()
_MAX_TRACKED_TURNS = 256


def _register_turn(turn_id):
    with _turns_lock:
        # Bound the map so a client that never completes a turn cannot grow it
        # without limit; oldest entries go first.
        while len(_active_turns) >= _MAX_TRACKED_TURNS:
            _active_turns.pop(next(iter(_active_turns)), None)
        _active_turns[turn_id] = False


def _release_turn(turn_id):
    with _turns_lock:
        _active_turns.pop(turn_id, None)


def _turn_cancelled(turn_id):
    with _turns_lock:
        return bool(_active_turns.get(turn_id))


@app.route('/api/assistant/cancel', methods=['POST'])
def api_assistant_cancel():
    """Ask an in-flight assistant turn to stop at its next checkpoint."""
    payload = request.get_json(silent=True) or {}
    turn_id = (payload.get('turn_id') or '').strip()
    if not turn_id:
        return jsonify({'error': 'turn_id is required'}), 400
    with _turns_lock:
        known = turn_id in _active_turns
        if known:
            _active_turns[turn_id] = True
    # An unknown id means the turn already finished -- not an error worth
    # surfacing, since the user's intent (it is not running) already holds.
    return jsonify({'cancelled': known, 'turn_id': turn_id})


# Cached service-principal client; see _sp_workspace_client for why.
_sp_client = None
_sp_client_lock = threading.Lock()


def _sp_workspace_client():
    """WorkspaceClient authenticated as the app's service principal.

    Job control uses this rather than the calling user's token. The job resource
    binding in app.yaml grants CAN_MANAGE_RUN to the app's service principal, and
    Databricks Apps exposes no user-authorization scope for the Jobs API — so an
    on-behalf-of-user token cannot start a run no matter its UC grants.

    Reading security data still runs as the user (see get_connection), so UC
    continues to enforce per-user visibility on findings.

    The client is cached: constructing one resolves credentials from scratch,
    which measured 0.65-1.0s and was the largest single cost in loading the data
    collection page. The SDK refreshes the underlying OAuth token itself, so a
    long-lived client keeps working. This is the app's own identity and carries no
    per-user state, so sharing one across requests is safe -- unlike
    get_connection(), which must stay per-request because it binds a user token.
    """
    global _sp_client
    if _sp_client is None:
        with _sp_client_lock:
            if _sp_client is None:
                from databricks.sdk import WorkspaceClient
                _sp_client = WorkspaceClient()
    return _sp_client



# ---------------------------------------------------------------------------
# Data collection control
#
# Lets an operator refresh the permissions graph or re-run the secret scanners
# without leaving the app.
#
# Scope is deliberately narrow: only the job IDs bound in this app's
# configuration can be started. There is no endpoint that accepts an arbitrary
# job ID, nothing here edits a job definition, and the security assistant has no
# tool that reaches these routes — it can explain findings but cannot cause
# anything to run.
# ---------------------------------------------------------------------------

# Logical name -> env vars that may carry that job's ID. Databricks Apps exposes
# a bound job resource as DATABRICKS_JOB_ID_<RESOURCE_NAME>; the plain names are
# accepted as an override and for local runs.
COLLECTION_JOBS = {
    'permissions': {
        'label': 'Permissions Graph',
        'group': 'Access',
        'description': 'Collects identities, groups, and grants, then builds the access graph.',
        'env': ('PERMISSIONS_JOB_ID', 'DATABRICKS_JOB_ID_PERMISSIONS_JOB'),
        'feeds': 'Principal and resource analysis, escalation paths, high privilege',
        'job_name_match': 'Data Collection',
    },
    'secrets': {
        'label': 'Secret Scanner',
        'group': 'Secrets',
        'description': 'Scans notebook source and cluster environment variables for credentials.',
        'env': ('SECRETS_JOB_ID', 'DATABRICKS_JOB_ID_SECRETS_JOB'),
        'feeds': 'Credential exposure, secret findings',
        'job_name_match': 'Secrets Scanner',
    },
    'shared_to_account': {
        'label': 'Shared to All Users',
        'group': 'Access',
        'description': 'Finds dashboards, Genie spaces, and apps shared with every account user.',
        'env': ('SHARED_TO_ACCOUNT_JOB_ID',),
        'feeds': 'Shared to All Users',
        'job_name_match': 'Shared to Account Users',
    },
    'privileged_non_idp': {
        'label': 'Privileged Non-IdP Identities',
        'group': 'Identity',
        'description': 'Finds admin roles held outside identity-provider-managed groups.',
        'env': ('PRIVILEGED_NON_IDP_JOB_ID',),
        'feeds': 'Privileged Non-IdP',
        'job_name_match': 'Privileged Non-IdP',
    },
    'denylist_candidates': {
        'label': 'Denylist Candidates',
        'group': 'Identity',
        'description': 'Ranks IdP groups whose members show no recent Databricks activity.',
        'env': ('DENYLIST_JOB_ID',),
        'feeds': 'Denylist Builder',
        'job_name_match': 'Denylist Candidates',
    },
    'code_scanner': {
        'label': 'Code Scanner',
        'group': 'Code',
        'description': 'Analyses notebook and file source for insecure patterns, and declared packages for known vulnerabilities.',
        'env': ('CODE_SCANNER_JOB_ID', 'DATABRICKS_JOB_ID_CODE_SCANNER_JOB'),
        'feeds': 'Code security overview, code findings',
        'job_name_match': 'Code Scanner',
    },
}

# Display order for the groups above.
COLLECTION_GROUPS = ('Access', 'Identity', 'Secrets', 'Code')

# Run states that mean a collection is still in flight.
_ACTIVE_RUN_STATES = {
    'PENDING', 'RUNNING', 'QUEUED', 'TERMINATING', 'BLOCKED', 'WAITING_FOR_RETRY',
}


# Job ids discovered from the workspace, keyed by collection. Populated on first
# use and refreshed when a lookup misses, so a job deployed after the app started
# is picked up without a restart.
_discovered_jobs: dict[str, str] = {}
_discovery_lock = threading.Lock()
_discovery_checked_at = 0.0
_DISCOVERY_TTL_SECONDS = 60.0


def _discover_collection_jobs(force=False):
    """Map each collection to the id of its job in this workspace.

    Jobs are matched on the names the installer deploys. Discovering them here
    means a job added to the workspace works immediately: the app does not need a
    reinstall to learn a new job id, and no secret has to be written to carry it.
    """
    global _discovery_checked_at

    now = time.time()
    with _discovery_lock:
        fresh = now - _discovery_checked_at < _DISCOVERY_TTL_SECONDS
        complete = len(_discovered_jobs) == len(COLLECTION_JOBS)
        if _discovered_jobs and (complete or fresh) and not force:
            return dict(_discovered_jobs)

    found: dict[str, str] = {}
    try:
        jobs = list(_sp_workspace_client().jobs.list())
    except Exception:  # noqa: BLE001
        logger.info("could not list jobs for discovery", exc_info=True)
        jobs = []

    for kind, spec in COLLECTION_JOBS.items():
        pattern = spec['job_name_match'].lower()
        for job in jobs:
            name = ((job.settings.name if job.settings else "") or "").lower()
            if pattern in name and job.job_id:
                found[kind] = str(job.job_id)
                break

    with _discovery_lock:
        _discovered_jobs.update(found)
        _discovery_checked_at = now
        return dict(_discovered_jobs)


def _collection_job_id(kind):
    """Resolve a job id for one collection, or None when its job is absent.

    An explicitly configured id wins, so an operator can point the app at a
    specific job; otherwise the id is discovered from the workspace.
    """
    spec = COLLECTION_JOBS.get(kind)
    if not spec:
        return None
    for var in spec['env']:
        value = (os.getenv(var) or '').strip()
        if value.isdigit():
            return value
    return _discover_collection_jobs().get(kind)


def _normalise_run(run):
    """Flatten a Jobs API run into what the UI needs.

    The API carries both a legacy ``state`` and a newer ``status``; whichever is
    populated is used so this works across workspace versions.
    """
    if run is None:
        return None
    life_cycle = None
    result = None
    status = getattr(run, 'status', None)
    if status is not None:
        life_cycle = str(getattr(status, 'state', '') or '').split('.')[-1] or None
        details = getattr(status, 'termination_details', None)
        result = str(getattr(details, 'code', '') or '').split('.')[-1] or None
    if life_cycle is None:
        state = getattr(run, 'state', None)
        if state is not None:
            life_cycle = str(getattr(state, 'life_cycle_state', '') or '').split('.')[-1] or None
            result = str(getattr(state, 'result_state', '') or '').split('.')[-1] or None
    # Task counts let the UI show real progress instead of an indefinite spinner.
    tasks_total = 0
    tasks_done = 0
    current_stage = None
    for task in (getattr(run, 'tasks', None) or []):
        tasks_total += 1
        t_status = getattr(task, 'status', None)
        t_state = getattr(task, 'state', None)
        t_life = None
        if t_status is not None:
            t_life = str(getattr(t_status, 'state', '') or '').split('.')[-1] or None
        if t_life is None and t_state is not None:
            t_life = str(getattr(t_state, 'life_cycle_state', '') or '').split('.')[-1] or None
        if (t_life or '').upper() == 'TERMINATED':
            tasks_done += 1
        elif (t_life or '').upper() in _ACTIVE_RUN_STATES and current_stage is None:
            current_stage = getattr(task, 'task_key', None)

    return {
        'run_id': getattr(run, 'run_id', None),
        'state': life_cycle,
        'result': result,
        'active': (life_cycle or '').upper() in _ACTIVE_RUN_STATES,
        'start_time': getattr(run, 'start_time', None),
        'end_time': getattr(run, 'end_time', None),
        'run_page_url': getattr(run, 'run_page_url', None),
        'tasks_total': tasks_total,
        'tasks_done': tasks_done,
        'current_stage': current_stage,
    }


def _latest_run(workspace_client, job_id):
    try:
        runs = list(workspace_client.jobs.list_runs(job_id=int(job_id), limit=1))
    except Exception:  # noqa: BLE001
        logger.info("list_runs failed for job %s", job_id, exc_info=True)
        return None
    return _normalise_run(runs[0]) if runs else None


# Cached collection-run state. Keyed by nothing: there is one set of jobs and the
# lookups run as the app, so every caller sees the same answer.
_COLLECTION_CACHE_TTL = 4.0
_collection_cache = {'at': 0.0, 'runs': None}
_collection_cache_lock = threading.Lock()


def _fetch_collection_runs(workspace_client, configured):
    """Latest run per configured job, fetched concurrently."""
    import concurrent.futures

    runs = {}
    if not configured:
        return runs
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(configured)) as pool:
        futures = {
            pool.submit(_latest_run, workspace_client, job_id): kind
            for kind, job_id in configured.items()
        }
        for future in concurrent.futures.as_completed(futures):
            kind = futures[future]
            try:
                runs[kind] = future.result()
            except Exception:  # noqa: BLE001
                logger.info("latest run lookup failed for %s", kind, exc_info=True)
                runs[kind] = None
    return runs


def _cached_collection_runs(workspace_client, configured, force=False):
    """Run state for every configured job, cached briefly.

    Returns (runs, cached_age_seconds). A cache entry is not used when a run is
    active, so an in-progress collection always reports live state; that is the
    one case where a stale answer would be visible to the user.
    """
    now = time.time()
    with _collection_cache_lock:
        cached = _collection_cache['runs']
        age = now - _collection_cache['at']
        fresh = cached is not None and age < _COLLECTION_CACHE_TTL
        any_active = bool(cached) and any(
            (r or {}).get('active') for r in cached.values())
        if fresh and not force and not any_active:
            return cached, round(age, 2)

    runs = _fetch_collection_runs(workspace_client, configured)
    with _collection_cache_lock:
        _collection_cache['runs'] = runs
        _collection_cache['at'] = time.time()
    return runs, 0.0


def _invalidate_collection_cache():
    """Drop cached run state after an action that changes it."""
    with _collection_cache_lock:
        _collection_cache['runs'] = None
        _collection_cache['at'] = 0.0


@app.route('/api/collection/status')
def api_collection_status():
    """Configured collection jobs and the state of their most recent run."""
    try:
        workspace_client = _sp_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    # Each job needs its most recent run, which is a ~1s API call. Done serially
    # across five jobs that made this page take four seconds to load, so the
    # lookups are fanned out across a small thread pool instead.
    #
    # The per-job jobs.get() call that fetched the display name was also dropped:
    # the name is only used for a tooltip, and the run URL already supplies
    # everything needed to link to the job.
    configured = {
        kind: job_id
        for kind, job_id in ((k, _collection_job_id(k)) for k in COLLECTION_JOBS)
        if job_id
    }

    # Even fanned out, the run lookups cost one Jobs API round trip (~0.6s), which
    # the page cannot render without. A short cache makes revisits and the
    # poller's refreshes instant while keeping the data current enough to be
    # trusted: the TTL is deliberately shorter than the poller's fastest interval,
    # and any run in flight bypasses the cache so progress is never stale.
    refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    runs, _cached_age = _cached_collection_runs(
        workspace_client, configured, force=refresh)

    host = (os.getenv('DATABRICKS_HOST') or '').rstrip('/')
    workspace_id = (os.getenv('WORKSPACE_ID') or '').strip()

    jobs = []
    for kind, spec in COLLECTION_JOBS.items():
        job_id = configured.get(kind)
        entry = {
            'kind': kind,
            'label': spec['label'],
            'group': spec.get('group', 'Other'),
            'description': spec['description'],
            'feeds': spec.get('feeds'),
            'job_id': job_id,
            'configured': bool(job_id),
        }
        if job_id:
            entry['latest_run'] = runs.get(kind)
            # The workspace UI expects /?o=<workspace_id>#job/<id>. Prefer deriving
            # the prefix from the run URL the API returned, since that is
            # authoritative; fall back to WORKSPACE_ID when there are no runs yet.
            run_url = (entry.get('latest_run') or {}).get('run_page_url') or ''
            if '#job/' in run_url:
                entry['job_url'] = f"{run_url.split('#job/')[0]}#job/{job_id}"
            elif host:
                entry['job_url'] = (
                    f"{host}/?o={workspace_id}#job/{job_id}" if workspace_id
                    else f"{host}/#job/{job_id}"
                )
            else:
                entry['job_url'] = None
        else:
            entry['message'] = (
                f"The {spec['label']} job is not connected to this app. Re-run the "
                f"installer to manage it here, or start it from Workflows."
            )
        jobs.append(entry)
    return jsonify({'jobs': jobs, 'groups': list(COLLECTION_GROUPS), 'cached_age': _cached_age})


@app.route('/api/collection/run', methods=['POST'])
def api_collection_run():
    """Start a collection job. Body: {"kind": "permissions"|"secrets"}.

    Refuses when that job already has a run in flight, so repeated clicks cannot
    stack concurrent collections writing the same tables.
    """
    payload = request.get_json(silent=True) or {}
    kind = (payload.get('kind') or '').strip()
    if kind not in COLLECTION_JOBS:
        return jsonify({'error': f"Unknown collection '{kind}'"}), 400

    job_id = _collection_job_id(kind)
    if not job_id:
        return jsonify({
            'error': (f"The {COLLECTION_JOBS[kind]['label']} job is not bound to this "
                      f"app. Re-run the SAT installer to enable in-app collection.")
        }), 409

    try:
        workspace_client = _sp_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    existing = _latest_run(workspace_client, job_id)
    if existing and existing.get('active'):
        return jsonify({
            'error': f"{COLLECTION_JOBS[kind]['label']} is already running.",
            'latest_run': existing,
        }), 409

    try:
        started = workspace_client.jobs.run_now(job_id=int(job_id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_now failed for %s", kind)
        return jsonify({
            'error': (f"Could not start {COLLECTION_JOBS[kind]['label']}: {exc}. The "
                      f"app needs CAN_MANAGE_RUN on this job.")
        }), 500

    run_id = getattr(started, 'run_id', None)
    _invalidate_collection_cache()
    logger.info("started %s collection job=%s run_id=%s", kind, job_id, run_id)
    return jsonify({'kind': kind, 'job_id': job_id, 'run_id': run_id, 'started': True})


@app.route('/api/collection/run/<int:run_id>')
def api_collection_run_status(run_id):
    """Poll one run, so the UI can follow a collection it started."""
    try:
        workspace_client = _sp_workspace_client()
        run = workspace_client.jobs.get_run(run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500
    normalised = _normalise_run(run) or {}
    normalised['run_id'] = run_id
    return jsonify(normalised)


@app.route('/api/collection/cancel', methods=['POST'])
def api_collection_cancel():
    """Cancel the in-flight run of a collection job.

    Body: {"kind": "<collection>"} to cancel whatever that job currently has in
    flight, or {"run_id": <id>} to cancel a specific run. Cancelling by kind is
    what the UI uses, so a stuck collection can be stopped without the operator
    having to find the run id.
    """
    payload = request.get_json(silent=True) or {}
    kind = (payload.get('kind') or '').strip()
    run_id = payload.get('run_id')

    if not kind and not run_id:
        return jsonify({'error': 'kind or run_id is required'}), 400
    if kind and kind not in COLLECTION_JOBS:
        return jsonify({'error': f"Unknown collection '{kind}'"}), 400

    try:
        workspace_client = _sp_workspace_client()
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    if not run_id:
        job_id = _collection_job_id(kind)
        if not job_id:
            return jsonify({
                'error': (f"The {COLLECTION_JOBS[kind]['label']} job is not bound to "
                          f"this app.")
            }), 409
        latest = _latest_run(workspace_client, job_id)
        if not latest or not latest.get('active'):
            # Nothing running: the caller's intent already holds, so this is not an
            # error worth surfacing as one.
            return jsonify({
                'cancelled': False,
                'kind': kind,
                'message': f"{COLLECTION_JOBS[kind]['label']} is not currently running.",
            })
        run_id = latest.get('run_id')

    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'run_id must be numeric'}), 400

    try:
        workspace_client.jobs.cancel_run(run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("cancel_run failed for run_id=%s", run_id)
        return jsonify({
            'error': (f"Could not cancel run {run_id}: {exc}. The app needs "
                      f"CAN_MANAGE_RUN on this job.")
        }), 500

    _invalidate_collection_cache()
    logger.info("cancelled collection run kind=%s run_id=%s by %s",
                kind or '<by run_id>', run_id, _assistant_user())
    return jsonify({'cancelled': True, 'kind': kind or None, 'run_id': run_id})


@app.route('/api/collection/debug')
def api_collection_debug():
    """Which job-related environment variables the app can see.

    Values are reported only as digit-or-not so no configuration leaks; this is
    for confirming that a job resource binding actually reached the container.
    """
    seen = {
        name: ('<digits>' if (value or '').strip().isdigit() else '<non-numeric>')
        for name, value in sorted(os.environ.items())
        if 'JOB' in name.upper()
    }
    return jsonify({
        'job_env_vars': seen,
        'resolved': {k: _collection_job_id(k) for k in COLLECTION_JOBS},
    })


@app.route('/api/collection/schedule/<kind>')
def api_collection_schedule(kind):
    """Current schedule for a collection job."""
    if kind not in COLLECTION_JOBS:
        return jsonify({'error': f"Unknown collection '{kind}'"}), 400
    job_id = _collection_job_id(kind)
    if not job_id:
        return jsonify({'error': 'This collection is not connected to the app.'}), 409
    try:
        job = _sp_workspace_client().jobs.get(job_id=int(job_id))
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    settings = getattr(job, 'settings', None)
    schedule = getattr(settings, 'schedule', None) if settings else None
    pause = str(getattr(schedule, 'pause_status', '') or '').split('.')[-1]
    return jsonify({
        'kind': kind,
        'job_id': job_id,
        'job_name': getattr(settings, 'name', None) if settings else None,
        'cron': getattr(schedule, 'quartz_cron_expression', None) if schedule else None,
        'timezone': getattr(schedule, 'timezone_id', None) if schedule else None,
        'paused': pause.upper() == 'PAUSED',
        'has_schedule': schedule is not None,
    })


@app.route('/api/collection/schedule/<kind>', methods=['POST'])
def api_collection_schedule_update(kind):
    """Change a collection job's schedule.

    Accepts a Quartz cron expression and timezone, or {"paused": true|false} to
    suspend and resume without discarding the expression. Scoped to the two
    configured collection jobs — no other job can be modified from here.
    """
    if kind not in COLLECTION_JOBS:
        return jsonify({'error': f"Unknown collection '{kind}'"}), 400
    job_id = _collection_job_id(kind)
    if not job_id:
        return jsonify({'error': 'This collection is not connected to the app.'}), 409

    payload = request.get_json(silent=True) or {}
    try:
        client = _sp_workspace_client()
        job = client.jobs.get(job_id=int(job_id))
    except Exception as exc:  # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

    settings = getattr(job, 'settings', None)
    existing = getattr(settings, 'schedule', None) if settings else None

    cron = (payload.get('cron') or '').strip() or (
        getattr(existing, 'quartz_cron_expression', None) if existing else None)
    timezone = (payload.get('timezone') or '').strip() or (
        getattr(existing, 'timezone_id', None) if existing else None) or 'UTC'

    if not cron:
        return jsonify({'error': 'A schedule expression is required.'}), 400

    # Reject obviously malformed expressions before calling the API, so the user
    # gets a clear message instead of a generic server error.
    if len(cron.split()) not in (6, 7):
        return jsonify({
            'error': ('That schedule is not a valid Quartz expression. It needs 6 or 7 '
                      'fields, for example "0 0 8 ? * *" for daily at 08:00.')
        }), 400

    paused = payload.get('paused')
    if paused is None and existing is not None:
        paused = str(getattr(existing, 'pause_status', '') or '').split('.')[-1].upper() == 'PAUSED'
    paused = bool(paused)

    try:
        from databricks.sdk.service.jobs import CronSchedule, PauseStatus
        client.jobs.update(
            job_id=int(job_id),
            new_settings={
                'schedule': CronSchedule(
                    quartz_cron_expression=cron,
                    timezone_id=timezone,
                    pause_status=PauseStatus.PAUSED if paused else PauseStatus.UNPAUSED,
                ),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("schedule update failed for %s", kind)
        return jsonify({'error': f'Could not save the schedule: {exc}'}), 500

    logger.info("updated %s schedule cron=%r tz=%s paused=%s", kind, cron, timezone, paused)
    return jsonify({'kind': kind, 'cron': cron, 'timezone': timezone, 'paused': paused, 'saved': True})


@app.route('/api/auth/whoami')
def api_auth_whoami():
    """Report what the forwarded user token actually contains.

    Diagnostic for on-behalf-of-user problems. The app config can advertise a
    scope while the token the platform forwards does not carry it, and the two are
    indistinguishable from the error text alone. This decodes the token's own
    claims so the answer is factual rather than inferred.

    The token itself is never returned or logged — only its scope list, issue time
    and audience.
    """
    import base64
    import datetime

    token = request.headers.get('x-forwarded-access-token')
    out = {
        'obo_header_present': bool(token),
        'forwarded_email': request.headers.get('X-Forwarded-Email'),
        'app_configured_scopes': None,
        'token_claims': None,
    }

    if not token:
        out['diagnosis'] = (
            'The platform is not forwarding a user token, so the app falls back to '
            'its service principal. User authorization is not active for this app.'
        )
        return jsonify(out)

    # A Databricks OAuth token is a JWT; the payload is the middle segment.
    try:
        parts = token.split('.')
        if len(parts) < 2:
            out['diagnosis'] = 'Forwarded token is not a JWT, so its scopes cannot be read.'
            return jsonify(out)
        payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        out['diagnosis'] = f'Could not decode the forwarded token: {exc}'
        return jsonify(out)

    scope_claim = claims.get('scope') or claims.get('scp') or ''
    scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim)
    issued = claims.get('iat')
    out['token_claims'] = {
        'scopes': scopes,
        'has_sql_scope': 'sql' in scopes,
        'issued_at': (datetime.datetime.utcfromtimestamp(issued).isoformat() + 'Z') if issued else None,
        'expires_at': (datetime.datetime.utcfromtimestamp(claims['exp']).isoformat() + 'Z') if claims.get('exp') else None,
        'audience': claims.get('aud'),
        'subject': claims.get('sub'),
    }

    if 'sql' in scopes:
        out['diagnosis'] = (
            'The forwarded token carries the sql scope. If queries still fail, the '
            'cause is Unity Catalog grants rather than app authorization.'
        )
    else:
        out['diagnosis'] = (
            'The forwarded token does not carry the sql scope. Compare issued_at '
            'against when the scope was added: an older timestamp means the session '
            'predates it, a newer one means the platform is not minting the scope '
            'for this app.'
        )
    return jsonify(out)


@app.route('/api/auth/mode')
def api_auth_mode():
    """Which identity the app is querying as.

    The UI shows a notice when queries run as the app's service principal rather
    than as the signed-in user, because in that mode results are not filtered by
    the viewer's own Unity Catalog permissions.
    """
    token = request.headers.get('x-forwarded-access-token')
    per_user = bool(token) and _token_has_sql_scope(token)
    return jsonify({
        'per_user': per_user,
        'identity': 'signed-in user' if per_user else 'application service principal',
        'notice': None if per_user else (
            'Results are not filtered to your own permissions. This app is querying '
            'with its own service account because your sign-in was not granted query '
            'access. An administrator can enable it under the app settings.'
        ),
    })


if __name__ == '__main__':
    # Debug mode should be explicitly enabled via environment variable
    # Never enable debug=True in production - it exposes sensitive information
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    # Binding to 0.0.0.0 is required by the Databricks Apps runtime — the
    # platform's reverse proxy terminates SSO/OAuth and forwards traffic
    # to the container on this address. The app is not directly reachable
    # from the public internet.
    app.run(host='0.0.0.0', port=8000, debug=debug_mode)  # nosemgrep: python.flask.security.audit.app-run-param-config.avoid_app_run_with_bad_host
