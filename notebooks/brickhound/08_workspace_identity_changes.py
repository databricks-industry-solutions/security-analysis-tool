# Databricks notebook source
# MAGIC %md
# MAGIC # Workspace Identity Changes — Detection & Remediation
# MAGIC *Catch identities introduced outside your IdP, and non-IdP identities assigned to workspaces*
# MAGIC
# MAGIC <div style="background-color: #fff3e0; border-left: 4px solid #d32f2f; padding: 12px; margin: 16px 0;">
# MAGIC   <p style="margin: 0; font-size: 0.85em; color: #d32f2f; font-weight: bold;">⚠️ DISCLAIMER</p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #555;">
# MAGIC     This tool may have incomplete data. Outputs are visibility and audit aids, not authoritative
# MAGIC     compliance determinations. Remediation (removing a workspace permission assignment) is a
# MAGIC     <b>destructive, opt-in</b> action — review findings before enabling it.
# MAGIC   </p>
# MAGIC </div>
# MAGIC
# MAGIC ## What This Analysis Does
# MAGIC
# MAGIC With **Automatic Identity Management (AIM)**, identities and group memberships should originate
# MAGIC from your identity provider (Entra ID), provisioned automatically. Two things break that model:
# MAGIC
# MAGIC 1. **A human creates or changes an identity outside the IdP sync** — e.g. an admin hand-creates a
# MAGIC    user/group/service principal, adds a member to a group, or grants account admin. Identities
# MAGIC    should come from the IdP, not be created directly in Databricks.
# MAGIC 2. **A non-IdP-managed identity is assigned to a workspace** — assigning identities to workspaces is
# MAGIC    a legitimate, necessary Databricks operation (it *cannot* be done by the IdP), but the thing
# MAGIC    being assigned should be an **IdP-managed** identity.
# MAGIC
# MAGIC This notebook reads `system.access.audit` and flags both. It **distinguishes human actions from the
# MAGIC AIM sync process**: AIM tags its automated events with `request_params.endpoint = 'autoUserCreation'`,
# MAGIC so any identity change *without* that tag was performed by a human.
# MAGIC
# MAGIC | Category | Source action(s) | Flagged when |
# MAGIC |---|---|---|
# MAGIC | `identity_created` | `add`, `createGroup` (accounts) | performed by a human (not AIM sync) |
# MAGIC | `group_membership_add` | `addPrincipalToGroup(s)` (accounts) | performed by a human (not AIM sync) |
# MAGIC | `admin_grant` | `setAdmin` (accounts) | performed by a human (not AIM sync) |
# MAGIC | `workspace_assignment_add` | `updatePermissionAssignment` (workspace) | assigned principal is **not** IdP-managed |
# MAGIC | `account_workspace_access` | `changeDatabricksWorkspaceAcl` (accounts) | assigned principal is **not** IdP-managed |
# MAGIC | `workspace_assignment_remove` | `deletePermissionAssignment` (workspace) | never (recorded for context) |
# MAGIC
# MAGIC AIM-sync events and assignments of IdP-managed identities are **recorded but not flagged** — they are
# MAGIC the expected, governed baseline. What SAT proves is *that an ungoverned-looking change happened, and
# MAGIC who/when* — it cannot by itself prove whether an Entra entitlement-management approval backed it.
# MAGIC
# MAGIC **Platform-managed Databricks App service principals are excluded.** Deploying a Databricks App
# MAGIC auto-creates an SP (audit `endpoint = DatabricksApps`); these are not ungoverned human onboarding, so
# MAGIC they are dropped from detection entirely and are never flagged or disabled.
# MAGIC
# MAGIC ### Scope of the two admin paths
# MAGIC
# MAGIC - **Workspace admins** assigning identities via the workspace UI → `updatePermissionAssignment`
# MAGIC   (service `workspace`). Fires for **users, groups, and service principals**.
# MAGIC - **Account admins** assigning identities via the account console → `changeDatabricksWorkspaceAcl`
# MAGIC   (service `accounts`).
# MAGIC
# MAGIC Findings are written to **`brickhound_workspace_identity_changes`** in SAT's analysis schema, stamped
# MAGIC with a `run_id`. The SAT Permissions Analysis app reads this table to surface findings in the UI.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC - SAT installed (`sat_scope` with `account-console-id`, `client-id`, `client-secret`,
# MAGIC   `analysis_schema_name`); service principal with **Account Admin**.
# MAGIC - Access to `system.access.audit` and `system.access.workspaces_latest`.
# MAGIC - **Azure only:** the compute needs network egress to `login.microsoftonline.com` (Entra ID) for
# MAGIC   MSAL token minting. If serverless egress is restricted, run on a classic cluster.

