"""query_genie — proxies a natural-language question to the customer's Genie
space configured over security_analysis.*.

We start a fresh conversation per call. Multi-turn investigation lives in
Scout's supervisor loop, not inside Genie — that way Scout retains control
of which questions get asked and Genie is a stateless SQL surface.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from databricks.sdk import WorkspaceClient

from ..supervisor import Tool, register_tool

log = logging.getLogger("sat.tools.genie")

MAX_RESULT_ROWS = 100


def query_genie(question: str) -> dict[str, Any]:
    """Ask a natural-language question against the SAT Genie space."""
    space_id = os.environ.get("GENIE_SPACE_ID")
    if not space_id:
        return {"error": "GENIE_SPACE_ID not configured; cannot use Genie tool"}
    if not question or not question.strip():
        return {"error": "question is required"}

    wc = WorkspaceClient()

    try:
        msg = wc.genie.start_conversation_and_wait(space_id=space_id, content=question)
    except Exception as exc:
        log.exception("genie start_conversation_and_wait failed")
        return {"error": f"genie call failed: {exc}"}

    response: dict[str, Any] = {
        "question": question,
        "status": str(getattr(msg, "status", "") or ""),
        "text": None,
        "sql": None,
        "description": None,
        "rows": [],
        "row_count": 0,
        "truncated": False,
    }

    if not msg.attachments:
        response["text"] = "Genie returned no attachments."
        return response

    for att in msg.attachments:
        if getattr(att, "text", None) and getattr(att.text, "content", None):
            response["text"] = att.text.content
        if getattr(att, "query", None):
            q = att.query
            response["sql"] = getattr(q, "query", None)
            response["description"] = getattr(q, "description", None)
            try:
                result = _fetch_attachment_result(
                    wc, space_id, msg.conversation_id, msg.id, att.attachment_id
                )
                rows, count, truncated = _extract_rows(result)
                response["rows"] = rows
                response["row_count"] = count
                response["truncated"] = truncated
            except Exception as exc:
                log.exception("genie result fetch failed")
                response["error"] = f"genie result fetch failed: {exc}"

    return response


def _fetch_attachment_result(wc: WorkspaceClient, space_id: str, conversation_id: str,
                             message_id: str, attachment_id: str) -> Any:
    """Resilient query-result fetch.

    The Databricks SDK has renamed this method across versions. We try each
    known name in order, then fall back to a raw REST call. The REST endpoint
    has been stable across all SDK versions that ship with Databricks Apps.
    """
    candidates = (
        "get_message_attachment_query_result",
        "get_message_query_result_by_attachment",
        "get_message_query_result",
    )
    for name in candidates:
        fn = getattr(wc.genie, name, None)
        if fn is None:
            continue
        try:
            log.info("genie result fetch using wc.genie.%s", name)
            return fn(
                space_id=space_id,
                conversation_id=conversation_id,
                message_id=message_id,
                attachment_id=attachment_id,
            )
        except TypeError:
            # Older signature may not accept attachment_id as kwarg
            try:
                return fn(space_id, conversation_id, message_id, attachment_id)
            except Exception as exc:
                log.debug("genie %s positional call failed: %s", name, exc)
                continue
        except Exception as exc:
            log.debug("genie %s failed: %s", name, exc)
            continue

    # REST fallback — endpoint shape is stable.
    path = (
        f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}"
        f"/messages/{message_id}/attachments/{attachment_id}/query-result"
    )
    log.info("genie result fetch via REST: %s", path)
    raw = wc.api_client.do("GET", path)
    return _RawGenieResult(raw)


class _RawGenieResult:
    """Adapts the REST response dict to the same shape as the SDK object so
    _extract_rows doesn't have to branch."""
    def __init__(self, raw: dict[str, Any]):
        sr = raw.get("statement_response") or {}
        self.statement_response = _StatementResponseShim(sr)


class _StatementResponseShim:
    def __init__(self, sr: dict[str, Any]):
        self.result = _ResultShim(sr.get("result")) if sr.get("result") else None
        self.manifest = _ManifestShim(sr.get("manifest")) if sr.get("manifest") else None


class _ResultShim:
    def __init__(self, r: dict[str, Any]):
        self.data_array = r.get("data_array") or []


class _ManifestShim:
    def __init__(self, m: dict[str, Any]):
        self.schema = _SchemaShim(m.get("schema")) if m.get("schema") else None


class _SchemaShim:
    def __init__(self, s: dict[str, Any]):
        self.columns = [_ColShim(c) for c in (s.get("columns") or [])]


class _ColShim:
    def __init__(self, c: dict[str, Any]):
        self.name = c.get("name")


def _extract_rows(result: Any) -> tuple[list[dict[str, Any]], int, bool]:
    """Pull a list-of-dicts out of a Genie query result, truncated to MAX_RESULT_ROWS."""
    statement = getattr(result, "statement_response", None)
    if not statement or not statement.result:
        return [], 0, False
    data = statement.result.data_array or []
    columns: list[str] = []
    if statement.manifest and statement.manifest.schema and statement.manifest.schema.columns:
        for col in statement.manifest.schema.columns:
            columns.append(getattr(col, "name", None) or f"col{len(columns)}")
    rows = []
    truncated = len(data) > MAX_RESULT_ROWS
    for row in data[:MAX_RESULT_ROWS]:
        if columns and len(columns) == len(row):
            rows.append(dict(zip(columns, row)))
        else:
            rows.append({f"col{i}": v for i, v in enumerate(row)})
    return rows, len(data), truncated


def register() -> None:
    register_tool(Tool(
        name="query_genie",
        description=(
            "Ask a natural-language SQL question against the SAT Genie space (configured "
            "over security_analysis.* tables). Use this for free-form aggregations, "
            "joins, or any question that isn't a structured findings filter. "
            "Examples: 'how many high-severity findings per workspace this week', "
            "'which checks have failed in every run for 30 days'. "
            "Prefer query_findings for simple finding lookups; use query_genie when "
            "you need ad-hoc SQL the structured tool can't express."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural-language question about SAT data.",
                },
            },
            "required": ["question"],
        },
        handler=query_genie,
    ))
