import json
import os
import re
import subprocess

from databricks.sdk import WorkspaceClient
from inquirer import Checkbox, Confirm, List, Password, Text, list_input, prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from sat.utils import (
    cloud_validation,
    get_catalogs,
    get_profiles,
    get_warehouses,
    loading,
    uc_enabled,
)

# ---------------------------------------------------------------------------
# Deferrable value catalog
# ---------------------------------------------------------------------------
# Each entry: (logical_name, display_label, default_physical_key, cloud_filter)
#
# - logical_name         key used in secret_key_names JSON and code
# - display_label        shown in the checkbox and key-name prompts
# - default_physical_key default Databricks secret key string
# - cloud_filter         None = all clouds; "azure"/"aws"/"gcp" = only that cloud
#
# Excluded intentionally:
#   sql_warehouse_id — still used as a notebook scope-fallback for the Setup/5
#     dashboard import, but no longer a secret the app needs (WAREHOUSE_ID now
#     resolves from the sql_warehouse resource directly via valueFrom: "warehouse").
#   use_sp_auth — derived from cloud type, never user-facing.
DEFERRABLE_VALUES = [
    ("client_secret",        "Service principal secret (required)", "client-secret",        None),
    ("account_id",           "Databricks Account ID",               "account-console-id",   None),
    ("client_id",            "Service principal client ID",         "client-id",             None),
    ("tenant_id",            "Azure tenant ID",                     "tenant-id",             "azure"),
    ("subscription_id",      "Azure subscription ID",               "subscription-id",       "azure"),
    ("proxies",              "Proxy configuration",                  "proxies",              None),
    ("analysis_schema_name", "Analysis schema (catalog.schema)",    "analysis_schema_name", None),
]

# Logical names that must always stay in the scope (cannot be deselected).
_LOCKED_LOGICALS = ["client_secret"]


def _deferrable_choices(cloud: str):
    """Return (label, logical_name) tuples filtered for the active cloud."""
    return [
        (label, logical)
        for logical, label, _key, cloud_filter in DEFERRABLE_VALUES
        if cloud_filter is None or cloud_filter == cloud
    ]


def _locked_for_cloud(cloud: str):
    """Return physical choice tuples that must remain selected."""
    choices = dict(_deferrable_choices(cloud))
    # locked list must contain the same objects that will appear in choices
    return [
        (label, logical)
        for logical, label, _key, cloud_filter in DEFERRABLE_VALUES
        if logical in _LOCKED_LOGICALS and (cloud_filter is None or cloud_filter == cloud)
    ]


def _default_physical_key(logical: str) -> str:
    for lg, _label, key, _cf in DEFERRABLE_VALUES:
        if lg == logical:
            return key
    return logical


# ---------------------------------------------------------------------------
# Question builders — split so tests can import build_questions() directly
# and exercise the real list without a hand-copied duplicate.
# ---------------------------------------------------------------------------