# COMMAND ----------

# DBTITLE 1,Run Configuration
# MAGIC %run ./00_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration Widgets
# MAGIC
# MAGIC | Widget | Description |
# MAGIC |---|---|
# MAGIC | `last_n_days` | How far back to search the audit log (default 30). |
# MAGIC | `finding_scope` | Comma-separated: `workspace_assignment`, `account_workspace_access`, `identity_creation`, `group_membership`, `admin_grant`. |
# MAGIC | `remediate` | `yes` removes the workspace permission assignment for flagged non-IdP assignments. Default `no` (report-only). |
# MAGIC | `disable_identities` | `yes` deactivates (SCIM `active=false`) flagged users / service principals added outside the AIM sync. **Destructive**; default `no`. |

# COMMAND ----------

# DBTITLE 1,Define Widgets
dbutils.widgets.text("last_n_days", "30", "Look-back window (days)")
dbutils.widgets.text(
    "finding_scope",
    "workspace_assignment,account_workspace_access,identity_creation,group_membership,admin_grant",
    "Finding scope (comma-separated)",
)
dbutils.widgets.dropdown("remediate", "no", ["no", "yes"], "Remove non-IdP workspace assignments")
dbutils.widgets.dropdown("disable_identities", "no", ["no", "yes"], "Disable users/SPs added outside AIM")

LAST_N_DAYS        = int(dbutils.widgets.get("last_n_days"))
FINDING_SCOPE      = [s.strip() for s in dbutils.widgets.get("finding_scope").split(",") if s.strip()]
REMEDIATE          = dbutils.widgets.get("remediate") == "yes"
DISABLE_IDENTITIES = dbutils.widgets.get("disable_identities") == "yes"

print(f"Look-back window:   {LAST_N_DAYS} days")
print(f"Finding scope:      {FINDING_SCOPE}")
print(f"Remediate (assign): {REMEDIATE}")
print(f"Disable identities: {DISABLE_IDENTITIES}")

# COMMAND ----------

# DBTITLE 1,Resolve Account Host, Credentials, and Output Table
# Mirrors core/dbclient.py: derive the accounts host per cloud, honoring the
# accounts_console override for GovCloud/DoD.

def _domain_from_url(url: str) -> str:
    host = url.split("://")[-1].split("/")[0]
    return host.split(".")[-1] if "." in host else "com"

def resolve_accounts_host(cloud: str, workspace_url: str, override: str = "") -> str:
    if override:
        return override.rstrip("/")
    domain = _domain_from_url(workspace_url)
    if cloud == "aws":
        return f"https://accounts.cloud.databricks.{domain}"
    elif cloud == "gcp":
        return f"https://accounts.gcp.databricks.{domain}"
    elif cloud == "azure":
        return f"https://accounts.azuredatabricks.{domain}"
    raise ValueError(f"Unsupported cloud type: '{cloud}'")

WORKSPACE_URL = (
    dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
)
ACCOUNTS_HOST = resolve_accounts_host(cloud_type, WORKSPACE_URL, json_.get("accounts_console", ""))
ACCOUNT_ID    = json_["account_id"]
CLIENT_ID     = dbutils.secrets.get(scope=SECRETS_SCOPE, key="client-id")
CLIENT_SECRET = dbutils.secrets.get(scope=SECRETS_SCOPE, key="client-secret")

# tenant-id is required for Azure (Entra/MSAL auth); absent on AWS/GCP.
TENANT_ID = None
if cloud_type == "azure":
    TENANT_ID = json_.get("tenant_id") or dbutils.secrets.get(scope=SECRETS_SCOPE, key="tenant-id")

WORKSPACE_IDENTITY_CHANGES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_workspace_identity_changes"

print(f"Cloud type:    {cloud_type}")
print(f"Accounts host: {ACCOUNTS_HOST}")
print(f"Output table:  {WORKSPACE_IDENTITY_CHANGES_TABLE}")

# COMMAND ----------

# DBTITLE 1,Auditor Implementation
from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests
from pyspark.sql import functions as F

# Tag SAT's direct REST traffic so it is attributed to SAT usage in Databricks
# telemetry, matching core/dbclient.py and the other SAT notebooks.
SAT_USER_AGENT = "databricks-sat/0.1.0"

