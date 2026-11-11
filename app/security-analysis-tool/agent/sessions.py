"""sat_agent_sessions table — persists each assistant thread across reloads.

A session stores the Genie ``conversation_id`` (so follow-up turns continue the
same Genie conversation) plus a transcript of the turns for the sidebar. Both
live base64-encoded in the single ``messages`` column, so no schema migration is
needed. Best-effort: failures are logged and the assistant still answers.
"""

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
            COMMENT 'Assistant thread persistence: Genie conversation id + transcript, one row per session'
        """
        exec_statement(sql, table="sat_agent_sessions")
        _table_ready = True


def _encode(payload: dict[str, Any]) -> str:
    """JSON then base64 — base64 is safe in any SQL string-literal escape mode."""
    raw = json.dumps(payload, default=str, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _decode(stored: str | None) -> dict[str, Any]:
    """Return {conversation_id, messages}. Tolerates the legacy bare-list format."""
    empty = {"conversation_id": None, "messages": []}
    if not stored:
        return empty
    s = stored.strip()
    obj: Any = None
    # Legacy rows stored a bare JSON list of messages; newer rows store a dict.
    try:
        obj = json.loads(s) if s.startswith(("{", "[")) else json.loads(
            base64.b64decode(s.encode("ascii")).decode("utf-8"))
    except Exception:  # noqa: BLE001
        try:
            obj = json.loads(base64.b64decode(s.encode("ascii")).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to decode session payload: %s", exc)
            return empty
    if isinstance(obj, list):
        return {"conversation_id": None, "messages": obj}
    if isinstance(obj, dict):
        return {"conversation_id": obj.get("conversation_id"),
                "messages": obj.get("messages") or []}
    return empty


def load(session_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    """Return (conversation_id, messages) for a session, or (None, []) if absent."""
    try:
        _ensure_table()
        rows = exec_query(
            f"SELECT messages FROM {fq_schema()}.{SESSIONS_TABLE} "
            f"WHERE session_id = '{sql_escape(session_id)}' "
            f"ORDER BY updated_at DESC LIMIT 1"
        )
        if not rows:
            return None, []
        payload = _decode(rows[0].get("messages"))
        return payload["conversation_id"], payload["messages"]
    except Exception as exc:  # noqa: BLE001
        log.warning("session load failed for %s: %s", session_id, exc)
        return None, []


def save(session_id: str, user: str, conversation_id: str | None,
         messages: list[dict[str, Any]]) -> None:
    """Persist a thread. Raises on failure — caller decides whether to swallow."""
    _ensure_table()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "")
    payload = _encode({"conversation_id": conversation_id, "messages": messages})
    log.info("session save: session_id=%s user=%s conv=%s turns=%d",
             session_id, user, conversation_id, len(messages))
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
    for m in messages:
        if m.get("role") == "user":
            content = (m.get("content") or "").strip().replace("\n", " ")
            if content:
                return content[:60] + ("…" if len(content) > 60 else "")
    return "(new conversation)"


def list_sessions(user: str, limit: int = 30) -> list[dict[str, Any]]:
    """Recent sessions for a user, newest first, each with a sidebar title."""
    _ensure_table()
    rows = exec_query(
        f"SELECT session_id, CAST(updated_at AS STRING) AS updated_at, messages "
        f"FROM {fq_schema()}.{SESSIONS_TABLE} "
        f"WHERE `user` = '{sql_escape(user)}' "
        f"ORDER BY updated_at DESC LIMIT {max(1, min(int(limit), 100))}"
    )
    out = []
    for row in rows:
        payload = _decode(row.get("messages"))
        out.append({
            "session_id": row.get("session_id"),
            "updated_at": row.get("updated_at"),
            "title": _title_from_messages(payload["messages"]),
        })
    return out


def delete(session_id: str, user: str) -> bool:
    """Delete one session, scoped by user so a customer can't drop another's."""
    try:
        _ensure_table()
        exec_statement(
            f"DELETE FROM {fq_schema()}.{SESSIONS_TABLE} "
            f"WHERE session_id = '{sql_escape(session_id)}' "
            f"AND `user` = '{sql_escape(user)}'",
            table="sat_agent_sessions",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("session delete failed for %s: %s", session_id, exc)
        return False
