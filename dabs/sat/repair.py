"""Bring an existing SAT installation back to a working state.

The failure this exists for: a Databricks App runs as a service principal the
platform creates and owns. If that principal is deleted, the app cannot run and
cannot be repaired in place -- a redeploy fails with "service principal does not
exist or is deleted", and the platform's own instruction is to delete the app.
Recreating it is therefore unavoidable, but everything around it is not: the
resource bindings, the Unity Catalog grants and the job ids can all be restored
automatically instead of by hand.

Deleting the SP also silently revokes every grant it held, and a schema owned by
that principal is left with no valid owner. Those are the parts that made manual
recovery slow and easy to get wrong, so they are handled here.

Run through ``install.sh --repair``. Safe to run repeatedly: every step checks
current state first and only acts when something is actually wrong.
"""

from __future__ import annotations

import time

APP_NAME = "security-analysis"
SCOPE_NAME = "sat_scope"

# Scopes the app requests when forwarding the caller's token. These bind when the
# app is CREATED; adding them to a running app does not rebind its OAuth client,
# which is why a repair recreates the app rather than patching it.
USER_API_SCOPES = ["sql", "serving.serving-endpoints"]

# Grants the app's own service principal needs. SELECT and USE SCHEMA to read the
# collection results; CREATE TABLE and MODIFY for the two tables the app owns
# (conversation history and the tool-call audit trail).
APP_SP_SCHEMA_PRIVILEGES = ("USE SCHEMA", "SELECT", "CREATE TABLE", "MODIFY")


class RepairError(RuntimeError):
    pass


def _sql(client, warehouse_id: str, statement: str, catalog: str | None = None):
    """Run one statement, raising with the server's message on failure."""
    from databricks.sdk.service.sql import StatementState

    kwargs = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "50s",
    }
    if catalog:
        kwargs["catalog"] = catalog
    result = client.statement_execution.execute_statement(**kwargs)
    state = result.status.state if result.status else None
    while state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.5)
        result = client.statement_execution.get_statement(result.statement_id)
        state = result.status.state if result.status else None
    if state != StatementState.SUCCEEDED:
        message = "unknown error"
        if result.status and result.status.error:
            message = result.status.error.message or message
        raise RepairError(message)
    rows = []
    if result.result and result.result.data_array:
        rows = result.result.data_array
    return rows


def _service_principal_valid(client, application_id: str | None) -> bool:
    """True if ``application_id`` resolves to a live service principal.

    An app keeps reporting its principal's id after that principal is deleted, so
    the id alone proves nothing and has to be looked up.
    """
    if not application_id:
        return False
    try:
        matches = list(client.service_principals.list(
            filter=f'applicationId eq "{application_id}"'))
    except Exception:  # noqa: BLE001
        return False
    return any(getattr(sp, "active", False) for sp in matches)


# Collection jobs, mapping the bundle's resource key to the secret the app reads.
# The app resolves job ids from these secrets because Databricks Apps binds job
# permissions but does not inject job ids.
JOB_ID_SECRET_KEYS = {
    "brickhound_data_collection": "permissions-job-id",
    "sat_secrets": "secrets-job-id",
    "brickhound_share_to_account": "shared-to-account-job-id",
    "brickhound_privileged_non_idp": "privileged-non-idp-job-id",
    "brickhound_denylist_candidates": "denylist-job-id",
    "sat_code_scanner": "code-scanner-job-id",
}

# Job names as deployed, used to resolve ids when the bundle summary is
# unavailable. Kept beside the resource keys so the two cannot drift apart.
JOB_NAME_PATTERNS = {
    "brickhound_data_collection": "Data Collection",
    "sat_secrets": "Secrets Scanner",
    "brickhound_share_to_account": "Shared to Account Users",
    "brickhound_privileged_non_idp": "Privileged Non-IdP",
    "brickhound_denylist_candidates": "Denylist Candidates",
    "sat_code_scanner": "Code Scanner",
}


def record_job_ids(client, scope_name="sat_scope"):
    """Write the deployed collection jobs' ids into the secret scope.

    Called after the bundle deploy, when the jobs exist. The app reads these to
    enable its in-app run controls; without them every collection shows as "not
    connected" even though the jobs were created.

    Matching is by job name because the bundle's own resource keys are not
    exposed through the Jobs API. Returns the keys it could not resolve so the
    installer can report them rather than failing silently.
    """
    unresolved = []
    try:
        jobs = list(client.jobs.list())
    except Exception:  # noqa: BLE001
        return list(JOB_ID_SECRET_KEYS.values())

    for resource_key, secret_key in JOB_ID_SECRET_KEYS.items():
        pattern = JOB_NAME_PATTERNS[resource_key]
        match = next(
            (j for j in jobs
             if pattern.lower() in ((j.settings.name if j.settings else "") or "").lower()),
            None,
        )
        if match is None or match.job_id is None:
            unresolved.append(secret_key)
            continue
        try:
            client.secrets.put_secret(
                scope=scope_name, key=secret_key, string_value=str(match.job_id))
        except Exception:  # noqa: BLE001
            unresolved.append(secret_key)
    return unresolved