# Audit action_name -> (change_category, changed_via, principal_id key, permission key)
# Verified against the live system.access.audit table. request_params is a MAP, so
# absent keys resolve to NULL (no "cannot find field" error).
_SCOPE_ACTIONS = {
    "workspace_assignment": [
        ("updatePermissionAssignment", "workspace_assignment_add",    "workspace_admin"),
        ("deletePermissionAssignment", "workspace_assignment_remove", "workspace_admin"),
    ],
    "account_workspace_access": [
        ("changeDatabricksWorkspaceAcl", "account_workspace_access", "account_admin"),
    ],
    "identity_creation": [
        ("add",         "identity_created", "account_admin"),
        ("createGroup", "identity_created", "account_admin"),
    ],
    "group_membership": [
        ("addPrincipalToGroup",  "group_membership_add", "account_admin"),
        ("addPrincipalsToGroup", "group_membership_add", "account_admin"),
    ],
    "admin_grant": [
        ("setAdmin", "admin_grant", "account_admin"),
    ],
}


@dataclass(frozen=True)
class RemediationResult:
    workspace_id: str
    principal_id: str
    success:      bool
    message:      str

    def __str__(self) -> str:
        icon = "✓" if self.success else "✗"
        return f"{icon} ws={self.workspace_id} principal={self.principal_id}: {self.message}"


