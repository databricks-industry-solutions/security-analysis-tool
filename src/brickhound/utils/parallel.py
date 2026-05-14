"""Parallel permission-fetch helper for BrickHound data collection.

Issue: https://github.com/databricks-industry-solutions/security-analysis-tool/issues/348
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def _unwrap_enum(value):
    """Return value.value if value has a .value attribute (SDK enum), else value as-is.

    Mirrors the notebook's safe_get() behavior so edges produced by this helper
    match the strings the original code wrote to Delta (e.g. "CAN_MANAGE" rather
    than the PermissionLevel enum object).
    """
    if value is not None and hasattr(value, "value"):
        return value.value
    return value


def collect_permission_edges(
    workspace_client: Any,
    request_object_type: str,
    object_specs: Iterable[tuple[str, str]],
    max_workers: int = 20,
    edge_properties: Optional[str] = None,
) -> list[dict]:
    """Fetch permissions for many objects in parallel and return edge dicts.

    Args:
        workspace_client: Databricks SDK WorkspaceClient.
        request_object_type: SDK permissions API resource type
            (e.g. "clusters", "jobs", "sql/warehouses", "pipelines").
        object_specs: Iterable of (object_id, dst_node_id) tuples. ``object_id``
            is the value passed to ``permissions.get()``; ``dst_node_id`` is the
            value used in the edge dict ``dst`` field. They are often the same
            but not always (e.g. pipelines use a raw id for the API and a
            ``pipeline:{id}`` prefix for the graph dst).
        max_workers: Maximum concurrent permission-fetch threads.
        edge_properties: Optional pre-serialized JSON string to attach to every
            edge's ``properties`` field. ``None`` matches the single-workspace
            edge shape; pass ``safe_json({"workspace_id": ...})`` for the
            multi-workspace shape.

    Returns:
        List of edge dicts. Each dict matches the existing notebook edge
        schema: ``{src, dst, relationship, permission_level, inherited,
        properties, created_at}``. Objects whose permission fetch raises an
        exception are silently skipped (matches existing notebook behavior).
    """
    specs = list(object_specs)
    if not specs:
        return []
    edges: list[dict] = []
    now = datetime.now

    def _fetch_and_build(spec: tuple[str, str]) -> list[dict]:
        object_id, dst = spec
        try:
            perms = workspace_client.permissions.get(request_object_type, object_id)
        # Matches the existing notebook contract: per-object permission failures
        # are silently dropped from the graph, not propagated to the caller.
        except Exception as exc:
            logger.debug(
                "permissions.get(%s, %s) failed: %s", request_object_type, object_id, exc
            )
            return []
        if not perms or not perms.access_control_list:
            return []
        result: list[dict] = []
        for acl in perms.access_control_list:
            principal = acl.user_name or acl.group_name or acl.service_principal_name
            if not principal or not acl.all_permissions:
                continue
            for perm in acl.all_permissions:
                level = _unwrap_enum(getattr(perm, "permission_level", None))
                inherited = _unwrap_enum(getattr(perm, "inherited", False))
                result.append({
                    "src": principal,
                    "dst": dst,
                    "relationship": level,
                    "permission_level": level,
                    "inherited": inherited,
                    "properties": edge_properties,
                    "created_at": now(),
                })
        return result

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(specs)))) as pool:
        futures = [pool.submit(_fetch_and_build, s) for s in specs]
        for fut in as_completed(futures):
            edges.extend(fut.result())
    return edges
