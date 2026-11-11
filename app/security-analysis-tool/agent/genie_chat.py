"""Genie-backed assistant.

The security assistant is a Databricks AI/BI Genie space configured over the
SAT results schema. This module is the thin client the app's chat endpoint
calls: it starts or continues a Genie conversation, waits for the answer, and
flattens it into {answer, sql, rows} for the UI.

Multi-turn is native to Genie — each app session maps to one Genie
``conversation_id``, so follow-up questions keep context. The caller supplies
the WorkspaceClient, which is built per request from the signed-in user's token
(OBO) so Genie answers under that user's Unity Catalog permissions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("sat.genie_chat")

MAX_RESULT_ROWS = 200


def space_id() -> str:
    return (os.environ.get("GENIE_SPACE_ID") or "").strip()


def answer(client, question: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Run one turn against the Genie space.

    Starts a new conversation when ``conversation_id`` is None, otherwise
    continues the existing one. Returns a dict the chat endpoint serializes
    directly; ``conversation_id`` in the result is what the caller persists for
    the next turn.
    """
    sid = space_id()
    if not sid:
        return {"error": "No Genie space is configured for the assistant."}
    if not question or not question.strip():
        return {"error": "question is required"}

    genie = client.genie
    try:
        if conversation_id:
            msg = genie.create_message_and_wait(
                space_id=sid, conversation_id=conversation_id, content=question)
        else:
            msg = genie.start_conversation_and_wait(space_id=sid, content=question)
    except Exception as exc:  # noqa: BLE001
        log.exception("genie turn failed")
        return {"error": f"Genie request failed: {exc}"}

    conv_id = getattr(msg, "conversation_id", None) or conversation_id
    out: dict[str, Any] = {
        "answer": "",
        "conversation_id": conv_id,
        "message_id": getattr(msg, "id", None),
        "sql": None,
        "description": None,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
    }

    text_parts: list[str] = []
    for att in (getattr(msg, "attachments", None) or []):
        text = getattr(att, "text", None)
        if text and getattr(text, "content", None):
            text_parts.append(text.content)
        query = getattr(att, "query", None)
        if query:
            out["sql"] = getattr(query, "query", None)
            out["description"] = getattr(query, "description", None)
            # Genie often puts its prose summary on the query attachment.
            if getattr(query, "description", None):
                text_parts.append(query.description)
            try:
                result = _fetch_result(client, sid, conv_id, msg.id, att.attachment_id)
                cols, rows, count, truncated = _extract_rows(result)
                out["columns"], out["rows"] = cols, rows
                out["row_count"], out["truncated"] = count, truncated
            except Exception as exc:  # noqa: BLE001
                log.exception("genie result fetch failed")
                out["description"] = (out["description"] or "") + f"\n(result fetch failed: {exc})"

    out["answer"] = "\n\n".join(p for p in text_parts if p and p.strip()) or (
        "Genie did not return a text answer." if not out["sql"]
        else "Genie ran a query; see the results below.")
    return out


def _fetch_result(client, space_id, conversation_id, message_id, attachment_id):
    """Fetch an attachment's query result, tolerating SDK method renames.

    The SDK has renamed this call across versions; try each known name, then
    fall back to the REST endpoint, whose shape has been stable.
    """
    for name in ("get_message_attachment_query_result",
                 "get_message_query_result_by_attachment",
                 "get_message_query_result"):
        fn = getattr(client.genie, name, None)
        if fn is None:
            continue
        try:
            return fn(space_id=space_id, conversation_id=conversation_id,
                      message_id=message_id, attachment_id=attachment_id)
        except TypeError:
            try:
                return fn(space_id, conversation_id, message_id, attachment_id)
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001
            continue
    path = (f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}"
            f"/messages/{message_id}/attachments/{attachment_id}/query-result")
    return _RawResult(client.api_client.do("GET", path))


def _extract_rows(result) -> tuple[list[str], list[dict[str, Any]], int, bool]:
    statement = getattr(result, "statement_response", None)
    if not statement or not getattr(statement, "result", None):
        return [], [], 0, False
    data = statement.result.data_array or []
    columns: list[str] = []
    man = getattr(statement, "manifest", None)
    if man and getattr(man, "schema", None) and man.schema.columns:
        columns = [getattr(c, "name", None) or f"col{i}" for i, c in enumerate(man.schema.columns)]
    truncated = len(data) > MAX_RESULT_ROWS
    rows = []
    for row in data[:MAX_RESULT_ROWS]:
        if columns and len(columns) == len(row):
            rows.append(dict(zip(columns, row)))
        else:
            rows.append({f"col{i}": v for i, v in enumerate(row)})
    return columns, rows, len(data), truncated


# --- REST-fallback shims: adapt the raw dict to the SDK object shape ----------
class _RawResult:
    def __init__(self, raw: dict[str, Any]):
        self.statement_response = _SR((raw or {}).get("statement_response") or {})


class _SR:
    def __init__(self, sr): self.result = _R(sr.get("result")) if sr.get("result") else None; self.manifest = _M(sr.get("manifest")) if sr.get("manifest") else None


class _R:
    def __init__(self, r): self.data_array = r.get("data_array") or []


class _M:
    def __init__(self, m): self.schema = _S(m.get("schema")) if m.get("schema") else None


class _S:
    def __init__(self, s): self.columns = [_C(c) for c in (s.get("columns") or [])]


class _C:
    def __init__(self, c): self.name = c.get("name")