class WorkspaceIdentityChangeAuditor:
    """Detect (and optionally remediate) workspace/identity changes from the audit
    log: identities created/changed outside the AIM sync, and non-IdP identities
    assigned to workspaces.
    """

    def __init__(self, accounts_host: str, account_id: str, client_id: str,
                 client_secret: str, cloud_type: str, tenant_id: Optional[str] = None,
                 proxies: Optional[dict] = None) -> None:
        self._accounts_host = accounts_host.rstrip("/")
        self._account_id    = account_id
        self._client_id     = client_id
        self._client_secret = client_secret
        self._cloud_type    = cloud_type
        self._tenant_id     = tenant_id
        self._proxies       = proxies or {}
        self._acct_token    = self._mint_account_token()
        self._acct_hdrs     = {"Authorization": f"Bearer {self._acct_token}",
                               "User-Agent": SAT_USER_AGENT}

    # ── Token helpers ────────────────────────────────────────────────────────

    def _mint_azure_msal_token(self) -> str:
        """AAD token for the Databricks resource (matches SatDBClient.getAzureTokenWithMSAL)."""
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
        )
        token = app.acquire_token_for_client(scopes=["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"])
        if not token or not token.get("access_token"):
            raise Exception(f"MSAL token acquisition failed: {token.get('error_description') if token else 'no token'}")
        return token["access_token"]

    def _mint_account_token(self) -> str:
        if self._cloud_type == "azure":
            return self._mint_azure_msal_token()
        resp = requests.post(
            f"{self._accounts_host}/oidc/accounts/{self._account_id}/v1/token",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": SAT_USER_AGENT},
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._client_id,
                "client_secret": self._client_secret,
                "scope":         "all-apis",
            },
            proxies=self._proxies,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ── SCIM enrichment ──────────────────────────────────────────────────────

    def _scim_list(self, resource: str, attributes: str) -> list[dict]:
        """Page through an account SCIM collection (Groups/Users/ServicePrincipals)."""
        items: list[dict] = []
        start_index, count = 1, 100
        while True:
            resp = requests.get(
                f"{self._accounts_host}/api/2.0/accounts/{self._account_id}/scim/v2/{resource}"
                f"?attributes={urllib.parse.quote(attributes)}&startIndex={start_index}&count={count}",
                headers=self._acct_hdrs,
                proxies=self._proxies,
            )
            resp.raise_for_status()
            body = resp.json()
            page = body.get("Resources", [])
            items.extend(page)
            total = body.get("totalResults", len(items))
            if start_index + count > total or not page:
                break
            start_index += count
        return items

    def build_identity_index(self) -> dict[str, dict]:
        """Map account SCIM id -> {principal_type, principal_name, principal_email,
        application_id, is_idp_managed}. Used to enrich the principal in each audit
        event (the audit log records only the principal_id, not its type)."""
        index: dict[str, dict] = {}
        specs = [
            ("Users",             "User",             "id,userName,displayName,externalId"),
            ("Groups",            "Group",            "id,displayName,externalId"),
            ("ServicePrincipals", "ServicePrincipal", "id,applicationId,displayName,externalId"),
        ]
        for resource, ptype, attrs in specs:
            for e in self._scim_list(resource, attrs):
                index[str(e.get("id"))] = {
                    "principal_type":  ptype,
                    "principal_name":  e.get("displayName") or e.get("userName") or e.get("applicationId"),
                    "principal_email": e.get("userName") if ptype == "User" else None,
                    "application_id":  e.get("applicationId") if ptype == "ServicePrincipal" else None,
                    "is_idp_managed":  bool(e.get("externalId")),
                }
        return index

    def _console_url(self, principal_type: Optional[str], principal_id: Optional[str]) -> str:
        """Deep link to the account-console detail page for a principal (mirrors 06/07)."""
        segment = {"Group": "groups", "User": "users",
                   "ServicePrincipal": "serviceprincipals"}.get(principal_type or "", "users")
        if not principal_id:
            return f"{self._accounts_host}/user-management/{segment}"
        return (f"{self._accounts_host}/user-management/{segment}/{principal_id}"
                f"?account_id={self._account_id}")

    # ── Detection ──────────────────────────────────────────────────────────────

    @staticmethod
    def _subquery(action: str, category: str, changed_via: str, since: str) -> str:
        """One UNION ALL branch. Columns are positional and identical across
        branches; principal-id / permission / hint keys differ per action."""
        # principal-id and permission keys per action (verified live)
        if action in ("updatePermissionAssignment", "deletePermissionAssignment"):
            pid_expr  = "request_params['principal_id']"
            perm_expr = "request_params['permissions']" if action == "updatePermissionAssignment" else "CAST(NULL AS STRING)"
            hint_expr = "CAST(NULL AS STRING)"
            grp_expr  = "CAST(NULL AS STRING)"
            ws_expr   = "coalesce(request_params['workspace_id'], CAST(workspace_id AS STRING))"
            extra     = ""
        elif action == "changeDatabricksWorkspaceAcl":
            pid_expr  = "request_params['targetUserId']"
            perm_expr = "request_params['aclPermissionSet']"
            hint_expr = "CAST(NULL AS STRING)"
            grp_expr  = "CAST(NULL AS STRING)"
            ws_expr   = "CAST(workspace_id AS STRING)"
            # Only grants (non-empty permission set); empty = a revoke.
            extra     = "AND request_params['aclPermissionSet'] != ''"
        elif action == "createGroup":
            pid_expr  = "request_params['targetGroupId']"
            perm_expr = "CAST(NULL AS STRING)"
            hint_expr = "request_params['targetGroupName']"
            grp_expr  = "CAST(NULL AS STRING)"
            ws_expr   = "CAST(workspace_id AS STRING)"
            extra     = ""
        elif action in ("addPrincipalToGroup", "addPrincipalsToGroup"):
            pid_expr  = "request_params['targetUserId']"
            perm_expr = "CAST(NULL AS STRING)"
            hint_expr = "request_params['targetUserName']"
            grp_expr  = "request_params['targetGroupName']"
            ws_expr   = "CAST(workspace_id AS STRING)"
            extra     = ""
        elif action == "setAdmin":
            pid_expr  = "request_params['targetUserId']"
            perm_expr = "'account_admin'"
            hint_expr = "request_params['targetUserName']"
            grp_expr  = "CAST(NULL AS STRING)"
            ws_expr   = "CAST(workspace_id AS STRING)"
            extra     = ""
        else:  # add (user/SP created)
            pid_expr  = "request_params['targetUserId']"
            perm_expr = "CAST(NULL AS STRING)"
            hint_expr = "request_params['targetUserName']"
            grp_expr  = "CAST(NULL AS STRING)"
            ws_expr   = "CAST(workspace_id AS STRING)"
            extra     = ""

        service = "workspace" if changed_via == "workspace_admin" else "accounts"
        return f"""
            SELECT
                '{category}'    AS change_category,
                '{changed_via}' AS changed_via,
                event_time,
                event_date,
                {ws_expr}       AS workspace_id,
                action_name,
                service_name,
                user_identity.email AS actor_email,
                source_ip_address   AS source_ip,
                {pid_expr}      AS principal_id,
                {perm_expr}     AS permission,
                request_params['endpoint'] AS endpoint,
                {hint_expr}     AS principal_hint,
                {grp_expr}      AS related_group
            FROM system.access.audit
            WHERE action_name = '{action}' AND service_name = '{service}'
              {extra}
              -- Exclude platform-managed Databricks App service principals: deploying
              -- an app auto-creates an SP via the DatabricksApps endpoint. These are
              -- not ungoverned human onboarding, so they must never be flagged or
              -- disabled (disabling one would take down a live app).
              AND coalesce(request_params['endpoint'], '') <> 'DatabricksApps'
              AND event_time >= '{since}'
        """

    def query_events(self, last_n_days: int, scopes: list[str]) -> pd.DataFrame:
        since = (datetime.now(timezone.utc) - timedelta(days=last_n_days)).strftime("%Y-%m-%d")
        branches: list[str] = []
        for scope in scopes:
            for action, category, changed_via in _SCOPE_ACTIONS.get(scope, []):
                branches.append(self._subquery(action, category, changed_via, since))
        if not branches:
            return pd.DataFrame()

        union = " UNION ALL ".join(branches)
        sql = f"""
            SELECT e.*, w.workspace_name
            FROM ( {union} ) e
            LEFT JOIN system.access.workspaces_latest w
                   ON e.workspace_id = CAST(w.workspace_id AS STRING)
                  AND w.status = 'RUNNING'
            ORDER BY e.event_time DESC
        """
        return spark.sql(sql).toPandas()

    def classify(self, df: pd.DataFrame, index: dict[str, dict]) -> pd.DataFrame:
        """Enrich each event's principal from SCIM and apply the flag model."""
        if df.empty:
            return df

        # Drop events with a blank principal_id. Creating a service principal or
        # group emits a secondary audit event whose id lands in a different field
        # (a second scim `add` with empty targetUserId, or a createGroup with
        # endpoint=permissionAssignment carrying the id in targetUserId), leaving
        # our extracted principal_id empty. These are duplicates of the real
        # creation event (which has the id and resolves) — dropping them removes
        # spurious "Unknown" rows without losing any genuine finding.
        df = df[df["principal_id"].map(
            lambda v: v is not None and str(v).strip() not in ("", "None"))].copy()
        if df.empty:
            return df

        def enrich(row):
            info = index.get(str(row["principal_id"])) if row.get("principal_id") else None
            if info:
                ptype, pname = info["principal_type"], info["principal_name"]
                pemail, app_id, idp = info["principal_email"], info["application_id"], info["is_idp_managed"]
            else:
                # Principal not in current SCIM (deleted since, or unknown) — fall
                # back to the name captured in the audit event.
                ptype, pname = "Unknown", row.get("principal_hint")
                pemail, app_id, idp = None, None, False
            return pd.Series({
                "principal_type":  ptype,
                "principal_name":  pname,
                "principal_email": pemail,
                "application_id":  app_id,
                "is_idp_managed":  idp,
                "console_url":     self._console_url(ptype, row.get("principal_id")),
            })

        df = df.copy()
        df[["principal_type", "principal_name", "principal_email", "application_id",
            "is_idp_managed", "console_url"]] = df.apply(enrich, axis=1)
        df["is_aim_sync"] = df["endpoint"] == "autoUserCreation"

        def flag(row):
            cat, aim, idp = row["change_category"], row["is_aim_sync"], row["is_idp_managed"]
            if cat == "identity_created":
                return (not aim, "ungoverned_identity_creation" if not aim else None)
            if cat == "group_membership_add":
                return (not aim, "ungoverned_group_membership" if not aim else None)
            if cat == "admin_grant":
                return (not aim, "ungoverned_admin_grant" if not aim else None)
            if cat in ("workspace_assignment_add", "account_workspace_access"):
                return ((not idp), "workspace_assignment_of_non_idp_identity" if not idp else None)
            return (False, None)  # workspace_assignment_remove, etc.

        flags = df.apply(flag, axis=1, result_type="expand")
        df["flagged"], df["flag_reason"] = flags[0].astype(bool), flags[1]
        df["auto_remediated"] = False
        df["remediation_action"] = None
        return df

    # ── Remediation ────────────────────────────────────────────────────────────

    def _remove_workspace_assignment(self, workspace_id: str, principal_id: str) -> RemediationResult:
        """Account-scoped DELETE of a principal's workspace permission assignment.

        Removes the principal's access to THAT workspace only; the account-level
        identity and any other-workspace access are untouched. Account-scoped so it
        needs no per-workspace token and is immune to cross-workspace enforcement.
        """
        url = (f"{self._accounts_host}/api/2.0/accounts/{self._account_id}"
               f"/workspaces/{workspace_id}/permissionassignments/principals/{principal_id}")
        try:
            resp = requests.delete(url, headers=self._acct_hdrs, proxies=self._proxies, timeout=30)
        except requests.RequestException as e:
            return RemediationResult(workspace_id, principal_id, False, f"{type(e).__name__}")
        if resp.ok or resp.status_code == 404:  # 404 = assignment already gone
            return RemediationResult(workspace_id, principal_id, True,
                                     "assignment removed" if resp.ok else "already removed")
        return RemediationResult(workspace_id, principal_id, False,
                                 f"DELETE {resp.status_code}: {resp.text[:200]}")

    def remediate(self, df: pd.DataFrame, max_workers: int = 8) -> list[RemediationResult]:
        """Remove workspace assignments for FLAGGED non-IdP assignment findings.

        Only `workspace_assignment_add` / `account_workspace_access` are remediated
        (removing a workspace permission assignment is safe and reversible).
        Ungoverned identity creation / membership / admin grants are left for manual
        review — undoing them means deleting the account identity, which is too
        destructive to automate here.
        """
        targets = df[
            df["flagged"]
            & df["change_category"].isin(["workspace_assignment_add", "account_workspace_access"])
            & df["workspace_id"].notna()
            & df["principal_id"].notna()
        ].drop_duplicates(["workspace_id", "principal_id"])

        if targets.empty:
            print("  No flagged workspace assignments to remediate.")
            return []

        results: list[RemediationResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._remove_workspace_assignment,
                            str(row["workspace_id"]), str(row["principal_id"])): None
                for _, row in targets.iterrows()
            }
            for future in as_completed(futures):
                results.append(future.result())

        for r in sorted(results, key=lambda r: (r.workspace_id, r.principal_id)):
            print(r)
        return results

    def _disable_identity(self, principal_type: str, principal_id: str) -> tuple[str, str, bool, str]:
        """Deactivate a user or service principal via account SCIM PATCH active=false.

        Reversible (does not delete the identity); the principal simply can no
        longer authenticate. Only Users / ServicePrincipals support `active` —
        groups cannot be deactivated this way.
        """
        resource = {"User": "Users", "ServicePrincipal": "ServicePrincipals"}.get(principal_type)
        if not resource:
            return (principal_id, principal_type, False, "not a user/service principal")
        url = f"{self._accounts_host}/api/2.0/accounts/{self._account_id}/scim/v2/{resource}/{principal_id}"
        body = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        try:
            resp = requests.patch(url, headers={**self._acct_hdrs, "Content-Type": "application/scim+json"},
                                  json=body, proxies=self._proxies, timeout=30)
        except requests.RequestException as e:
            return (principal_id, principal_type, False, f"{type(e).__name__}")
        return (principal_id, principal_type, resp.ok,
                "deactivated" if resp.ok else f"PATCH {resp.status_code}: {resp.text[:150]}")

    def disable_identities(self, df: pd.DataFrame, max_workers: int = 8) -> list[tuple]:
        """Deactivate FLAGGED users/SPs added outside the AIM sync — either created
        in the account (`identity_created`) or assigned to a workspace as a non-IdP
        identity. Groups are excluded (SCIM `active` applies only to users/SPs).
        """
        targets = df[
            df["flagged"]
            & df["principal_type"].isin(["User", "ServicePrincipal"])
            & df["change_category"].isin(
                ["identity_created", "workspace_assignment_add", "account_workspace_access"])
            & df["principal_id"].notna()
        ].drop_duplicates("principal_id")

        if targets.empty:
            print("  No flagged users/service principals to disable.")
            return []

        results: list[tuple] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self._disable_identity, row["principal_type"], str(row["principal_id"]))
                       for _, row in targets.iterrows()]
            for future in as_completed(futures):
                results.append(future.result())

        for pid, ptype, ok, msg in sorted(results, key=lambda r: (r[1], r[0])):
            print(f"{'✓' if ok else '✗'} [{ptype}] {pid}: {msg}")
        return results

