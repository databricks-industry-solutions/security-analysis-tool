"""Permissions graph tools — read from BrickHound's vertices/edges tables to
answer "who can access X" and "what can principal Y reach".

v1 traverses one hop of group membership (User -> MemberOf -> Group ->
permission_edge -> resource). Deep nested-group resolution is deferred.
"""

from __future__ import annotations

import logging
from typing import Any

from ..sql_client import exec_query, fq_schema, sql_escape
from ..supervisor import Tool, register_tool

log = logging.getLogger("sat.tools.permissions")

V_TABLE = "brickhound_vertices"
E_TABLE = "brickhound_edges"
M_TABLE = "brickhound_collection_metadata"
MAX_LIMIT = 200

PERMISSION_EDGES_EXCLUDED = ("MemberOf", "Contains")

_ACCESS_DENIED_MARKERS = (
    "permission denied",
    "permission_denied",
    "does not have",
    "insufficient privileges",
    "insufficient_permissions",
    "requires additional privileges",
    "unauthorized",
    "not authorized",
    "use schema",
    "access denied",
)


def _access_error(exc: Exception) -> str:
    """Explain a query failure, naming the schema when it is a grants problem.

    Distinguishes "you cannot read the tables" from "there is no data", because
    the two have completely different remedies and the assistant should never
    present the first as the second.
    """
    message = str(exc)
    if any(marker in message.lower() for marker in _ACCESS_DENIED_MARKERS):
        return (
            f"Cannot read the SAT tables in {fq_schema()}: the identity running "
            f"this query lacks USE SCHEMA and SELECT on that schema. This is a "
            f"grants issue, not an absence of data. Underlying error: {message}"
        )
    return f"Could not query the permissions tables: {message}"


# Names of the run-scoped CTEs, used in place of the raw tables.
V_SCOPED = "v_run"
E_SCOPED = "e_run"


def _run_scope(schema: str, run_id: str) -> str:
    """WITH clause restricting vertices and edges to a single collection run.

    The tables are append-only across runs, so querying them directly counts
    every historical collection as if it were current -- three runs in a workspace
    reported roughly three times the real grants. Every tool must read one run.
    """
    rid = sql_escape(run_id)
    return (
        f"WITH {V_SCOPED} AS (SELECT * FROM {schema}.{V_TABLE} WHERE run_id = '{rid}'),\n"
        f"     {E_SCOPED} AS (SELECT * FROM {schema}.{E_TABLE} WHERE run_id = '{rid}')\n"
    )


def _resolve_principals(schema: str, run_id: str, needle: str) -> list[dict[str, Any]]:
    """Principals whose identifiers contain ``needle``, for disambiguation.

    An exact-match lookup returning nothing is ambiguous: the principal may hold
    no grants, or the identifier may simply not have matched. Reporting the two
    identically sends people to check grants that were never the problem, so a
    substring search establishes which case it is -- and lets a first name resolve
    to the full identity instead of failing.
    """
    # '!' is the LIKE escape rather than a backslash: a backslash is itself an
    # escape inside a SQL string literal, so ESCAPE '\' is a parse error.
    like = (needle.lower().replace("!", "!!")
            .replace("%", "!%").replace("_", "!_").replace("'", "''"))
    sql = _run_scope(schema, run_id) + f"""
        SELECT DISTINCT id, node_type, name, display_name, email
        FROM {V_SCOPED}
        WHERE node_type IN ('User', 'Group', 'ServicePrincipal',
                            'AccountUser', 'AccountServicePrincipal')
          AND (lower(COALESCE(name, '')) LIKE '%{like}%' ESCAPE '!'
            OR lower(COALESCE(display_name, '')) LIKE '%{like}%' ESCAPE '!'
            OR lower(COALESCE(email, '')) LIKE '%{like}%' ESCAPE '!')
        LIMIT 10
    """
    try:
        return exec_query(sql)
    except Exception:  # noqa: BLE001 - disambiguation is best-effort
        log.warning("principal resolution failed for %r", needle, exc_info=True)
        return []