def build_questions(client: WorkspaceClient) -> list:
    """Build the complete inquirer question list for the SAT installer.

    This is the single source of truth.  ``form()`` calls this and passes the
    result to ``inquirer.prompt()``.  Tests import this directly to run
    ordering assertions and ignore-callback coverage without a TTY.
    """
    from sat.utils import cloud_type as _cloud_type  # local import avoids circular

    cloud = _cloud_type(client)

    # ---- A1 fix: cloud_validation() returns a BOOL, not a callable. ----
    # Evaluate once; close over the bool value in lambdas so we never call it.
    skip_azure = cloud_validation(client, "azure")  # True  when NOT azure
    skip_gcp   = cloud_validation(client, "gcp")
    skip_aws   = cloud_validation(client, "aws")

    # Choices and locked sets for the scope_contains checkbox.
    byo_choices = _deferrable_choices(cloud)
    byo_locked  = _locked_for_cloud(cloud)

    # ---- Core questions ----
    # secret_scope / manage_secrets come FIRST so every subsequent ignore
    # lambda can read them from the already-answered dict.
    core = [
        Text(
            name="secret_scope",
            message="Secret scope name",
            default="sat_scope",
        ),
        Confirm(
            name="manage_secrets",
            message="Let SAT write the service principal secret to this scope?",
            default=True,
        ),
    ]

    # ---- BYO scope: checkbox + per-key prompts ----
    # scope_contains: which logical values live in the existing scope?
    # Shown only when manage_secrets=False.  client_secret is locked (always in scope).
    byo_scope = [
        Checkbox(
            name="scope_contains",
            message="Which values are already in your scope? (Space=toggle)",
            choices=byo_choices,
            locked=byo_locked,
            default=byo_locked,
            ignore=lambda x: x.get("manage_secrets", True),
        ),
    ]

    # One Text prompt per deferrable entry to collect the physical key name.
    # Shown only when that logical name was checked in scope_contains.
    # IMPORTANT: use lg=lg default-arg binding to capture the loop variable;
    # a bare closure would make every lambda see the last value of lg.
    byo_key_names = [
        Text(
            name=f"key_name__{lg}",
            message=f"Secret scope key name for: {label}",
            default=default_key,
            ignore=lambda x, lg=lg: lg not in (x.get("scope_contains") or []),
        )
        for lg, label, default_key, cloud_filter in DEFERRABLE_VALUES
        if cloud_filter is None or cloud_filter == cloud
    ]

    # ---- Non-secret config values ----
    # account_id / client_id / tenant_id / subscription_id: suppressed when the
    # user said those values are already in their scope.
    # catalog / security_analysis_schema: suppressed when analysis_schema_name is
    # deferred — the installer has no need for the component parts if the full
    # catalog.schema string comes from the user's existing scope key.
    _schema_deferred = lambda x: "analysis_schema_name" in (x.get("scope_contains") or [])
    config_values = [
        Text(
            name="account_id",
            message="Databricks Account ID",
            validate=lambda _, x: re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", x
            ),
            ignore=lambda x: "account_id" in (x.get("scope_contains") or []),
        ),
        List(
            name="catalog",
            message="Select catalog",
            choices=loading(get_catalogs, client=client),
            ignore=_schema_deferred,
        ),
        Text(
            name="security_analysis_schema",
            message="Schema name for SAT",
            default="security_analysis",
            ignore=_schema_deferred,
        ),
        Confirm(
            name="enable_serverless",
            message="Run on serverless? [Only monitor current workspace]",
            default=True,
        ),
        List(
            name="warehouse",
            message="Select warehouse",
            choices=loading(get_warehouses, client=client),
        ),
    ]

    # ---- Cloud-specific credential questions ----
    # client-id is a non-secret param: always ask unless in-scope or wrong cloud.
    # client-secret is a secret: ask only when manage_secrets=True AND right cloud.
    azure_qs = [
        Text(
            name="azure-tenant-id",
            message="Azure Tenant ID",
            ignore=lambda x: skip_azure or "tenant_id" in (x.get("scope_contains") or []),
        ),
        Text(
            name="azure-subscription-id",
            message="Azure Subscription ID",
            ignore=lambda x: skip_azure or "subscription_id" in (x.get("scope_contains") or []),
        ),
        Text(
            name="azure-client-id",
            message="SAT service principal Client ID",
            ignore=lambda x: skip_azure or "client_id" in (x.get("scope_contains") or []),
        ),
        Password(
            name="azure-client-secret",
            message="SAT service principal Client Secret",
            ignore=lambda x: skip_azure or not x.get("manage_secrets", True),
            echo="",
        ),
    ]
    gcp_qs = [
        Text(
            name="gcp-client-id",
            message="SAT service principal Client ID",
            ignore=lambda x: skip_gcp or "client_id" in (x.get("scope_contains") or []),
        ),
        Password(
            name="gcp-client-secret",
            message="SAT service principal Client Secret",
            ignore=lambda x: skip_gcp or not x.get("manage_secrets", True),
            echo="",
        ),
    ]
    aws_qs = [
        Text(
            name="aws-client-id",
            message="SAT service principal Client ID",
            ignore=lambda x: skip_aws or "client_id" in (x.get("scope_contains") or []),
        ),
        Password(
            name="aws-client-secret",
            message="SAT service principal Client Secret",
            ignore=lambda x: skip_aws or not x.get("manage_secrets", True),
            echo="",
        ),
    ]

    # ---- Proxy questions ----
    # proxies suppressed if the user flagged it as already in their scope.
    proxies = [
        Confirm(
            name="use_proxy",
            message="Want to use a proxy?",
            default=False,
            ignore=lambda x: "proxies" in (x.get("scope_contains") or []),
        ),
        Text(
            name="http",
            message="HTTP Proxy",
            ignore=lambda x: "proxies" in (x.get("scope_contains") or [])
                             or not x.get("use_proxy", False),
            default="",
        ),
        Text(
            name="https",
            message="HTTPS Proxy",
            ignore=lambda x: "proxies" in (x.get("scope_contains") or [])
                             or not x.get("use_proxy", False),
            default="",
        ),
    ]

    # ---- Scheduling ----
    scheduling = [
        Text(
            name="driver_schedule",
            message="Driver job schedule (Quartz cron expression)",
            default="0 0 8 ? * Mon,Wed,Fri",
        ),
        Text(
            name="secrets_scanner_schedule",
            message="Secrets scanner job schedule (Quartz cron expression)",
            default="0 0 8 ? * *",
        ),
        Text(
            name="job_timezone",
            message="Job schedule timezone (IANA timezone ID)",
            default="UTC",
        ),
    ]

    # ---- Permissions Analysis (BrickHound) ----
    brickhound = [
        Confirm(
            name="enable_brickhound",
            message="Deploy Permissions Analysis?",
            default=True,
        ),
        Text(
            name="brickhound_schedule",
            message="Permissions Analysis schedule (Quartz cron expression)",
            default="0 0 2 ? * *",
            ignore=lambda x: not x.get("enable_brickhound", False),
        ),
    ]

    # app_config_scope MUST come after enable_brickhound so the ignore lambda
    # can read the already-answered value from the answers dict.
    #
    # Both ignore and default delegate to _needs_app_config_scope() — the single
    # predicate that decides whether SAT must create a separate scope.  Keeping
    # them in sync prevents the mismatch where ignore=hidden but default returns
    # a non-blank value, which previously caused the app resource to bind to a
    # scope SAT never created (sat_app_scope 404 crash).
    #
    # default MUST be a callable: ConsoleRender.render() stores question.default
    # even for ignored questions (console/__init__.py:29-30).  A static string
    # would let the explicit-answer branch in _resolve_app_config_scope shadow
    # the deferral branch regardless of scope_contains.
    app_config = [
        Text(
            name="app_config_scope",
            message="Scope SAT will create for Permissions Analysis app config (non-secret)",
            default=lambda x: "sat_app_scope" if _needs_app_config_scope(x) else "",
            ignore=lambda x: not _needs_app_config_scope(x),
        ),
    ]

    return (
        core
        + byo_scope
        + byo_key_names
        + config_values
        + aws_qs + azure_qs + gcp_qs
        + proxies
        + scheduling
        + brickhound
        + app_config
    )