# COMMAND ----------

# DBTITLE 1,Initialize Auditor & Build Identity Index
auditor = WorkspaceIdentityChangeAuditor(
    accounts_host = ACCOUNTS_HOST,
    account_id    = ACCOUNT_ID,
    client_id     = CLIENT_ID,
    client_secret = CLIENT_SECRET,
    cloud_type    = cloud_type,
    tenant_id     = TENANT_ID,
    proxies       = json_.get("proxies", {}),
)
identity_index = auditor.build_identity_index()
print(f"✓ Auditor initialized; account SCIM identity index: {len(identity_index)} principals")

# COMMAND ----------

# DBTITLE 1,Detect Changes
raw = auditor.query_events(LAST_N_DAYS, FINDING_SCOPE)
print(f"Found {len(raw)} identity/assignment event(s) in the last {LAST_N_DAYS} days.")

findings = auditor.classify(raw, identity_index)
if not findings.empty:
    flagged_n = int(findings["flagged"].sum())
    print(f"Flagged (require review): {flagged_n} of {len(findings)}")
    print(findings.groupby(["change_category", "flagged"]).size().to_string())

# COMMAND ----------

# DBTITLE 1,Remediate (opt-in)
ok_assign: set = set()   # (workspace_id, principal_id) whose assignment was removed
ok_disable: set = set()  # principal_id that was deactivated

