"""query_secret_scans — read the TruffleHog detections SAT's secret scanner
writes to `notebooks_secret_scan_results` and `clusters_secret_scan_results`.

These tables only get rows when secrets are actually found (or a single
"no-secrets" tracking row per run with secrets_found=0). We default to
filtering those tracking rows out so the model sees real detections.
"""

from __future__ import annotations

import logging
from typing import Any

from ..sql_client import exec_query, fq_schema, sql_escape
from ..supervisor import Tool, register_tool

log = logging.getLogger("sat.tools.secret_scans")

NOTEBOOKS_TABLE = "notebooks_secret_scan_results"
CLUSTERS_TABLE = "clusters_secret_scan_results"
MAX_LIMIT = 200

SCAN_TYPES = ("notebooks", "clusters", "both")


def query_secret_scans(
    scan_type: str = "both",
    workspace_id: str | None = None,
    detector_name: str | None = None,
    only_secrets_found: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Return detections from the secret scanner. Always pulls the most recent
    run unless run_id is supplied (not exposed in v1 — usually you want latest)."""
    if scan_type not in SCAN_TYPES:
        return {"error": f"scan_type must be one of {SCAN_TYPES}, got {scan_type!r}"}
    limit = max(1, min(int(limit), MAX_LIMIT))
    schema = fq_schema()

    results: dict[str, Any] = {
        "scan_type": scan_type,
        "filters": {
            "workspace_id": workspace_id,
            "detector_name": detector_name,
            "only_secrets_found": only_secrets_found,
            "limit": limit,
        },
    }

    if scan_type in ("notebooks", "both"):
        results["notebooks"] = _query_notebooks(schema, workspace_id, detector_name, only_secrets_found, limit)
    if scan_type in ("clusters", "both"):
        results["clusters"] = _query_clusters(schema, workspace_id, detector_name, only_secrets_found, limit)

    total = 0
    if "notebooks" in results and isinstance(results["notebooks"], dict):
        total += results["notebooks"].get("count", 0)
    if "clusters" in results and isinstance(results["clusters"], dict):
        total += results["clusters"].get("count", 0)
    results["total_detections"] = total
    return results


def _query_notebooks(schema, workspace_id, detector_name, only_secrets_found, limit) -> dict[str, Any]:
    where = []
    if only_secrets_found:
        where.append("secrets_found > 0")
    if workspace_id:
        where.append(f"workspace_id = '{sql_escape(workspace_id)}'")
    if detector_name:
        where.append(f"detector_name = '{sql_escape(detector_name)}'")
    where_clause = " AND ".join(where) if where else "1=1"

    sql = f"""
        WITH latest_run AS (
          SELECT MAX(run_id) AS run_id FROM {schema}.{NOTEBOOKS_TABLE}
        )
        SELECT
          workspace_id, notebook_id, notebook_path, notebook_name,
          detector_name, secret_sha256, secrets_found,
          CAST(scan_time AS STRING) AS scan_time
        FROM {schema}.{NOTEBOOKS_TABLE}
        WHERE {where_clause}
          AND run_id = (SELECT run_id FROM latest_run)
        ORDER BY scan_time DESC
        LIMIT {limit}
    """
    try:
        rows = exec_query(sql)
    except Exception as exc:
        log.exception("notebooks secret scan query failed")
        return {"error": f"query failed: {exc}"}
    return {"count": len(rows), "detections": rows}


def _query_clusters(schema, workspace_id, detector_name, only_secrets_found, limit) -> dict[str, Any]:
    where = []
    if only_secrets_found:
        where.append("secrets_found > 0")
    if workspace_id:
        where.append(f"workspace_id = '{sql_escape(workspace_id)}'")
    if detector_name:
        where.append(f"detector_name = '{sql_escape(detector_name)}'")
    where_clause = " AND ".join(where) if where else "1=1"

    sql = f"""
        WITH latest_run AS (
          SELECT MAX(run_id) AS run_id FROM {schema}.{CLUSTERS_TABLE}
        )
        SELECT
          workspace_id, cluster_id, cluster_name,
          config_field, config_key, detector_name,
          secret_sha256, source_file, verified, secrets_found,
          CAST(scan_time AS STRING) AS scan_time
        FROM {schema}.{CLUSTERS_TABLE}
        WHERE {where_clause}
          AND run_id = (SELECT run_id FROM latest_run)
        ORDER BY scan_time DESC
        LIMIT {limit}
    """
    try:
        rows = exec_query(sql)
    except Exception as exc:
        log.exception("clusters secret scan query failed")
        return {"error": f"query failed: {exc}"}
    return {"count": len(rows), "detections": rows}


def register() -> None:
    register_tool(Tool(
        name="query_secret_scans",
        description=(
            "Query SAT's TruffleHog-based secret scanner results. This is "
            "SEPARATE from the SAT config findings (security_checks). Use this "
            "for questions about hardcoded credentials in notebooks or cluster "
            "configurations — e.g. 'are there any leaked secrets', 'do I have "
            "hardcoded tokens in my code', 'which notebooks have AWS keys'. "
            "Returns only detections (rows with secrets_found > 0) by default. "
            "Tables: notebooks_secret_scan_results (TruffleHog over notebook "
            "source) and clusters_secret_scan_results (TruffleHog over cluster "
            "env vars and init scripts). Always pulls the latest scan run."
        ),
        parameters={
            "type": "object",
            "properties": {
                "scan_type": {
                    "type": "string",
                    "enum": list(SCAN_TYPES),
                    "description": (
                        "Which scan results to query. 'notebooks' searches notebook source "
                        "for secrets, 'clusters' searches cluster env vars / init scripts, "
                        "'both' (default) returns both."
                    ),
                    "default": "both",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Filter detections to one workspace. Omit to search across all scanned workspaces.",
                },
                "detector_name": {
                    "type": "string",
                    "description": "Filter by TruffleHog detector (e.g. 'AWS', 'AzureBatch', 'GenericSecret', 'PrivateKey').",
                },
                "only_secrets_found": {
                    "type": "boolean",
                    "description": "If true (default) excludes the per-run no-secrets tracking rows.",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max rows per scan type. Default 50, max {MAX_LIMIT}.",
                    "default": 50,
                },
            },
            "required": [],
        },
        handler=query_secret_scans,
    ))