def form():
    profile = list_input(
        message="Select profile",
        choices=loading(get_profiles, "Loading profiles..."),
    )
    client = WorkspaceClient(profile=profile)
    return client, prompt(build_questions(client)), profile


# ---------------------------------------------------------------------------
# Secret key name assembly — called from main.py
# ---------------------------------------------------------------------------

def build_secret_key_names(answers: dict, cloud: str) -> dict:
    """Build the secret_key_names dict from structured prompt answers.

    For each logical name the user checked in scope_contains, use the
    corresponding key_name__<logical> answer (or fall back to the default
    physical key name).  Returns a dict suitable for JSON serialisation and
    injection into tmp_config.json / job base_parameters.
    """
    scope_contains = answers.get("scope_contains") or []
    result = {}
    for lg, _label, default_key, cloud_filter in DEFERRABLE_VALUES:
        if cloud_filter is not None and cloud_filter != cloud:
            continue
        if lg in scope_contains:
            result[lg] = answers.get(f"key_name__{lg}") or default_key
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_key_overrides(answers: dict) -> dict:
    """Return the merged key-override dict from answers.

    Accepts either the structured dict built by build_secret_key_names()
    (stored under 'secret_key_names_dict') or the legacy JSON string
    stored under 'secret_key_names'.  Returns empty dict on any error.
    """
    # Structured path (new): a plain dict stored directly.
    if isinstance(answers.get("secret_key_names_dict"), dict):
        return answers["secret_key_names_dict"]
    # Legacy / Terraform path: a JSON string.
    raw = answers.get("secret_key_names", "") or ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _needs_app_config_scope(answers: dict) -> bool:
    """True only when SAT must create/write a separate scope for the app's schema key.

    Used as the single source of truth for both the ignore lambda and the default
    lambda of the app_config_scope prompt.  Keeping both in sync here prevents the
    "ignore says hidden but default returns non-blank" mismatch that caused the
    sat_app_scope/404 crash when analysis_schema_name was deferred.

    Conditions that make a separate scope unnecessary:
    - BrickHound is not being deployed (no app)
    - manage_secrets=True: the key is written to the main scope
    - analysis_schema_name is in scope_contains: key lives in the user's scope,
      app binds there directly — SAT writes nothing, no new scope needed
    """
    if not answers.get("enable_brickhound", False):
        return False
    if answers.get("manage_secrets", True):
        return False
    if "analysis_schema_name" in (answers.get("scope_contains") or []):
        return False
    return True