if not findings.empty and (REMEDIATE or DISABLE_IDENTITIES):
    if REMEDIATE:
        print("Removing flagged non-IdP workspace assignments...\n")
        results = auditor.remediate(findings)
        ok_assign = {(r.workspace_id, r.principal_id) for r in results if r.success}
    if DISABLE_IDENTITIES:
        print("\nDisabling flagged users/service principals added outside AIM...\n")
        disable_results = auditor.disable_identities(findings)
        ok_disable = {pid for pid, ptype, success, msg in disable_results if success}

    # Per-row remediation outcome. A principal can be both assignment-removed and
    # disabled; record every action applied to that row.
    def _action(row):
        acts = []
        if (row["change_category"] in ("workspace_assignment_add", "account_workspace_access")
                and bool(row["flagged"])
                and (str(row["workspace_id"]), str(row["principal_id"])) in ok_assign):
            acts.append("assignment_removed")
        if str(row["principal_id"]) in ok_disable:
            acts.append("identity_disabled")
        return ",".join(acts) if acts else None

    findings["remediation_action"] = findings.apply(_action, axis=1)
    findings["auto_remediated"] = findings["remediation_action"].notna()

    manual = int((findings["flagged"] & findings["remediation_action"].isna()).sum())
    if manual:
        print(f"\nℹ {manual} flagged change(s) not auto-remediated (e.g. group creation, "
              "membership, or admin grants — review/undo at the account level manually).")