def diagnose(client, app_name: str = APP_NAME) -> dict:
    """Report what is wrong, without changing anything."""
    from databricks.sdk.errors import NotFound

    report = {
        "app_name": app_name,
        "app_exists": False,
        "app_sp": None,
        "app_sp_valid": False,
        "needs_recreate": False,
        "duplicate_apps": [],
    }

    try:
        app = client.apps.get(name=app_name)
        report["app_exists"] = True
        report["app_sp"] = app.service_principal_client_id
        report["app_sp_valid"] = _service_principal_valid(
            client, app.service_principal_client_id)
        report["needs_recreate"] = not report["app_sp_valid"]
    except NotFound:
        report["needs_recreate"] = True
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)

    # Extra SAT apps are reported but never deleted automatically: an app may be
    # serving users, and that is not a call this script should make silently.
    try:
        for other in client.apps.list():
            name = other.name or ""
            if name != app_name and ("security-analysis" in name or "sat" in name.lower()):
                report["duplicate_apps"].append(name)
    except Exception:  # noqa: BLE001
        pass

    return report


def restore_grants(client, warehouse_id: str, uc_schema: str,
                   app_sp: str, owner: str | None = None) -> list[str]:
    """Re-apply the Unity Catalog grants the app needs.

    Deleting a service principal revokes everything granted to it, so these must
    be re-applied against the *current* principal after any recreate. Returns a
    list of the actions taken, for reporting.

    ``owner`` sets the schema owner. A schema owned by an individual service
    principal is left ownerless when that principal is deleted, which is what
    turns a recoverable outage into a manual repair -- so this should be a group
    or a durable user.
    """
    actions = []
    catalog = uc_schema.split(".")[0].strip("`")
    schema_fq = uc_schema

    if owner:
        try:
            _sql(client, warehouse_id,
                 f"ALTER SCHEMA {schema_fq} OWNER TO `{owner}`")
            actions.append(f"set schema owner to {owner}")
        except RepairError as exc:
            actions.append(f"could not set schema owner: {exc}")

    try:
        _sql(client, warehouse_id,
             f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{app_sp}`")
        actions.append(f"granted USE CATALOG on {catalog}")
    except RepairError as exc:
        actions.append(f"could not grant USE CATALOG: {exc}")

    for privilege in APP_SP_SCHEMA_PRIVILEGES:
        try:
            _sql(client, warehouse_id,
                 f"GRANT {privilege} ON SCHEMA {schema_fq} TO `{app_sp}`")
            actions.append(f"granted {privilege} on {schema_fq}")
        except RepairError as exc:
            actions.append(f"could not grant {privilege}: {exc}")

    return actions


def verify(client, app_name: str, warehouse_id: str, uc_schema: str) -> list[dict]:
    """Prove the repair worked, rather than assuming it did.

    Each check is the same operation the app performs at runtime, so a pass here
    means the corresponding feature works.
    """
    checks = []

    def record(label, fn):
        try:
            detail = fn()
            checks.append({"label": label, "ok": True, "detail": detail})
        except Exception as exc:  # noqa: BLE001
            checks.append({"label": label, "ok": False, "detail": str(exc)[:300]})

    def check_app():
        app = client.apps.get(name=app_name)
        sp = app.service_principal_client_id
        if not _service_principal_valid(client, sp):
            raise RepairError(f"service principal {sp} is not valid")
        scopes = list(app.user_api_scopes or [])
        if "sql" not in scopes:
            raise RepairError(
                f"user_api_scopes is {scopes or 'empty'}; 'sql' is required for "
                f"per-user data access")
        return f"running as {sp}, scopes {scopes}"

    def check_reads():
        rows = _sql(client, warehouse_id,
                    f"SELECT COUNT(*) FROM {uc_schema}.brickhound_vertices")
        return f"permissions graph readable ({rows[0][0] if rows else 0} rows)"

    def check_alerts():
        if not hasattr(client, "alerts_v2"):
            raise RepairError("databricks-sdk is older than 0.51; alerts unavailable")
        list(client.alerts_v2.list_alerts())
        return "alerts API reachable"

    def check_jobs():
        missing = []
        for key in JOB_ID_SECRET_KEYS.values():
            try:
                value = client.secrets.get_secret(scope=SCOPE_NAME, key=key)
                import base64
                raw = base64.b64decode(value.value or "").decode().strip()
                if not raw.isdigit():
                    missing.append(key)
            except Exception:  # noqa: BLE001
                missing.append(key)
        if missing:
            raise RepairError("job ids not recorded: " + ", ".join(missing))
        return "all five collection job ids recorded"

    record("App and service principal", check_app)
    record("Unity Catalog reads", check_reads)
    record("Secret-scanning alerts", check_alerts)
    record("Collection job bindings", check_jobs)
    return checks

def repair(client, profile: str, uc_schema: str, warehouse_id: str,
           owner: str | None = None, app_name: str = APP_NAME,
           source_code_path: str | None = None) -> bool:
    """Restore a broken installation. Returns True if it ends up healthy.

    Ordered so that each step's precondition is already satisfied: the app is
    recreated first (a new service principal invalidates every grant), then grants
    are applied to whatever principal the app now runs as, then the result is
    verified against the same operations the app performs at runtime.
    """
    print("Checking the installation...")
    report = diagnose(client, app_name)

    if report.get("duplicate_apps"):
        print("  Other SAT apps found: " + ", ".join(report["duplicate_apps"]))
        print("  Not touching them; delete any you no longer want from Compute -> Apps.")

    if report["needs_recreate"]:
        if report["app_exists"]:
            print(f"  {app_name} runs as a service principal that no longer exists.")
            print("  The platform cannot rebind one, so the app is recreated. Its URL,")
            print("  source code, jobs and data are unaffected.")
            _recreate_app(client, app_name, source_code_path)
        else:
            print(f"  {app_name} does not exist; creating it.")
            _create_app(client, app_name, _default_resources(uc_schema, warehouse_id),
                        source_code_path)
        report = diagnose(client, app_name)
        if not report["app_sp_valid"]:
            print("  Could not obtain a working service principal for the app.")
            return False
        print(f"  App running as {report['app_sp']}.")
    else:
        print(f"  App is healthy, running as {report['app_sp']}.")

    print("Restoring Unity Catalog grants...")
    for action in restore_grants(client, warehouse_id, uc_schema,
                                 app_sp=report["app_sp"], owner=owner):
        print(f"  {action}")

    print("Recording collection job ids...")
    unresolved = record_job_ids(client)
    if unresolved:
        print("  Could not resolve: " + ", ".join(unresolved))
    else:
        print("  All five recorded.")

    print("Verifying...")
    checks = verify(client, app_name, warehouse_id, uc_schema)
    for check in checks:
        print(f"  [{'ok' if check['ok'] else 'FAILED'}] {check['label']}: {check['detail']}")

    healthy = all(c["ok"] for c in checks)
    print()
    if healthy:
        print("Repair complete. The app is serving.")
    else:
        print("Repair finished with problems above. The app's Settings page shows the")
        print("same checks with the remedy for each.")
    return healthy


def _app_payload(app_name, resources, description=None):
    return {
        "name": app_name,
        "description": description or (
            "Security Analysis Tool - permissions analysis, secret scanning, "
            "and security assistant"),
        # Must be set at creation: adding scopes to an existing app does not
        # rebind its OAuth client, so per-user data access would stay broken.
        "user_api_scopes": list(USER_API_SCOPES),
        "resources": resources,
    }


def _create_app(client, app_name, resources, source_code_path=None):
    from databricks.sdk.service.apps import App

    client.apps.create(app=App.from_dict(_app_payload(app_name, resources)))
    _wait_for_app(client, app_name)
    if source_code_path:
        client.apps.deploy(app_name=app_name, source_code_path=source_code_path)


def _recreate_app(client, app_name, source_code_path=None):
    """Delete and recreate, preserving the existing resource bindings.

    The bindings are read back from the live app first so a repair does not have
    to reconstruct them, which would risk dropping one.
    """
    existing = client.apps.get(name=app_name)
    resources = [r.as_dict() for r in (existing.resources or [])]
    description = existing.description
    path = source_code_path or (
        existing.active_deployment.source_code_path
        if existing.active_deployment else None)

    client.apps.delete(name=app_name)
    for _ in range(60):
        try:
            client.apps.get(name=app_name)
            time.sleep(5)
        except Exception:  # noqa: BLE001 - gone is what we are waiting for
            break

    from databricks.sdk.service.apps import App
    client.apps.create(app=App.from_dict(
        _app_payload(app_name, resources, description)))
    _wait_for_app(client, app_name)
    if path:
        client.apps.deploy(app_name=app_name, source_code_path=path)


def _wait_for_app(client, app_name, timeout_seconds=900):
    """Wait until the app leaves its starting state."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            app = client.apps.get(name=app_name)
            state = str(getattr(getattr(app, "compute_status", None), "state", "") or "")
            if state.split(".")[-1] in ("ACTIVE", "ERROR", "STOPPED"):
                return state
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)
    return "TIMEOUT"


def _default_resources(uc_schema, warehouse_id):
    """Bindings for an app being created from scratch during a repair."""
    secrets = [
        "analysis_schema_name", "sql-warehouse-id", "model-endpoint",
        "genie-space-id", "workspace-id", "permissions-job-id", "secrets-job-id",
        "shared-to-account-job-id", "privileged-non-idp-job-id", "denylist-job-id",
    ]
    resources = [{
        "name": "warehouse",
        "sql_warehouse": {"id": warehouse_id, "permission": "CAN_USE"},
    }]
    resources.extend({
        "name": key,
        "secret": {"scope": SCOPE_NAME, "key": key, "permission": "READ"},
    } for key in secrets)
    return resources