def _resolve_app_config_scope(answers: dict, scope_name: str, manage_secrets: bool) -> str:
    """Return the scope that holds the BrickHound app's analysis_schema_name key.

    Resolution order (mirrors terraform/common/locals.tf):
    1. analysis_schema_name deferred to user's scope → scope_name directly.
       This takes precedence over any explicit answer because the user's prompt
       default was pre-filled with "sat_app_scope" and pressing Enter without
       clearing it would otherwise route to a scope SAT never created.
    2. manage_secrets=True → scope_name (key lives in the main scope).
    3. Explicit app_config_scope answer (non-blank, non-default) → use it.
    4. Fallback → "sat_app_scope" (SAT creates and owns it; credential scope untouched).
    """
    scope_contains = answers.get("scope_contains") or []
    if "analysis_schema_name" in scope_contains:
        return scope_name
    if manage_secrets:
        return scope_name
    explicit = (answers.get("app_config_scope") or "").strip()
    if explicit and explicit != "sat_app_scope":
        return explicit
    return explicit or "sat_app_scope"


def ensure_app_config_secrets(
    client: WorkspaceClient,
    answers: dict,
    scope_name: str,
    manage_secrets: bool,
    key_overrides: dict,
    existing_scopes: set,
) -> None:
    """Write analysis_schema_name to the app config scope when needed.

    WAREHOUSE_ID is no longer written here — app.yaml uses valueFrom: "warehouse"
    which resolves from the sql_warehouse resource directly (no secret needed).

    Skipped entirely when:
    - BrickHound is not being deployed, OR
    - analysis_schema_name is already in the user's scope (scope_contains).

    Called from both manage_secrets=True and manage_secrets=False paths.
    """
    if not answers.get("enable_brickhound", False):
        return

    scope_contains = answers.get("scope_contains") or []
    if "analysis_schema_name" in scope_contains:
        # Key is pre-populated in the user's scope; SAT must not write to it.
        return

    app_scope = _resolve_app_config_scope(answers, scope_name, manage_secrets)

    if app_scope not in existing_scopes:
        client.secrets.create_scope(app_scope)

    analysis_schema_key = key_overrides.get("analysis_schema_name", "analysis_schema_name")
    client.secrets.put_secret(
        scope=app_scope,
        key=analysis_schema_key,
        string_value=f'`{answers["catalog"]}`.{answers["security_analysis_schema"]}',
    )