elif REMEDIATE or DISABLE_IDENTITIES:
    print("Remediation enabled, but no findings to act on.")
else:
    print("Remediation not enabled — set 'remediate' and/or 'disable_identities' to 'yes' to take action.")

# COMMAND ----------

# DBTITLE 1,Persist Findings to Delta
import uuid
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, BooleanType, DateType,
)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
DETECTION_TIME = datetime.now(timezone.utc)
print(f"Run ID: {RUN_ID}")

findings_schema = StructType([
    StructField("run_id",              StringType(),    False),
    StructField("detection_timestamp", TimestampType(), False),
    StructField("event_time",          TimestampType(), True),
    StructField("event_date",          DateType(),      True),
    StructField("action_name",         StringType(),    True),
    StructField("change_category",     StringType(),    True),
    StructField("changed_via",         StringType(),    True),
    StructField("is_aim_sync",         BooleanType(),   True),
    StructField("actor_email",         StringType(),    True),
    StructField("source_ip",           StringType(),    True),
    StructField("principal_id",        StringType(),    True),
    StructField("principal_type",      StringType(),    True),
    StructField("principal_name",      StringType(),    True),
    StructField("principal_email",     StringType(),    True),
    StructField("application_id",      StringType(),    True),
    StructField("is_idp_managed",      BooleanType(),   True),
    StructField("related_group",       StringType(),    True),
    StructField("permission",          StringType(),    True),
    StructField("workspace_id",        StringType(),    True),
    StructField("workspace_name",      StringType(),    True),
    StructField("flagged",             BooleanType(),   True),
    StructField("flag_reason",         StringType(),    True),
    StructField("console_url",         StringType(),    True),
    StructField("auto_remediated",     BooleanType(),   True),
    StructField("remediation_action",  StringType(),    True),
])

_cols = [
    "run_id", "detection_timestamp", "event_time", "event_date", "action_name",
    "change_category", "changed_via", "is_aim_sync", "actor_email", "source_ip",
    "principal_id", "principal_type", "principal_name", "principal_email", "application_id",
    "is_idp_managed", "related_group", "permission", "workspace_id", "workspace_name",
    "flagged", "flag_reason", "console_url", "auto_remediated", "remediation_action",
]

if findings.empty:
    findings_df = spark.createDataFrame([], schema=findings_schema)
else:
    out = findings.copy()
    out["run_id"]              = RUN_ID
    out["detection_timestamp"] = DETECTION_TIME
    out["workspace_id"]        = out["workspace_id"].astype("object").where(out["workspace_id"].notna(), None)
    out["principal_id"]        = out["principal_id"].astype("object").where(out["principal_id"].notna(), None)
    # Coerce numpy.bool_ -> python bool; some Spark versions reject numpy.bool_
    # against a BooleanType schema column.
    for _b in ("is_aim_sync", "is_idp_managed", "flagged", "auto_remediated"):
        out[_b] = out[_b].map(bool)
    findings_df = spark.createDataFrame(out[_cols], schema=findings_schema)

findings_df.write.format("delta").mode("append") \
    .option("mergeSchema", "true") \
    .saveAsTable(WORKSPACE_IDENTITY_CHANGES_TABLE)

