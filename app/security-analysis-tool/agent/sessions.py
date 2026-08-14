"""sat_agent_sessions table — persists conversation history across page reloads
and app restarts. Best-effort: failures are logged and the in-memory cache
keeps working."""

from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from .sql_client import exec_query, exec_statement, fq_schema, sql_escape

log = logging.getLogger("sat.sessions")

SESSIONS_TABLE = "sat_agent_sessions"
_table_ready = False
_lock = threading.Lock()


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with _lock:
        if _table_ready:
            return
        sql = f"""
            CREATE TABLE IF NOT EXISTS {fq_schema()}.{SESSIONS_TABLE} (
              session_id STRING,
              `user` STRING,
              updated_at TIMESTAMP,
              messages STRING
            )
            USING DELTA
            COMMENT 'Scout conversation thread persistence (one row per session, overwritten on each turn)'
        """
        exec_statement(sql, table="sat_agent_sessions")
        _table_ready = True


def load(session_id: str) -> list[dict[str, Any]]:
    try:
        _ensure_table()
        rows = exec_query(
            f"SELECT messages FROM {fq_schema()}.{SESSIONS_TABLE} "
            f"WHERE session_id = '{sql_escape(session_id)}' "
            f"ORDER BY updated_at DESC LIMIT 1"
        )
        if not rows:
            return []
        return _decode_messages(rows[0].get("messages"))
    except Exception as exc:
        log.warning("session load failed for %s: %s", session_id, exc)
        return []


def _encode_messages(messages: list[dict[str, Any]]) -> str:
    """JSON-encode then base64-encode. Base64 contains only [A-Za-z0-9+/=],
    none of which are special in any SQL string-literal escape mode, so the
    round-trip is bulletproof regardless of Spark's `escapedStringLiterals`
    setting."""
    raw = json.dumps(messages, default=str, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_messages(stored: str | None) -> list[dict[str, Any]]:
    if not stored:
        return []
    # Backwards-compat: tolerate rows written before base64 by trying raw JSON first.
    s = stored.strip()
    if s.startswith("["):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    try:
        raw = base64.b64decode(s.encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        log.warning("failed to decode session messages: %s", exc)
        return []


def save(session_id: str, user: str, messages: list[dict[str, Any]]) -> None:
    """Persist a conversation. Raises on failure — caller decides whether to
    swallow. Messages are base64-encoded to survive SQL string-literal parsing."""
    _ensure_table()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "")
    payload = _encode_messages(messages)
    log.info(
        "session save: session_id=%s user=%s messages=%d bytes_b64=%d",
        session_id, user, len(messages), len(payload),
    )
    exec_statement(
        f"DELETE FROM {fq_schema()}.{SESSIONS_TABLE} "
        f"WHERE session_id = '{sql_escape(session_id)}'",
        table="sat_agent_sessions",
    )
    exec_statement(
        f"INSERT INTO {fq_schema()}.{SESSIONS_TABLE} (session_id, `user`, updated_at, messages) "
        f"VALUES ('{sql_escape(session_id)}', '{sql_escape(user)}', "
        f"TIMESTAMP '{ts}', '{payload}')",
        table="sat_agent_sessions",
    )


def _title_from_messages(messages: list[dict[str, Any]]) -> str:
    """First user turn, truncated. Falls back to '(new investigation)' if empty."""
    for m in messages:
        if m.get("role") == "user":
            content = (m.get("content") or "").strip().replace("\n", " ")
            if content:
                return content[:60] + ("…" if len(content) > 60 else "")
    return "(new investigation)"


def list_sessions(user: str, limit: int = 30) -> list[dict[str, Any]]:
    """Recent sessions for a user, newest first. Each row carries an extracted
    title for the sidebar so the UI doesn't have to parse messages itself."""
    _ensure_table()
    log.info("session list for user=%r", user)
    rows = exec_query(
        f"SELECT session_id, CAST(updated_at AS STRING) AS updated_at, messages "
        f"FROM {fq_schema()}.{SESSIONS_TABLE} "
        f"WHERE `user` = '{sql_escape(user)}' "
        f"ORDER BY updated_at DESC LIMIT {max(1, min(int(limit), 100))}"
    )
    log.info("session list returned %d rows for user=%r", len(rows), user)

    sessions = []
    for row in rows:
        msgs = _decode_messages(row.get("messages"))
        sessions.append({
            "session_id": row.get("session_id"),
            "updated_at": row.get("updated_at"),
            "title": _title_from_messages(msgs),
        })
    return sessions


def delete(session_id: str, user: str) -> bool:
    """Delete a single session (scoped by user so one customer can't drop another's)."""
    try:
        _ensure_table()
        exec_statement(
            f"DELETE FROM {fq_schema()}.{SESSIONS_TABLE} "
            f"WHERE session_id = '{sql_escape(session_id)}' "
            f"AND `user` = '{sql_escape(user)}'",
        table="sat_agent_sessions",
    )
        return True
    except Exception as exc:
        log.warning("session delete failed for %s: %s", session_id, exc)
        return False
