"""Audit logging for Scout tool calls.

Every tool invocation writes a row to {SAT_SCHEMA}.sat_agent_log so the
customer's security team can review what the agent did and why. The table
is created lazily on first write — no startup-time dependency on env vars,
which keeps the Flask app bootable even when schema/warehouse aren't set yet.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .sql_client import exec_statement, fq_schema, sql_escape

log = logging.getLogger("sat.audit")

LOG_TABLE = "sat_agent_log"
_table_ready = False
_table_lock = threading.Lock()


def _ensure_log_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with _table_lock:
        if _table_ready:
            return
        sql = f"""
            CREATE TABLE IF NOT EXISTS {fq_schema()}.{LOG_TABLE} (
              ts TIMESTAMP,
              session_id STRING,
              `user` STRING,
              tool_name STRING,
              tool_args STRING,
              tool_result_summary STRING,
              model_response STRING,
              error STRING
            )
            USING DELTA
            COMMENT 'Scout agent audit log — every tool call, args, and result summary'
        """
        exec_statement(sql, table="sat_agent_log")
        _table_ready = True
        log.info("sat_agent_log table ready at %s.%s", fq_schema(), LOG_TABLE)


def new_session_id() -> str:
    return uuid.uuid4().hex


def log_tool_call(
    session_id: str,
    user: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result_summary: str,
    model_response: str | None = None,
    error: str | None = None,
) -> None:
    """Insert one row describing a single tool invocation. Best-effort — failures here
    must never block a tool call from returning, so all exceptions are logged and swallowed."""
    try:
        _ensure_log_table()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "")
        args_json = json.dumps(tool_args, default=str, ensure_ascii=False)
        summary = (tool_result_summary or "")[:2000]
        response = (model_response or "")[:4000]
        err = (error or "")[:1000]
        sql = f"""
            INSERT INTO {fq_schema()}.{LOG_TABLE}
            (ts, session_id, `user`, tool_name, tool_args, tool_result_summary, model_response, error)
            VALUES (
              TIMESTAMP '{ts}',
              '{sql_escape(session_id)}',
              '{sql_escape(user)}',
              '{sql_escape(tool_name)}',
              '{sql_escape(args_json)}',
              '{sql_escape(summary)}',
              '{sql_escape(response)}',
              '{sql_escape(err)}'
            )
        """
        exec_statement(sql, table="sat_agent_log")
    except Exception as exc:
        log.exception("audit log write failed (continuing): %s", exc)