def who_can_access(
    resource_name: str,
    resource_type: str | None = None,
    privilege: str | None = None,
    include_indirect: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Principals (users, groups, SPs) that have access to a named resource.
    Matches on vertex id, name, or display_name."""
    if not resource_name or not resource_name.strip():
        return {"error": "resource_name is required"}
    limit = max(1, min(int(limit), MAX_LIMIT))
    schema = fq_schema()
    rn = sql_escape(resource_name.strip())

    try:
        run_id = _latest_run_id()
    except Exception as exc:  # noqa: BLE001
        return {"error": _access_error(exc)}
    if not run_id:
        return {"error": "No permissions collection has completed yet."}
    scope = _run_scope(schema, run_id)

    resource_filter = (
        f"(v.id = '{rn}' OR v.name = '{rn}' OR v.display_name = '{rn}' "
        f"OR v.application_id = '{rn}')"
    )
    if resource_type:
        resource_filter = f"({resource_filter} AND v.node_type = '{sql_escape(resource_type)}')"

    privilege_filter = ""
    if privilege:
        privilege_filter = f" AND e.relationship = '{sql_escape(privilege)}'"
    else:
        excluded = ", ".join(f"'{x}'" for x in PERMISSION_EDGES_EXCLUDED)
        privilege_filter = f" AND e.relationship NOT IN ({excluded})"

    # Direct grants
    direct_sql = f"""
        SELECT
          'direct' AS access_kind,
          src_v.id           AS principal_id,
          src_v.node_type    AS principal_type,
          COALESCE(src_v.email, src_v.name, src_v.display_name, e.src) AS principal,
          e.relationship     AS privilege,
          e.permission_level AS permission_level,
          e.inherited        AS inherited,
          v.id               AS resource_id,
          v.node_type        AS resource_type,
          COALESCE(v.name, v.display_name) AS resource
        FROM {E_SCOPED} e
        JOIN {V_SCOPED} v ON e.dst = v.id
        LEFT JOIN {V_SCOPED} src_v ON src_v.id = e.src OR src_v.email = e.src
        WHERE {resource_filter}{privilege_filter}
    """

    if not include_indirect:
        sql = scope + direct_sql + f"\nLIMIT {limit}"
    else:
        # Indirect via one hop of group membership: User --MemberOf--> Group --grant--> resource
        indirect_sql = f"""
            SELECT
              'via_group'        AS access_kind,
              member.id          AS principal_id,
              member.node_type   AS principal_type,
              COALESCE(member.email, member.name, member.display_name, mem.src) AS principal,
              e.relationship     AS privilege,
              e.permission_level AS permission_level,
              e.inherited        AS inherited,
              v.id               AS resource_id,
              v.node_type        AS resource_type,
              COALESCE(v.name, v.display_name) AS resource
            FROM {E_SCOPED} e
            JOIN {V_SCOPED} v ON e.dst = v.id
            JOIN {E_SCOPED} mem ON mem.dst = e.src AND mem.relationship = 'MemberOf'
            LEFT JOIN {V_SCOPED} member ON member.id = mem.src OR member.email = mem.src
            WHERE {resource_filter}{privilege_filter}
        """
        sql = scope + f"{direct_sql}\nUNION ALL\n{indirect_sql}\nLIMIT {limit}"

    try:
        rows = exec_query(sql)
    except Exception as exc:
        log.exception("who_can_access failed")
        return {"error": _access_error(exc)}

    return {
        "resource_name": resource_name,
        "filters": {
            "resource_type": resource_type, "privilege": privilege,
            "include_indirect": include_indirect, "limit": limit,
        },
        "count": len(rows),
        "access_paths": rows,
    }


def what_can_principal_access(
    principal: str,
    principal_type: str | None = None,
    resource_type: str | None = None,
    privilege: str | None = None,
    include_indirect: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Resources a named principal can reach.
    Matches on vertex id, name, email, or display_name."""
    if not principal or not principal.strip():
        return {"error": "principal is required"}
    limit = max(1, min(int(limit), MAX_LIMIT))
    schema = fq_schema()
    p = sql_escape(principal.strip())

    try:
        run_id = _latest_run_id()
    except Exception as exc:  # noqa: BLE001
        return {"error": _access_error(exc)}
    if not run_id:
        return {"error": "No permissions collection has completed yet."}
    scope = _run_scope(schema, run_id)

    principal_filter = (
        f"(src_v.id = '{p}' OR src_v.name = '{p}' "
        f"OR src_v.email = '{p}' OR src_v.display_name = '{p}' "
        f"OR src_v.application_id = '{p}')"
    )
    matches = _resolve_principals(schema, run_id, p)
    if principal_type:
        principal_filter = f"({principal_filter} AND src_v.node_type = '{sql_escape(principal_type)}')"

    privilege_filter = ""
    if privilege:
        privilege_filter = f" AND e.relationship = '{sql_escape(privilege)}'"
    else:
        excluded = ", ".join(f"'{x}'" for x in PERMISSION_EDGES_EXCLUDED)
        privilege_filter = f" AND e.relationship NOT IN ({excluded})"

    resource_filter = ""
    if resource_type:
        resource_filter = f" AND dst_v.node_type = '{sql_escape(resource_type)}'"

    direct_sql = f"""
        SELECT
          'direct'           AS access_kind,
          src_v.id           AS principal_id,
          src_v.node_type    AS principal_type,
          COALESCE(src_v.email, src_v.name, src_v.display_name) AS principal,
          e.relationship     AS privilege,
          e.permission_level AS permission_level,
          e.inherited        AS inherited,
          dst_v.id           AS resource_id,
          dst_v.node_type    AS resource_type,
          COALESCE(dst_v.name, dst_v.display_name) AS resource
        FROM {V_SCOPED} src_v
        JOIN {E_SCOPED} e ON e.src = src_v.id OR e.src = src_v.email
        JOIN {V_SCOPED} dst_v ON dst_v.id = e.dst
        WHERE {principal_filter}{privilege_filter}{resource_filter}

        UNION ALL

        -- Implicit principals. Databricks groups like 'account users' and
        -- '_workspace_users_<id>' hold real grants but have no vertex row, so the
        -- branch above (which joins the grantee to a vertex) misses them entirely.
        -- They include every user in the account or workspace, which makes them the
        -- highest-impact grants in the graph — reporting nothing for them would be
        -- actively misleading.
        SELECT
          'direct'           AS access_kind,
          e.src              AS principal_id,
          'ImplicitGroup'    AS principal_type,
          e.src              AS principal,
          e.relationship     AS privilege,
          e.permission_level AS permission_level,
          e.inherited        AS inherited,
          dst_v.id           AS resource_id,
          dst_v.node_type    AS resource_type,
          COALESCE(dst_v.name, dst_v.display_name) AS resource
        FROM {E_SCOPED} e
        JOIN {V_SCOPED} dst_v ON dst_v.id = e.dst
        LEFT JOIN {V_SCOPED} miss
               ON miss.id = e.src OR miss.email = e.src OR miss.name = e.src
        WHERE miss.id IS NULL
          AND e.src = '{p}'{privilege_filter}{resource_filter}
    """

    if not include_indirect:
        sql = scope + direct_sql + f"\nLIMIT {limit}"
    else:
        indirect_sql = f"""
            SELECT
              'via_group'        AS access_kind,
              src_v.id           AS principal_id,
              src_v.node_type    AS principal_type,
              COALESCE(src_v.email, src_v.name, src_v.display_name) AS principal,
              e.relationship     AS privilege,
              e.permission_level AS permission_level,
              e.inherited        AS inherited,
              dst_v.id           AS resource_id,
              dst_v.node_type    AS resource_type,
              COALESCE(dst_v.name, dst_v.display_name) AS resource
            FROM {V_SCOPED} src_v
            JOIN {E_SCOPED} mem ON (mem.src = src_v.id OR mem.src = src_v.email)
                                        AND mem.relationship = 'MemberOf'
            JOIN {E_SCOPED} e ON e.src = mem.dst
            JOIN {V_SCOPED} dst_v ON dst_v.id = e.dst
            WHERE {principal_filter}{privilege_filter}{resource_filter}
        """
        sql = scope + f"{direct_sql}\nUNION ALL\n{indirect_sql}\nLIMIT {limit}"

    try:
        rows = exec_query(sql)
    except Exception as exc:
        log.exception("what_can_principal_access failed")
        return {"error": _access_error(exc)}

    # An exact-match miss and a principal with no grants both return no rows, but
    # they mean different things. Say which one this is, and if the identifier only
    # matched loosely (a first name, say) retry against the resolved identity so a
    # partial name still yields a real answer.
    if not rows and matches:
        exact = {str(m.get(f) or "").lower()
                 for m in matches for f in ("id", "name", "display_name", "email")}
        if principal.strip().lower() not in exact and len(matches) == 1:
            resolved = matches[0].get("email") or matches[0].get("id")
            if resolved and resolved.lower() != principal.strip().lower():
                retried = what_can_principal_access(
                    resolved, principal_type=principal_type,
                    resource_type=resource_type, privilege=privilege,
                    include_indirect=include_indirect, limit=limit,
                )
                retried["resolved_from"] = principal
                return retried

    result = {
        "principal": principal,
        "filters": {
            "principal_type": principal_type, "resource_type": resource_type,
            "privilege": privilege, "include_indirect": include_indirect, "limit": limit,
        },
        "count": len(rows),
        "access_rights": rows,
    }
    if not rows:
        if matches:
            result["principal_exists"] = True
            result["matched_principals"] = matches
            result["note"] = (
                "This principal exists in the permissions graph but holds no "
                "grants in the latest collection, directly or via group "
                "membership. This is a real result, not a lookup failure."
            )
        else:
            result["principal_exists"] = False
            result["note"] = (
                "No principal matching this identifier exists in the latest "
                "collection, so no access could be determined. Check the "
                "spelling, or supply an email address or vertex id."
            )
    return result




# Privileges that confer administrative control. Ownership counts: an owner can
# grant to anyone.
ADMIN_PRIVILEGES = (
    "ALL PRIVILEGES", "MANAGE", "CAN_MANAGE", "IS_OWNER",
    "CanManageSecret", "CAN_MANAGE_RUN", "MODIFY",
)


def list_high_privilege_principals(principal_type: str | None = None, limit: int = 100):
    """Principals holding administrative or ownership privileges anywhere.

    Answers estate-wide questions ("who has admin rights?") that the per-resource
    and per-principal tools cannot. Without this the assistant fell back to Genie
    for a question the graph answers directly in SQL.

    Implicit groups such as 'account users' hold real grants but have no vertex
    row, so the grantee join is a LEFT JOIN and unresolved sources are reported as
    ImplicitGroup rather than dropped.
    """
    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 100

    schema = fq_schema()
    admin_list = ", ".join("'" + p.replace("'", "''") + "'" for p in ADMIN_PRIVILEGES)

    type_filter = ""
    if principal_type:
        safe = sql_escape(str(principal_type))
        type_filter = f"AND COALESCE(p.node_type, 'ImplicitGroup') = '{safe}'"

    try:
        run_id = _latest_run_id()
    except Exception as exc:  # noqa: BLE001
        return {"error": _access_error(exc)}
    if not run_id:
        return {"error": "No permissions collection has completed yet."}

    sql = _run_scope(schema, run_id) + f"""
        SELECT COALESCE(p.display_name, p.name, e.src)      AS principal,
               COALESCE(p.node_type, 'ImplicitGroup')       AS principal_type,
               p.email                                      AS email,
               e.relationship                               AS privilege,
               COUNT(*)                                     AS grant_count,
               COUNT(DISTINCT e.dst)                        AS distinct_targets,
               MIN(e.dst)                                   AS example_target
        FROM {E_SCOPED} e
        LEFT JOIN {V_SCOPED} p ON (e.src = p.id OR e.src = p.name OR e.src = p.email)
        WHERE e.relationship IN ({admin_list})
          {type_filter}
        GROUP BY COALESCE(p.display_name, p.name, e.src),
                 COALESCE(p.node_type, 'ImplicitGroup'), p.email, e.relationship
        ORDER BY grant_count DESC
        LIMIT {limit}
    """
    try:
        rows = exec_query(sql)
    except Exception as exc:  # noqa: BLE001
        return {"error": _access_error(exc)}
    return {"count": len(rows), "run_id": run_id, "principals": rows}


def _latest_run_id():
    """Newest permissions collection run, or raise if the tables are unreadable.

    A failure here used to be swallowed and reported to the user as "no
    collection has completed yet", which is indistinguishable from an empty
    result -- so a missing UC grant looked like missing data and sent people
    looking for a collection job that had in fact already run. The last error is
    re-raised instead, so the caller can say what actually went wrong.
    """
    schema = fq_schema()
    last_error = None
    for table in (M_TABLE, V_TABLE):
        try:
            rows = exec_query(
                f"SELECT run_id FROM {schema}.{table} ORDER BY run_id DESC LIMIT 1")
            if rows:
                return rows[0].get("run_id")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return None


def register() -> None:
    register_tool(Tool(
        name="who_can_access",
        description=(
            "List principals (users, groups, service principals) that can access a "
            "named resource. Resolves by vertex id, name, or display_name. Set "
            "include_indirect=true (default) to follow one hop of group membership "
            "(User -> MemberOf -> Group -> grant). Use for questions like "
            "'who has SELECT on main.finance.revenue', 'who can manage cluster X'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "resource_name": {
                    "type": "string",
                    "description": "Resource identifier — e.g. 'main.finance.revenue' for a UC table, a vertex id, or a display name.",
                },
                "resource_type": {
                    "type": "string",
                    "description": (
                        "Optional node_type filter. Common values: Table, View, Schema, "
                        "Catalog, Cluster, Job, SecretScope, ServingEndpoint, Query, Alert."
                    ),
                },
                "privilege": {
                    "type": "string",
                    "description": (
                        "Optional privilege filter. UC grants: SELECT, MODIFY, "
                        "ALL PRIVILEGES, USE SCHEMA, USE CATALOG, EXECUTE, READ VOLUME, "
                        "CREATE TABLE. Other: MANAGE, BROWSE, CanReadSecret, CanManageSecret."
                    ),
                },
                "include_indirect": {
                    "type": "boolean",
                    "description": "Include access granted via group membership (default true).",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max rows, default 100, max {MAX_LIMIT}.",
                    "default": 100,
                },
            },
            "required": ["resource_name"],
        },
        handler=who_can_access,
    ))

    register_tool(Tool(
        name="what_can_principal_access",
        description=(
            "List resources a principal can reach. Resolves principal by email, "
            "vertex id, name, or display_name. Set include_indirect=true (default) "
            "to follow group memberships one hop. Use for questions like 'what does "
            "sp-data-pipeline have access to', 'what tables can user@x.com see'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "principal": {
                    "type": "string",
                    "description": (
                        "Principal identifier — accepts email, vertex id, name, "
                        "display name, or service principal application_id "
                        "(UUID, e.g. '254c92fa-c3e6-4f00-aa2f-1d9cef1d3fac')."
                    ),
                },
                "principal_type": {
                    "type": "string",
                    "description": "Optional filter: User, Group, AccountServicePrincipal, AccountUser.",
                },
                "resource_type": {
                    "type": "string",
                    "description": "Optional filter on the resource node_type (Table, Cluster, Job, etc).",
                },
                "privilege": {
                    "type": "string",
                    "description": "Optional privilege filter (SELECT, MODIFY, MANAGE, etc).",
                },
                "include_indirect": {
                    "type": "boolean",
                    "description": "Include access via group membership (default true).",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max rows, default 100, max {MAX_LIMIT}.",
                    "default": 100,
                },
            },
            "required": ["principal"],
        },
        handler=what_can_principal_access,
    ))

    register_tool(Tool(
        name="list_high_privilege_principals",
        description=(
            "List principals holding administrative or ownership privileges anywhere "
            "in the estate (ALL PRIVILEGES, MANAGE, CAN_MANAGE, IS_OWNER, "
            "CanManageSecret, MODIFY). Use this for estate-wide questions such as "
            "'who has admin rights', 'which service principals are over-privileged', "
            "or 'who can manage secrets' — it answers directly from the permissions "
            "graph and does not need a specific resource or principal. Implicit "
            "everyone-groups such as 'account users' are included and reported with "
            "principal_type 'ImplicitGroup'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "principal_type": {
                    "type": "string",
                    "description": (
                        "Optional filter, e.g. 'ServicePrincipal', "
                        "'AccountServicePrincipal', 'User', 'Group', 'ImplicitGroup'."
                    ),
                },
                "limit": {"type": "integer", "description": "Max rows (default 100)."},
            },
        },
        handler=list_high_privilege_principals,
    ))