spark.sql(
    f"COMMENT ON TABLE {WORKSPACE_IDENTITY_CHANGES_TABLE} IS "
    "'SAT Permissions Analysis — workspace/identity changes from system.access.audit: identities created "
    "or changed outside the AIM sync, and non-IdP identities assigned to workspaces. is_aim_sync marks the "
    "automated sync vs a human actor; flagged marks findings that need review. Stamped with run_id.'"
)
for _col, _comment in {
    "run_id":              "Detection run identifier in format YYYYMMDD_HHMMSS_hash",
    "detection_timestamp": "UTC timestamp when this detection run executed",
    "event_time":          "Timestamp of the change in the audit log",
    "event_date":          "Date of the change in the audit log",
    "action_name":         "Raw audit action_name",
    "change_category":     "Normalized category (identity_created, group_membership_add, admin_grant, workspace_assignment_add, workspace_assignment_remove, account_workspace_access)",
    "changed_via":         "workspace_admin (workspace UI/API) or account_admin (account console/API)",
    "is_aim_sync":         "True if performed by the AIM sync process (request_params.endpoint = autoUserCreation); False = human actor",
    "actor_email":         "Email of the identity that made the change",
    "source_ip":           "Source IP of the change request",
    "principal_id":        "SCIM id of the affected principal",
    "principal_type":      "User, Group, ServicePrincipal, or Unknown (resolved from account SCIM)",
    "principal_name":      "Display name of the affected principal",
    "principal_email":     "Email / userName (users only)",
    "application_id":      "OAuth application id (service principals only)",
    "is_idp_managed":      "True if the affected principal carries an externalId (provisioned from an IdP)",
    "related_group":       "For group-membership changes, the group the principal was added to",
    "permission":          "Permission granted (USER/ADMIN, Workspace Access, account_admin), when applicable",
    "workspace_id":        "Target workspace id (assignment events)",
    "workspace_name":      "Workspace name from system.access.workspaces_latest",
    "flagged":             "True if this change needs review (ungoverned identity change, or non-IdP workspace assignment)",
    "flag_reason":         "Why the change was flagged, when flagged",
    "console_url":         "Deep link to the account-console section for this principal type",
    "auto_remediated":     "True if any remediation action was applied to this finding in this run",
    "remediation_action":  "What was done: assignment_removed and/or identity_disabled (comma-separated), or null",
}.items():
    spark.sql(f"ALTER TABLE {WORKSPACE_IDENTITY_CHANGES_TABLE} ALTER COLUMN `{_col}` COMMENT '{_comment.replace(chr(39), chr(39) * 2)}'")

print(f"Wrote {findings_df.count()} finding(s) to {WORKSPACE_IDENTITY_CHANGES_TABLE} (run_id={RUN_ID})")

# COMMAND ----------

# DBTITLE 1,Display Findings
if findings.empty:
    print("✓ No workspace/identity changes detected in the selected window and scope.")
else:
    display(findings_df.orderBy(F.desc("flagged"), F.desc("event_time")))

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Understanding Results
# MAGIC
# MAGIC Each row is one audit event. **`flagged = true`** are the findings to review:
# MAGIC
# MAGIC - **`ungoverned_identity_creation` / `ungoverned_group_membership` / `ungoverned_admin_grant`** — a
# MAGIC   human created/changed an identity, group membership, or admin role *outside* the AIM sync. These
# MAGIC   should originate from your IdP.
# MAGIC - **`workspace_assignment_of_non_idp_identity`** — a **non-IdP-managed** identity was assigned to a
# MAGIC   workspace. Assigning identities to workspaces is fine; assigning a locally-created (non-governed)
# MAGIC   one is the issue.
# MAGIC
# MAGIC Assignments of **IdP-managed** identities and **AIM-sync** events are recorded but not flagged — that
# MAGIC is the expected, governed baseline.
# MAGIC
# MAGIC ### Recommended workflow
# MAGIC
# MAGIC 1. Run **report-only** (`remediate = no`, `disable_identities = no`) and review flagged rows.
# MAGIC 2. Re-run with `remediate = yes` to remove flagged **non-IdP workspace assignments** (account-scoped;
# MAGIC    removes workspace access only, leaves the account identity intact).
# MAGIC 3. Optionally set `disable_identities = yes` to **deactivate** (SCIM `active=false`) flagged users /
# MAGIC    service principals added outside the AIM sync — reversible, and leaves the identity in place for
# MAGIC    audit. Groups are not deactivated (SCIM `active` doesn't apply); undo those at the account level.
# MAGIC 4. Both actions are recorded per row in `remediation_action` (`assignment_removed` / `identity_disabled`).
# MAGIC 5. Schedule this notebook (see `terraform/common/brickhound_workspace_identity_changes_job.tf`) to
# MAGIC    keep detection fresh. Leave both actions `no` in the job unless you intend continuous remediation.
