"""Security assistant supervisor — one agent driving a tool-calling loop.

Model calls go through the workspace's AI Gateway (the ``/serving-endpoints``
OpenAI-compatible surface), so routing, rate limits, usage tracking and payload
logging are handled centrally rather than per-app.

Every request carries a ``usage_context`` map and a ``client_request_id``. The
gateway persists both to ``system.serving.endpoint_usage``, which is what makes
this app's traffic — and each user and conversation within it — separable for
tracing and cost attribution.

Tools are registered through a small registry; each is read-only.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from databricks.sdk import WorkspaceClient
from openai import OpenAI

from .logging_util import log_tool_call
from .system_prompt import SYSTEM_PROMPT

log = logging.getLogger("sat.supervisor")

MAX_TOOL_ITERATIONS = 8


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)


def _content_text(content) -> str:
    """Flatten a model's content into displayable text.

    Some gateway models return a plain string; others return a list of typed
    blocks (``text``, ``reasoning``, ``tool_use``). Only the text blocks are
    shown — reasoning blocks carry opaque encoded traces that must not reach the
    UI, and tool_use blocks are handled separately by the tool loop.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                continue
            # Pydantic-style objects from the SDK.
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                parts.append(str(block.text))
        return "\n\n".join(p for p in parts if p.strip())
    return str(content)


def _assistant_turn(msg) -> dict[str, Any]:
    """The assistant's tool-calling turn, in a form safe to send back.

    Rebuilding this message field-by-field drops provider-specific fields the
    model expects to see returned. Gemini attaches a ``thoughtSignature`` to each
    tool call and rejects the next request with "Function call is missing a
    thought_signature" if it does not come back, which broke every multi-tool
    Gemini conversation. Dumping the message preserves such fields without this
    code needing to know which providers use them.
    """
    try:
        turn = msg.model_dump(exclude_none=True)
    except Exception:  # noqa: BLE001 - not a pydantic model, or dump failed
        turn = None
    if not isinstance(turn, dict) or not turn.get("tool_calls"):
        # Fall back to an explicit rebuild so a dump failure cannot lose the
        # tool_calls the loop depends on.
        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        }
    turn["role"] = "assistant"
    turn.setdefault("content", msg.content or "")
    return turn


def _summarize_result(result: Any) -> str:
    """Build a short human-readable summary of a tool result for UI display."""
    if isinstance(result, dict):
        if "error" in result:
            return f"error: {result['error']}"
        if "count" in result:
            return f"{result['count']} result{'s' if result['count'] != 1 else ''}"
        for key in ("findings", "access_paths", "access_rights", "rows"):
            if isinstance(result.get(key), list):
                n = len(result[key])
                return f"{n} {key.replace('_', ' ')}"
        if isinstance(result.get("sql"), str):
            return "SQL returned"
    if isinstance(result, list):
        return f"{len(result)} rows"
    return "ok"


def _gateway_base_url() -> str:
    """Base URL for the AI Gateway's OpenAI-compatible surface.

    ``AI_GATEWAY_BASE_URL`` allows pointing at a gateway in another workspace
    (a shared, centrally-governed one); otherwise the local workspace's own
    ``/serving-endpoints`` path is used, which is the same gateway.
    """
    override = (os.environ.get("AI_GATEWAY_BASE_URL") or "").strip().rstrip("/")
    if override:
        return override if override.endswith("/serving-endpoints") else f"{override}/serving-endpoints"
    from databricks.sdk import WorkspaceClient
    return f"{WorkspaceClient().config.host.rstrip('/')}/serving-endpoints"