def generate_secrets(client: WorkspaceClient, answers: dict, cloud_type: str):
    """Create the SAT secret scope (if absent) and write only the credential secret.

    Non-secret config values (account_id, client_id, sql_warehouse_id, etc.) are
    now passed as direct job base_parameters via the bundle template — not stored
    in the scope.  Only ``client-secret`` (and cloud-equivalent) is written here
    because it is an actual credential that must not travel through job parameters.
    """
    scope_name = answers.get("secret_scope", "sat_scope") or "sat_scope"
    key_overrides = _resolve_key_overrides(answers)
    client_secret_key = key_overrides.get("client_secret", "client-secret")

    # Only create the scope if it doesn't already exist. Previous versions
    # deleted and recreated the scope on every install, which wiped ACLs —
    # including the READ ACL that Databricks Apps auto-creates when a
    # `secret` resource is bound to an app. That left re-installs with the
    # BrickHound app unable to resolve its `valueFrom` env vars and crashing
    # at startup. Overwriting individual keys with `put_secret` below
    # preserves existing ACLs.
    existing = {scope.name for scope in client.secrets.list_scopes()}
    if scope_name not in existing:
        client.secrets.create_scope(scope_name)

    # Write only the credential secret — the only value that must remain in the scope.
    for value in answers.keys():
        if cloud_type in value and value.endswith("-client-secret"):
            client.secrets.put_secret(
                scope=scope_name,
                key=client_secret_key,
                string_value=answers[value],
            )
            break

    # Always ensure app config secrets exist for BrickHound regardless of
    # manage_secrets; extracted so the BYO path also calls this.
    ensure_app_config_secrets(client, answers, scope_name, True, key_overrides, existing)


def validate_secrets(client: WorkspaceClient, answers: dict, cloud_type: str) -> None:
    """Validate that a pre-existing scope has all the keys SAT needs.

    Called when ``manage_secrets=False``.  Raises ``ValueError`` (caught by the
    ``except Exception`` in main.py) with the full list of missing keys before
    bundle deploy is attempted.
    """
    scope_name = answers.get("secret_scope", "sat_scope") or "sat_scope"
    key_overrides = _resolve_key_overrides(answers)

    # Check scope exists.
    existing = {scope.name for scope in client.secrets.list_scopes()}
    if scope_name not in existing:
        raise ValueError(
            f"Secret scope '{scope_name}' does not exist. "
            f"Create it first or set manage_secrets=True to let SAT create it."
        )

    # Validate every key the user declared is in the scope — report all
    # missing at once rather than stopping at the first failure.
    scope_contains = answers.get("scope_contains") or []
    missing = []
    for lg, _label, default_key, cloud_filter in DEFERRABLE_VALUES:
        if cloud_filter is not None and cloud_filter != cloud_type:
            continue
        if lg not in scope_contains:
            continue
        physical = key_overrides.get(lg, default_key)
        try:
            result = client.secrets.get_secret(scope=scope_name, key=physical)
            if not result.value:
                missing.append(
                    f"  - {lg} (scope='{scope_name}', key='{physical}'): empty value"
                )
        except Exception as exc:
            missing.append(
                f"  - {lg} (scope='{scope_name}', key='{physical}'): {exc}"
            )

    if missing:
        raise ValueError(
            "The following required secrets are missing from scope "
            f"'{scope_name}':\n" + "\n".join(missing) + "\n"
            "Please populate these keys before re-running the installer."
        )

    # Still ensure app config secrets exist for BrickHound even when
    # the user brings their own credential scope.
    ensure_app_config_secrets(client, answers, scope_name, False, key_overrides, existing)
