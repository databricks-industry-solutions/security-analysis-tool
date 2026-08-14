"""query_audit — read system.access.audit for security investigation.

Designed to be cheap and safe:
- Time window is mandatory (default 24h, hard cap 30d) so queries always prune
  on event_date, which is the partition column on system.access.audit.
- Hard LIMIT (default 100, max 500) — Scout never returns full result sets to
  the model.
- Workspace scoping defaults to the workspace the app is running in, derived
  from WorkspaceClient.config.host. The LLM can override with an explicit
  workspace_id, but only one at a time.
- Every string input is validated with a regex before SQL interpolation.
  No path lets the model inject arbitrary identifiers or values.
- request_params is summarized (keys only), not returned verbatim — these
  blobs can contain sensitive values like notebook paths or query text.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any

from databricks.sdk import WorkspaceClient

from ..sql_client import exec_query, sql_escape
from ..supervisor import Tool, register_tool

log = logging.getLogger("sat.tools.audit")

AUDIT_TABLE = "system.access.audit"
MAX_LIMIT = 500
MAX_DAYS = 30
DEFAULT_DAYS = 1

_RE_WORKSPACE_ID = re.compile(r"^\d{6,20}$")
_RE_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")   # action_name / service_name
_RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_SINCE_REL = re.compile(r"^(\d{1,4})([hd])$")
_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# user_identity.email in system.access.audit contains the application_id
# (UUID format) for service principal events, so accept either an email or a
# UUID here. Anything else fails validation.
_RE_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_RE_IP = re.compile(r"^[A-Fa-f0-9:.]{3,45}$")  # rough IPv4/IPv6 acceptance

STATUS_VALUES = ("success", "failure", "any")


@lru_cache(maxsize=1)
def calling_workspace_id() -> str | None:
    """Resolve the workspace_id Scout is running in, cached for the process
    lifetime. Tries three sources in order:

    1. Env var `WORKSPACE_ID` or `DATABRICKS_WORKSPACE_ID` — explicit override
       or auto-injected by some Databricks Apps runtimes.
    2. SDK config (`wc.config.workspace_id`) — populated on newer SDK versions.
    3. SQL function `current_workspace_id()` — works in recent DBSQL runtimes.

    Returns None if all three fail; audit queries then run unscoped with a
    scope_warning so the user knows.
    """
    # 1. Env var
    for var in ("WORKSPACE_ID", "DATABRICKS_WORKSPACE_ID"):
        wid = os.environ.get(var, "").strip()
        if wid and wid.isdigit():
            log.info("calling_workspace_id resolved from env %s", var)
            return wid

    # 2. SDK config
    try:
        wc = WorkspaceClient()
        wid = getattr(wc.config, "workspace_id", None)
        if wid:
            log.info("calling_workspace_id resolved from SDK config")
            return str(wid)
    except Exception as exc:
        log.debug("SDK config workspace_id unavailable: %s", exc)

    # 3. SQL function
    try:
        from ..sql_client import warehouse_id, workspace_client
        wc = workspace_client()
        result = wc.statement_execution.execute_statement(
            warehouse_id=warehouse_id(),
            statement="SELECT current_workspace_id() AS wid",
            wait_timeout="10s",
        )
        if result.result and result.result.data_array:
            wid = result.result.data_array[0][0]
            if wid is not None:
                log.info("calling_workspace_id resolved via SQL function")
                return str(wid)
    except Exception as exc:
        log.debug("SQL current_workspace_id() unavailable: %s", exc)

    log.warning("calling_workspace_id could not be resolved through any source")
    return None


def _parse_since(since: str) -> str:
    """Return a SQL expression for the lower bound on event_date. Always
    constrains to <= MAX_DAYS in the past."""
    if not since:
        return f"current_date() - INTERVAL {DEFAULT_DAYS} DAYS"
    since = since.strip()
    if _RE_DATE.match(since):
        # Caller provided an ISO date. Refuse if it's older than MAX_DAYS.
        return (
            f"GREATEST(DATE('{since}'), current_date() - INTERVAL {MAX_DAYS} DAYS)"
        )
    m = _RE_SINCE_REL.match(since)
    if not m:
        raise ValueError(f"since must be like '24h', '7d', or 'YYYY-MM-DD', got {since!r}")
    n, unit = int(m.group(1)), m.group(2)
    days = n if unit == "d" else max(1, (n + 23) // 24)
    days = min(days, MAX_DAYS)
    return f"current_date() - INTERVAL {days} DAYS"


def query_audit(
    action_name: str | None = None,
    service_name: str | None = None,
    user: str | None = None,
    workspace_id: str | None = None,
    source_ip: str | None = None,
    status: str = "any",
    since: str = "24h",
    limit: int = 100,
) -> dict[str, Any]:
    """Query system.access.audit with strict validation, time-bounded and
    workspace-scoped by default."""
    limit = max(1, min(int(limit), MAX_LIMIT))

    # Validate every string input before interpolating into SQL.
    where: list[str] = []
    try:
        since_clause = _parse_since(since)
    except ValueError as e:
        return {"error": str(e)}

    where.append(f"event_date >= {since_clause}")

    effective_workspace_id = workspace_id or calling_workspace_id()
    if effective_workspace_id:
        if not _RE_WORKSPACE_ID.match(effective_workspace_id):
            return {"error": f"workspace_id must be 6-20 digits, got {workspace_id!r}"}
        where.append(f"workspace_id = '{effective_workspace_id}'")
    # If neither resolved, we let the query run unscoped but warn — security
    # teams reviewing audit data across an account might legitimately want this.
    unscoped = effective_workspace_id is None

    if action_name:
        if not _RE_IDENT.match(action_name):
            return {"error": f"action_name must be an alphanumeric identifier, got {action_name!r}"}
        where.append(f"action_name = '{action_name}'")

    if service_name:
        if not _RE_IDENT.match(service_name):
            return {"error": f"service_name must be an alphanumeric identifier, got {service_name!r}"}
        where.append(f"service_name = '{service_name}'")

    if user:
        if not (_RE_EMAIL.match(user) or _RE_UUID.match(user)):
            return {"error": f"user must be an email address or UUID (for service principals), got {user!r}"}
        where.append(f"user_identity.email = '{sql_escape(user)}'")

    if source_ip:
        if not _RE_IP.match(source_ip):
            return {"error": f"source_ip must look like an IPv4 or IPv6 address, got {source_ip!r}"}
        where.append(f"source_ip_address = '{sql_escape(source_ip)}'")

    if status not in STATUS_VALUES:
        return {"error": f"status must be one of {STATUS_VALUES}, got {status!r}"}
    if status == "success":
        where.append("response.status_code BETWEEN 200 AND 299")
    elif status == "failure":
        where.append("(response.status_code IS NULL OR response.status_code < 200 OR response.status_code >= 300)")

    sql = f"""
        SELECT
          CAST(event_time AS STRING)        AS event_time,
          workspace_id                      AS workspace_id,
          user_identity.email               AS user,
          service_name                      AS service_name,
          action_name                       AS action_name,
          source_ip_address                 AS source_ip,
          response.status_code              AS status_code,
          response.error_message            AS error_message,
          map_keys(request_params)          AS request_param_keys,
          audit_level                       AS audit_level
        FROM {AUDIT_TABLE}
        WHERE {' AND '.join(where)}
        ORDER BY event_time DESC
        LIMIT {limit}
    """

    try:
        rows = exec_query(sql)
    except Exception as exc:
        log.exception("query_audit failed")
        return {"error": f"query failed: {exc}"}

    return {
        "count": len(rows),
        "scope": {
            "workspace_id": effective_workspace_id,
            "scope_warning": (
                "no workspace_id supplied and the calling workspace could not be "
                "resolved — returned rows may span multiple workspaces"
            ) if unscoped else None,
            "since": since,
            "filters": {
                "action_name": action_name, "service_name": service_name,
                "user": user, "source_ip": source_ip, "status": status,
                "limit": limit,
            },
        },
        "audit_events": rows,
    }


def register() -> None:
    register_tool(Tool(
        name="query_audit",
        description=(
            "Query Databricks audit logs (system.access.audit). Use for "
            "questions about logins, API calls, data access, who did what "
            "and when. Always time-bounded (default 24h, max 30d) and "
            "scoped to the calling workspace unless the caller overrides "
            "workspace_id. Returns events ordered newest first. "
            "Common action_names: 'login', 'tokenLogin', 'aadTokenLogin', "
            "'createCluster', 'startCluster', 'downloadQueryResult', "
            "'downloadLargeResults', 'createTable', 'getTable', "
            "'updatePermissions'. Use status='failure' to find errors "
            "or denied attempts (e.g. failed logins). "
            "IMPORTANT: account-level events (logins, account API calls) "
            "have workspace_id=0 by design — they are not scoped to any "
            "single workspace. If the user asks 'were there failed logins "
            "to THIS workspace', explain that logins are account-level and "
            "show all account-level login failures for users who can access "
            "this workspace. To find activity inside a specific workspace, "
            "filter on workspace-level actions like 'createCluster', "
            "'startCluster', 'downloadQueryResult', etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action_name": {
                    "type": "string",
                    "description": "Exact action name. Examples: 'login', 'tokenLogin', 'createCluster', 'downloadQueryResult', 'getTable'.",
                },
                "service_name": {
                    "type": "string",
                    "description": "Service name filter. Examples: 'accounts', 'workspace', 'unityCatalog', 'sqlanalytics', 'clusters', 'jobs'.",
                },
                "user": {
                    "type": "string",
                    "description": (
                        "Filter to events by this identity. Use an email address "
                        "for human users, or the service principal's application_id "
                        "(UUID format) for SPs — system.access.audit puts the "
                        "application_id into user_identity.email for SP events."
                    ),
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Workspace ID (digits only). If omitted, defaults to the workspace Scout is running in.",
                },
                "source_ip": {
                    "type": "string",
                    "description": "Filter to events from this source IP address.",
                },
                "status": {
                    "type": "string",
                    "enum": list(STATUS_VALUES),
                    "description": "Filter by HTTP status: 'success' (2xx), 'failure' (non-2xx or null), or 'any'.",
                    "default": "any",
                },
                "since": {
                    "type": "string",
                    "description": (
                        f"Time window (max {MAX_DAYS}d). Formats: relative like '24h' "
                        f"or '7d', or an absolute date like '2026-05-01'. Default '24h'."
                    ),
                    "default": "24h",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max rows, default 100, max {MAX_LIMIT}.",
                    "default": 100,
                },
            },
            "required": [],
        },
        handler=query_audit,
    ))