def _auth_token() -> str:
    """Bearer token for the gateway.

    Prefers the SDK's resolved credentials so the app works under any auth mode
    the Apps runtime provides (OAuth service principal in deployment, PAT or CLI
    profile locally). ``authenticate()`` returns the ready-made header, which
    avoids reaching for a ``.token`` attribute that is empty under OAuth.
    """
    explicit = (os.environ.get("DATABRICKS_TOKEN") or "").strip()
    if explicit:
        return explicit
    from databricks.sdk import WorkspaceClient
    cfg = WorkspaceClient().config
    header = cfg.authenticate() or {}
    value = header.get("Authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:]
    if cfg.token:
        return cfg.token
    raise RuntimeError("could not resolve a bearer token for the AI Gateway")


def _usage_context(user=None, session_id=None):
    """Attribution recorded by the AI Gateway for each request.

    The gateway persists this map to ``system.serving.endpoint_usage.usage_context``,
    which is what makes traffic from this app separable from everything else sharing
    the same endpoint — and lets token counts be attributed per user and per
    conversation for cost reporting.

    An earlier version sent a Databricks-Ai-Gateway-Request-Tags header instead;
    that is not persisted to the usage table, so it produced no queryable trace.
    """
    context = {"application": "security-analysis-tool"}
    if user:
        context["end_user"] = str(user)[:128]
    if session_id:
        context["session"] = str(session_id)[:128]
    workspace_id = (os.environ.get("WORKSPACE_ID") or "").strip()
    if workspace_id:
        context["workspace_id"] = workspace_id
    return context


def _openai_client() -> OpenAI:
    """OpenAI-compatible client bound to the workspace's AI Gateway.

    ``api_key`` is passed as a callable, which the OpenAI client re-invokes to
    refresh the credential per request. A string captured here instead would go
    stale: the Apps runtime's OAuth token lasts an hour, and this client outlives
    that, so the gateway would start answering "Invalid access token" once the
    app had been up long enough -- with no way to recover short of a redeploy.
    """
    base_url = _gateway_base_url()
    log.info("AI Gateway base_url=%s", base_url)
    return OpenAI(
        api_key=_auth_token,
        base_url=base_url,
        max_retries=3,
        timeout=180.0,
    )


# An endpoint's metadata cannot tell us whether it will serve a chat request.
# Deprecated models keep reporting task=llm/v1/chat and state READY with no
# deprecation marker anywhere, and Responses-API-only models (gpt-5-5-pro,
# gpt-5-3-codex) look identical too -- the SDK's FoundationModel does not even
# expose the api_types field that would distinguish them. So usability is
# established the only way available: by calling the endpoint the same way the
# assistant does and reading the error. Cached, so that costs one probe per
# endpoint per TTL rather than one per picker load.
_PROBE_TTL_SECONDS = 6 * 3600
_unusable: dict[str, Any] = {"checked_at": 0.0, "names": frozenset()}

# Errors that mean this endpoint can never serve a chat completion.
_FATAL_ERRORS = ("is deprecated", "only supports the responses api")

# A too-small max_tokens budget is a property of the probe, not the endpoint:
# reasoning models spend the budget before emitting content. Not disqualifying.
_PROBE_ARTIFACTS = ("max_tokens", "output limit")


def _probe_unusable(names: list[str]) -> frozenset[str]:
    """Names among ``names`` that cannot serve a chat completion.

    A probe on a retired endpoint is rejected before inference and bills nothing;
    a probe on a live one bills a single token. Only errors that are definitively
    fatal exclude a model -- a transient failure (rate limit, timeout) must not
    hide a working one, so anything unrecognised is left in the list.
    """
    if not names:
        return frozenset()

    client = _openai_client()

    def probe(name: str) -> tuple[str, bool]:
        try:
            client.chat.completions.create(
                model=name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return name, False
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if any(artifact in message for artifact in _PROBE_ARTIFACTS):
                return name, False
            fatal = any(err in message for err in _FATAL_ERRORS)
            if not fatal:
                log.info("keeping %s despite probe error: %s", name, message[:200])
            return name, fatal

    found = set()
    try:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            for name, is_unusable in pool.map(probe, names):
                if is_unusable:
                    found.add(name)
    except Exception:  # noqa: BLE001
        log.exception("endpoint probe failed; offering all endpoints")
        return frozenset()
    if found:
        log.info("excluding unusable endpoints: %s", ", ".join(sorted(found)))
    return frozenset(found)


def _unusable_names(names: list[str], refresh: bool = False) -> frozenset[str]:
    now = time.time()
    fresh = now - _unusable["checked_at"] < _PROBE_TTL_SECONDS
    if fresh and not refresh:
        return _unusable["names"]
    _unusable["names"] = _probe_unusable(names)
    _unusable["checked_at"] = now
    return _unusable["names"]


def list_chat_endpoints(refresh: bool = False):
    """Chat-capable endpoints on the gateway that actually serve a request.

    Backs the model picker, so an entry appearing here is a promise the model
    works: task and ready-state alone are not enough, since both stay unchanged
    after a model is retired.
    """
    from databricks.sdk import WorkspaceClient

    candidates: list[dict[str, Any]] = []
    try:
        for endpoint in WorkspaceClient().serving_endpoints.list():
            task = str(getattr(endpoint, "task", "") or "")
            if task and task != "llm/v1/chat":
                continue
            state = getattr(endpoint, "state", None)
            ready = str(getattr(state, "ready", "") or "").split(".")[-1].upper()
            if ready and ready != "READY":
                continue
            candidates.append({"name": endpoint.name, "task": task or "llm/v1/chat"})
    except Exception:  # noqa: BLE001
        log.exception("could not list serving endpoints")
        return []

    dead = _unusable_names([c["name"] for c in candidates], refresh=refresh)
    return sorted(
        (c for c in candidates if c["name"] not in dead),
        key=lambda e: e["name"],
    )


class Supervisor:
    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()
        self.model = os.environ.get("MODEL_ENDPOINT", "databricks-claude-opus-4-7")
        self._client: OpenAI | None = None

    def client(self) -> OpenAI:
        if self._client is None:
            self._client = _openai_client()
        return self._client

    def chat(
        self,
        session_id: str,
        user: str,
        history: list[dict[str, Any]],
        new_message: str,
        model: str | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """Run one conversational turn. Returns {reply, tool_calls, messages}.
        `history` is the prior conversation (assistant + user dicts). `messages`
        in the return value is the updated history including this turn so the
        caller can persist it for the next request."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": new_message})

        tool_calls_made: list[dict[str, Any]] = []
        client = self.client()
        # A caller-supplied endpoint wins, so the model can be switched per
        # conversation without redeploying.
        endpoint = (model or "").strip() or self.model
        usage_context = _usage_context(user=user, session_id=session_id)

        def cancelled() -> bool:
            try:
                return bool(is_cancelled and is_cancelled())
            except Exception:  # noqa: BLE001 - a broken check must not kill the turn
                return False

        def stopped_result() -> dict[str, Any]:
            log.info("turn cancelled by user after %d tool call(s)", len(tool_calls_made))
            return {
                "reply": "Stopped.",
                "tool_calls": tool_calls_made,
                "messages": messages[1:],
                "model": endpoint,
                "cancelled": True,
            }

        for iteration in range(MAX_TOOL_ITERATIONS):
            # Checked before each model call and after each tool, which are the
            # points where the loop would otherwise commit to more work.
            if cancelled():
                return stopped_result()
            t0 = time.time()
            kwargs: dict[str, Any] = {
                "model": endpoint,
                "messages": messages,
                # Recorded by the gateway in system.serving.endpoint_usage.
                "extra_body": {"usage_context": usage_context},
                # Correlates a gateway row back to this turn and iteration.
                "extra_headers": {
                    "x-databricks-client-request-id": f"sat-{session_id}-{iteration}",
                },
            }
            if self.registry.tools:
                kwargs["tools"] = self.registry.schemas()
                kwargs["tool_choice"] = "auto"
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message
            log.info(
                "model turn iter=%d finish_reason=%s elapsed=%.2fs",
                iteration, choice.finish_reason, time.time() - t0,
            )

            if not msg.tool_calls:
                reply = _content_text(msg.content)
                messages.append({"role": "assistant", "content": reply})
                log_tool_call(
                    session_id=session_id,
                    user=user,
                    tool_name="model.respond",
                    tool_args={"model": self.model, "iteration": iteration},
                    tool_result_summary=reply[:500],
                    model_response=reply,
                )
                return {
                    "reply": reply,
                    "tool_calls": tool_calls_made,
                    "messages": messages[1:],  # strip system prompt for persistence
                    "model": endpoint,
                }

            messages.append(_assistant_turn(msg))

            for tc in msg.tool_calls:
                name = tc.function.name
                summary: str
                ok: bool
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    args = {}
                    err = f"could not parse tool arguments: {e}"
                    result_text = json.dumps({"error": err})
                    summary, ok = err, False
                    log_tool_call(session_id, user, name, {"raw": tc.function.arguments}, result_text, error=err)
                else:
                    tool = self.registry.get(name)
                    if tool is None:
                        result_text = json.dumps({"error": f"unknown tool {name!r}"})
                        summary, ok = f"unknown tool {name!r}", False
                        log_tool_call(session_id, user, name, args, result_text, error="unknown tool")
                    else:
                        try:
                            result = tool.handler(**args)
                            result_text = json.dumps(result, default=str)[:8000]
                            summary, ok = _summarize_result(result), True
                            log_tool_call(session_id, user, name, args, result_text[:2000])
                        except Exception as exc:
                            log.exception("tool %s failed", name)
                            result_text = json.dumps({"error": f"tool failed: {exc}"})
                            summary, ok = f"error: {exc}", False
                            log_tool_call(session_id, user, name, args, result_text, error=str(exc))

                tool_calls_made.append({"name": name, "args": args, "summary": summary, "ok": ok})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

            if cancelled():
                return stopped_result()

        log.warning("hit MAX_TOOL_ITERATIONS=%d, returning partial", MAX_TOOL_ITERATIONS)
        return {
            "reply": ("The assistant reached its tool-call limit for this question. "
                      "Try narrowing it to a single principal, resource, or workspace."),
            "tool_calls": tool_calls_made,
            "messages": messages[1:],
            "model": endpoint,
        }


_supervisor: Supervisor | None = None
_registry = ToolRegistry()


def get_supervisor() -> Supervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = Supervisor(registry=_registry)
    return _supervisor


def register_tool(tool: Tool) -> None:
    _registry.register(tool)
