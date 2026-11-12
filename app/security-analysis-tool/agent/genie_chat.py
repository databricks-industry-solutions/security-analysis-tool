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
    import time

    def _run_once():
        """One start-or-continue turn plus a poll to a terminal state.

        Polls get_message ourselves rather than the SDK's *_and_wait helper,
        which raises a generic "failed to reach COMPLETED" and hides Genie's own
        error. Returns (message, conversation_id).
        """
        if conversation_id:
            started = genie.create_message(
                space_id=sid, conversation_id=conversation_id, content=question)
        else:
            started = genie.start_conversation(space_id=sid, content=question)
        cid = getattr(started, "conversation_id", None) or conversation_id
        mid = getattr(started, "message_id", None) or getattr(started, "id", None)
        m = None
        deadline = time.time() + 150
        while time.time() < deadline:
            m = genie.get_message(space_id=sid, conversation_id=cid, message_id=mid)
            if str(getattr(m, "status", "") or "").split(".")[-1] in (
                    "COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
                break
            time.sleep(3)
        return m, cid

    # Genie occasionally returns a transient FAILED with no error detail; retry
    # once when that happens. A FAILED carrying a real error (bad SQL, insufficient
    # privileges) is deterministic, so it is surfaced immediately rather than retried.
    msg = conv_id = None
    for attempt in range(2):
        try:
            msg, conv_id = _run_once()
        except Exception as exc:  # noqa: BLE001
            log.exception("genie turn failed")
            return {"error": f"Genie request failed: {exc}"}
        status = str(getattr(msg, "status", "") or "").split(".")[-1]
        if status == "COMPLETED":
            break
        detail = getattr(msg, "error", None)
        for att in (getattr(msg, "attachments", None) or []):
            q = getattr(att, "query", None)
            if q and getattr(q, "error", None):
                detail = detail or q.error
        if status == "FAILED" and not detail and attempt == 0:
            log.warning("genie returned a transient FAILED (no detail); retrying once")
            continue
        detail = str(detail) if detail else (status or "unknown")
        log.error("genie message not COMPLETED: status=%s detail=%s", status, detail)
        return {"error": f"Genie could not answer that ({detail}).",
                "conversation_id": conv_id}

    conv_id = getattr(msg, "conversation_id", None) or conv_id
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


def list_conversations(client) -> list[dict[str, Any]]:
    """The signed-in user's past conversations in the space, newest first.

    Genie scopes conversations to the caller, so under OBO each user sees only
    their own. ``title`` is the opening question Genie recorded for the thread.
    """
    sid = space_id()
    if not sid:
        return []
    out = []
    token = None
    for _ in range(50):  # page cap, just in case next_page_token never clears
        res = client.genie.list_conversations(space_id=sid, page_token=token)
        for c in (getattr(res, "conversations", None) or []):
            out.append({
                "conversation_id": getattr(c, "conversation_id", None),
                "title": (getattr(c, "title", None) or "Conversation"),
                "created": getattr(c, "created_timestamp", None),
            })
        token = getattr(res, "next_page_token", None)
        if not token:
            break
    out.sort(key=lambda x: x["created"] or 0, reverse=True)
    return [c for c in out if c["conversation_id"]]


def conversation_turns(client, conversation_id: str) -> list[dict[str, Any]]:
    """Flatten a stored conversation into render-ready turns (oldest first).

    Each Genie message is one user turn plus its answer; the SQL query result
    rows are not re-fetched here (they are historical and costly) -- the text
    answer and the SQL are enough to re-read the thread.
    """
    sid = space_id()
    if not sid:
        return []
    # Page through all messages -- Genie returns them newest-first and may
    # paginate a long thread, so collect every page and reorder below.
    msgs = []
    token = None
    for _ in range(50):
        res = client.genie.list_conversation_messages(
            space_id=sid, conversation_id=conversation_id, page_token=token)
        msgs.extend(getattr(res, "messages", None) or [])
        token = getattr(res, "next_page_token", None)
        if not token:
            break
    # Order oldest-first when a timestamp is available; otherwise trust API order.
    if msgs and getattr(msgs[0], "created_timestamp", None) is not None:
        msgs.sort(key=lambda m: getattr(m, "created_timestamp", 0) or 0)
    turns: list[dict[str, Any]] = []
    for m in msgs:
        question = getattr(m, "content", None)
        if question:
            turns.append({"role": "user", "content": question})
        text_parts, sql = [], None
        for att in (getattr(m, "attachments", None) or []):
            text = getattr(att, "text", None)
            if text and getattr(text, "content", None):
                text_parts.append(text.content)
            query = getattr(att, "query", None)
            if query:
                sql = getattr(query, "query", None)
                if getattr(query, "description", None):
                    text_parts.append(query.description)
        answer_text = "\n\n".join(p for p in text_parts if p and p.strip())
        if answer_text or sql:
            turns.append({"role": "assistant", "content": answer_text, "sql": sql})
    return turns


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
