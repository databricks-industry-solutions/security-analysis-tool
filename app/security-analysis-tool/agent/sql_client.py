"""SQL access for the security assistant's tools.

Runs read queries against the same warehouse and schema the rest of the app uses,
and rejects anything that is not a read. The assistant reaches data only through
registered tools, and those tools reach the warehouse only through here — so
read-only is a property of this module rather than a convention each tool has to
remember.

The two tables the app owns (conversation history and the tool-call audit trail)
are written through ``exec_statement``, which refuses any other target.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

log = logging.getLogger("sat.agent.sql")

# Tables the assistant layer may write. Everything else in the schema is read-only.
APP_OWNED_TABLES = ("sat_agent_sessions", "sat_agent_log")

_READ_PREFIXES = ("select", "with", "explain", "describe", "desc", "show")
_COMMENT_RE = re.compile(r"(--[^\n]*)|(/\*.*?\*/)", re.DOTALL)


class SqlClientError(RuntimeError):
    pass


def _strip_comments(sql: str) -> str:
    return _COMMENT_RE.sub(" ", sql or "").strip()


def assert_read_only(sql: str) -> None:
    """Raise unless ``sql`` is a single read statement."""
    body = _strip_comments(sql)
    if not body:
        raise SqlClientError("empty statement")
    trimmed = body.rstrip().rstrip(";")
    if ";" in trimmed:
        raise SqlClientError("multiple statements are not allowed")
    first = trimmed.lstrip("( \t\r\n").split(None, 1)
    keyword = first[0].lower() if first else ""
    if keyword not in _READ_PREFIXES:
        raise SqlClientError(
            f"only read statements are permitted; got '{keyword.upper() or '?'}'"
        )


def assert_app_owned_write(sql: str, table: str) -> None:
    """Raise unless ``sql`` writes only to an app-owned table.

    Two checks, because either alone is bypassable: the declared target must be on
    the allowlist, and the statement text must not name any other schema table.
    """
    if table not in APP_OWNED_TABLES:
        raise SqlClientError(
            f"'{table}' is not an app-owned table; writes are limited to "
            f"{', '.join(APP_OWNED_TABLES)}"
        )
    lowered = _strip_comments(sql).lower()
    if ";" in lowered.rstrip().rstrip(";"):
        raise SqlClientError("multiple statements are not allowed")
    for name in re.findall(r"[a-z0-9_]+\.[a-z0-9_]+\.`?([a-z0-9_]+)`?", lowered):
        if name not in APP_OWNED_TABLES:
            raise SqlClientError(f"statement references non-app-owned table '{name}'")


def _config() -> tuple[str, str, str]:
    """Return (catalog, schema, warehouse_id) from the app's environment."""
    raw = os.environ.get("SAT_SCHEMA") or os.environ.get("BRICKHOUND_SCHEMA")
    if not raw:
        raise SqlClientError("SAT_SCHEMA / BRICKHOUND_SCHEMA is not set")
    parts = [p.strip().strip("`").strip('"') for p in raw.split(".")]
    parts = [p for p in parts if p]
    if len(parts) != 2:
        raise SqlClientError(f"schema must be 'catalog.schema', got {raw!r}")
    warehouse = os.environ.get("WAREHOUSE_ID") or os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse:
        raise SqlClientError("WAREHOUSE_ID is not set")
    return parts[0], parts[1], warehouse


def workspace_client():
    """Client for the assistant's queries, as the calling user where possible.

    The assistant reads the same security tables as the rest of the app, so it
    must read them as the same identity: querying as the app's service principal
    would show every user the full dataset regardless of their own UC grants.
    Databricks Apps forwards the user's token on the request, and Flask's request
    context is available here because tool handlers run inside the request that
    triggered them.

    Outside a request context (startup, background work) there is no user to act
    for and the app's own identity is used.
    """
    from databricks.sdk import WorkspaceClient

    token = None
    try:
        from flask import request

        token = request.headers.get("x-forwarded-access-token")
    except Exception:  # noqa: BLE001 - no request context, or Flask absent
        token = None

    if token:
        # auth_type="pat" and an explicit host are required: without them the SDK
        # sees both this token and the app SP's injected OAuth env vars and fails
        # with "more than one authorization method configured".
        return WorkspaceClient(
            host=os.environ.get("DATABRICKS_HOST"),
            token=token,
            auth_type="pat",
        )
    return _app_client()


def _app_client():
    """Client for the app's own identity, ignoring any forwarded user token."""
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def warehouse_id() -> str:
    return _config()[2]


def schema_parts() -> tuple[str, str]:
    catalog, schema, _ = _config()
    return catalog, schema


def fq_schema() -> str:
    catalog, schema = schema_parts()
    return f"`{catalog}`.`{schema}`"


def fq_table(name: str) -> str:
    catalog, schema = schema_parts()
    return f"`{catalog}`.`{schema}`.`{name}`"


def _run(sql: str, wait_timeout: str, as_user: bool = True) -> Any:
    from databricks.sdk.service.sql import StatementState

    catalog, schema, warehouse = _config()
    client = workspace_client() if as_user else _app_client()
    result = client.statement_execution.execute_statement(
        warehouse_id=warehouse,
        catalog=catalog,
        schema=schema,
        statement=sql,
        wait_timeout=wait_timeout,
    )
    state = result.status.state if result.status else None
    while state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.5)
        result = client.statement_execution.get_statement(result.statement_id)
        state = result.status.state if result.status else None
    if state != StatementState.SUCCEEDED:
        message = "unknown execution error"
        if result.status and result.status.error:
            message = result.status.error.message or message
        raise SqlClientError(f"query failed ({state}): {message}")
    return result


def exec_query(sql: str, wait_timeout: str = "50s") -> list[dict[str, Any]]:
    """Run a read query and return dict rows."""
    assert_read_only(sql)
    result = _run(sql, wait_timeout)
    if not result.result or not result.manifest:
        return []
    columns = [c.name for c in result.manifest.schema.columns]
    return [dict(zip(columns, row)) for row in (result.result.data_array or [])]


def exec_statement(sql: str, *, table: str, wait_timeout: str = "30s") -> None:
    """Write to one of the app's own tables. Refuses any other target.

    Runs as the app rather than the calling user: these are the app's own
    conversation-history and audit tables, and an audit trail that only records
    the actions of users who happen to hold write grants is not an audit trail.
    """
    assert_app_owned_write(sql, table)
    _run(sql, wait_timeout, as_user=False)


def sql_escape(value: str) -> str:
    """Escape a string for use inside a single-quoted SQL literal."""
    return str(value).replace("'", "''")
