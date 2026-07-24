# Databricks notebook source
# MAGIC %md
# MAGIC # Privileged Non-IdP Managed Identities — Detection & Remediation
# MAGIC *Find privileged identities that are not centrally IdP-managed*
# MAGIC
# MAGIC <div style="background-color: #fff3e0; border-left: 4px solid #d32f2f; padding: 12px; margin: 16px 0;">
# MAGIC   <p style="margin: 0; font-size: 0.85em; color: #d32f2f; font-weight: bold;">⚠️ DISCLAIMER</p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #555;">
# MAGIC     This tool may have incomplete data. Outputs are visibility and audit aids, not authoritative
# MAGIC     compliance determinations. Remediation (removing a privileged role or admin-group membership)
# MAGIC     is a <b>destructive, opt-in</b> action — review findings before enabling it.
# MAGIC   </p>
# MAGIC </div>
# MAGIC
# MAGIC ## What This Analysis Does
# MAGIC
# MAGIC Privileged access should be granted to **IdP-managed** (SCIM-provisioned / externally-sourced)
# MAGIC identities so it is governed by your identity provider's joiner/mover/leaver processes. Privileged
# MAGIC roles held by **locally-managed** groups (no `externalId`), or assigned **directly** to users and
# MAGIC service principals, bypass that governance.
# MAGIC
# MAGIC This notebook flags:
# MAGIC
# MAGIC | Finding | Definition |
# MAGIC |---|---|
# MAGIC | Non-IdP group with **Account Admin** | Account group with no `externalId` that holds the `account_admin` role |
# MAGIC | Non-IdP group with **Workspace Admin** | Workspace `admins` group members that are locally-managed groups |
# MAGIC | User / SP with **Account Admin** (direct) | `account_admin` assigned directly to a user or service principal |
# MAGIC | User / SP with **Workspace Admin** (direct) | Direct member of a workspace `admins` group |
# MAGIC
# MAGIC ### IdP-managed signal
# MAGIC
# MAGIC A group/user/SP is considered **IdP-managed** when it carries an `externalId` in account SCIM
# MAGIC (i.e. it was provisioned from an external identity provider). Anything without an `externalId`
# MAGIC is treated as **locally-managed (non-IdP)**.
# MAGIC
# MAGIC ### Scope
# MAGIC
# MAGIC - **Account Admin** detection is account-wide (account SCIM).
# MAGIC - **Workspace Admin** detection covers the workspaces the SAT service principal can reach
# MAGIC   (the current workspace when run on serverless). Workspaces not covered are reported in the
# MAGIC   run's `workspaces_scanned` list.
# MAGIC
# MAGIC Findings are written to **`brickhound_privileged_non_idp`** in SAT's analysis schema. The SAT
# MAGIC Permissions Analysis app reads this table to surface findings in the UI.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC - SAT installed (`sat_scope` with `account-console-id`, `client-id`, `client-secret`,
# MAGIC   `analysis_schema_name`).
# MAGIC - The service principal must have **Account Admin**, and **Workspace Admin** on any workspace
# MAGIC   you want workspace-admin findings for (and remediation to work there).
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
# MAGIC | `finding_types` | Comma-separated: `account_admin`, `workspace_admin`. |
# MAGIC | `include_idp_managed` | `yes` also lists IdP-managed privileged identities (for context). Default `no` — only flag non-IdP. |
# MAGIC | `remediate` | `yes` removes the flagged privileged role / admin-group membership. Default `no` (report-only). |

# COMMAND ----------

# DBTITLE 1,Define Widgets
dbutils.widgets.text("finding_types", "account_admin,workspace_admin", "Finding types (comma-separated)")
dbutils.widgets.dropdown("include_idp_managed", "no", ["no", "yes"], "Include IdP-managed (context)")
dbutils.widgets.dropdown("remediate", "no", ["no", "yes"], "Remove privileged role/membership")

FINDING_TYPES       = [t.strip() for t in dbutils.widgets.get("finding_types").split(",") if t.strip()]
INCLUDE_IDP_MANAGED = dbutils.widgets.get("include_idp_managed") == "yes"
REMEDIATE           = dbutils.widgets.get("remediate") == "yes"

print(f"Finding types:        {FINDING_TYPES}")
print(f"Include IdP-managed:  {INCLUDE_IDP_MANAGED}")
print(f"Remediate:            {REMEDIATE}")

# COMMAND ----------

# DBTITLE 1,Resolve Account Host, Credentials, and Output Table
def _domain_from_url(url: str) -> str:
    host = url.split("://")[-1].split("/")[0]
    return host.split(".")[-1] if "." in host else "com"

def resolve_accounts_host(cloud: str, workspace_url: str, accounts_console_override: str = "") -> str:
    """Return the accounts console base URL for the given cloud (mirrors core/dbclient.py)."""
    if accounts_console_override:
        return accounts_console_override.rstrip("/")
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

PRIVILEGED_NON_IDP_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_privileged_non_idp"

print(f"Cloud type:    {cloud_type}")
print(f"Accounts host: {ACCOUNTS_HOST}")
print(f"Output table:  {PRIVILEGED_NON_IDP_TABLE}")

# COMMAND ----------

# DBTITLE 1,Auditor Implementation
from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
from pyspark.sql import functions as F


@dataclass(frozen=True)
class RemediationResult:
    principal_type: str
    principal_id:   str
    finding_type:   str
    success:        bool
    message:        str

    def __str__(self) -> str:
        icon = "✓" if self.success else "✗"
        return f"{icon} [{self.finding_type}] {self.principal_type} {self.principal_id}: {self.message}"


class PrivilegedIdentityAuditor:
    """Detect (and optionally remediate) privileged identities that are not
    IdP-managed: non-external groups with account_admin / workspace-admin, and
    users/SPs with those roles assigned directly.
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
        self._acct_hdrs     = {"Authorization": f"Bearer {self._acct_token}"}

    # ── Token helpers ────────────────────────────────────────────────────────

    def _mint_azure_msal_token(self) -> str:
        """AAD token for the Databricks resource — valid for account SCIM and
        workspace REST calls on Azure (matches SatDBClient.getAzureTokenWithMSAL)."""
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
            headers={"Content-Type": "application/x-www-form-urlencoded"},
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

    def _mint_workspace_token(self, host: str) -> Optional[str]:
        if self._cloud_type == "azure":
            return self._acct_token
        resp = requests.post(
            f"{host}/oidc/v1/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._client_id,
                "client_secret": self._client_secret,
                "scope":         "all-apis",
            },
            proxies=self._proxies,
        )
        return resp.json().get("access_token") if resp.ok else None

    # ── SCIM paging helper ─────────────────────────────────────────────────────

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

    @staticmethod
    def _has_account_admin(entity: dict) -> bool:
        return any(r.get("value") == "account_admin" for r in entity.get("roles", []) or [])

    @staticmethod
    def _is_idp_managed(entity: dict) -> bool:
        # Presence of an externalId means the identity was provisioned from an IdP.
        return bool(entity.get("externalId"))

    # ── Detection ──────────────────────────────────────────────────────────────

    def detect_account_admins(self, include_idp: bool) -> list[dict]:
        """Groups / users / SPs holding the account_admin role."""
        findings: list[dict] = []

        specs = [
            ("Groups",            "AccountGroup",            "id,displayName,roles,externalId"),
            ("Users",             "AccountUser",             "id,userName,displayName,roles,externalId"),
            ("ServicePrincipals", "AccountServicePrincipal", "id,applicationId,displayName,roles,externalId"),
        ]
        for resource, ptype, attrs in specs:
            for e in self._scim_list(resource, attrs):
                if not self._has_account_admin(e):
                    continue
                idp = self._is_idp_managed(e)
                if idp and not include_idp:
                    continue
                findings.append({
                    "finding_type":   "account_admin",
                    "principal_type": ptype,
                    "principal_id":   e.get("id"),
                    "principal_name": e.get("displayName") or e.get("userName") or e.get("applicationId"),
                    "principal_email": e.get("userName") if ptype == "AccountUser" else None,
                    "application_id": e.get("applicationId") if ptype == "AccountServicePrincipal" else None,
                    "is_idp_managed": idp,
                    "external_id":    e.get("externalId"),
                    "scope":          "account",
                    "workspace_id":   None,
                    "workspace_name": None,
                })
        return findings

    def detect_workspace_admins(self, workspaces: list[dict], include_idp: bool) -> tuple[list[dict], list[str]]:
        """Members of each workspace's 'admins' group. Returns (findings, workspaces_scanned).

        Each workspace is probed independently and defensively: a workspace the
        compute can't reach (DNS/egress) or the SP isn't a member of is skipped,
        not fatal. Only workspaces successfully queried appear in `scanned`.
        """
        findings: list[dict] = []
        scanned: list[str] = []

        # Build an account-level lookup of externalId by SCIM id so we can tell
        # which admin-group members are IdP-managed.
        idp_by_id: dict[str, bool] = {}
        for resource, attrs in [("Groups", "id,externalId"), ("Users", "id,externalId"),
                                ("ServicePrincipals", "id,externalId")]:
            for e in self._scim_list(resource, attrs):
                idp_by_id[str(e.get("id"))] = self._is_idp_managed(e)

        for ws in workspaces:
            host = ws.get("workspace_url")
            ws_id = str(ws.get("workspace_id"))
            ws_name = ws.get("workspace_name")
            if not host:
                continue
            try:
                token = self._mint_workspace_token(host)
                if not token:
                    continue  # SP not a member of this workspace
                hdrs = {"Authorization": f"Bearer {token}"}
                # Find the workspace 'admins' group and expand members.
                admins_filter = urllib.parse.quote('displayName eq "admins"')
                resp = requests.get(
                    f"{host}/api/2.0/preview/scim/v2/Groups"
                    f"?filter={admins_filter}&attributes=id,members",
                    headers=hdrs, proxies=self._proxies, timeout=15,
                )
                if not resp.ok:
                    continue
                groups = resp.json().get("Resources", [])
            except Exception as e:
                # Unreachable workspace (DNS/egress), timeout, or auth issue —
                # skip it rather than failing the whole run.
                print(f"  ⚠ Skipping workspace {ws_name or ws_id}: {type(e).__name__}")
                continue
            scanned.append(ws_name or ws_id)
            for g in groups:
                for m in g.get("members", []) or []:
                    ref = m.get("$ref", "") or ""
                    if "Users" in ref:
                        ptype = "User"
                    elif "ServicePrincipals" in ref:
                        ptype = "ServicePrincipal"
                    elif "Groups" in ref:
                        ptype = "Group"
                    else:
                        ptype = "User"
                    mid = str(m.get("value"))
                    idp = idp_by_id.get(mid, False)
                    if idp and not include_idp:
                        continue
                    findings.append({
                        "finding_type":   "workspace_admin",
                        "principal_type": ptype,
                        "principal_id":   mid,
                        "principal_name": m.get("display"),
                        "principal_email": None,
                        "application_id": None,
                        "is_idp_managed": idp,
                        "external_id":    None,
                        "scope":          "workspace",
                        "workspace_id":   ws_id,
                        "workspace_name": ws_name,
                    })
        return findings, scanned

    # ── Remediation ────────────────────────────────────────────────────────────

    def remediate_account_admin(self, ptype: str, principal_id: str) -> RemediationResult:
        """Remove the account_admin role from an account group/user/SP via SCIM PATCH."""
        resource = {"AccountGroup": "Groups", "AccountUser": "Users",
                    "AccountServicePrincipal": "ServicePrincipals"}.get(ptype)
        if not resource:
            return RemediationResult(ptype, principal_id, "account_admin", False, "unknown principal type")
        url = f"{self._accounts_host}/api/2.0/accounts/{self._account_id}/scim/v2/{resource}/{principal_id}"
        body = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "remove", "path": "roles[value eq \"account_admin\"]"}],
        }
        resp = requests.patch(url, headers={**self._acct_hdrs, "Content-Type": "application/scim+json"},
                              json=body, proxies=self._proxies)
        return RemediationResult(
            ptype, principal_id, "account_admin", resp.ok,
            "account_admin removed" if resp.ok else f"PATCH {resp.status_code}: {resp.text[:200]}",
        )


# COMMAND ----------

# DBTITLE 1,Initialize Auditor & Enumerate Workspaces
auditor = PrivilegedIdentityAuditor(
    accounts_host = ACCOUNTS_HOST,
    account_id    = ACCOUNT_ID,
    client_id     = CLIENT_ID,
    client_secret = CLIENT_SECRET,
    cloud_type    = cloud_type,
    tenant_id     = TENANT_ID,
    proxies       = json_.get("proxies", {}),
)
print("✓ Auditor initialized")

# Enumerate RUNNING workspaces for workspace-admin detection.
workspaces = []
if "workspace_admin" in FINDING_TYPES:
    try:
        wl = spark.sql("""
            SELECT workspace_id, workspace_name, workspace_url
            FROM system.access.workspaces_latest
            WHERE status = 'RUNNING'
        """).toPandas()
        workspaces = wl.to_dict("records")
        print(f"Found {len(workspaces)} RUNNING workspace(s) to consider for workspace-admin detection")
    except Exception as e:
        print(f"⚠ Could not enumerate workspaces from system.access.workspaces_latest: {e}")

# COMMAND ----------

# DBTITLE 1,Detect Privileged Identities
all_findings: list[dict] = []
workspaces_scanned: list[str] = []

if "account_admin" in FINDING_TYPES:
    aa = auditor.detect_account_admins(INCLUDE_IDP_MANAGED)
    print(f"Account Admin findings: {len(aa)}")
    all_findings.extend(aa)

if "workspace_admin" in FINDING_TYPES and workspaces:
    wa, workspaces_scanned = auditor.detect_workspace_admins(workspaces, INCLUDE_IDP_MANAGED)
    print(f"Workspace Admin findings: {len(wa)} (across {len(workspaces_scanned)} workspace(s))")
    all_findings.extend(wa)

findings = pd.DataFrame(all_findings)
findings["auto_remediated"] = False
print(f"\nTotal findings: {len(findings)}")

# COMMAND ----------

# DBTITLE 1,Remediate (opt-in)
if REMEDIATE and not findings.empty:
    print("Remediating...\n")
    results = []
    # Only account_admin remediation is supported programmatically here;
    # workspace-admin membership removal requires per-workspace group PATCH and
    # is intentionally left manual for v1 (flagged in output).
    for _, row in findings[findings["finding_type"] == "account_admin"].iterrows():
        r = auditor.remediate_account_admin(row["principal_type"], row["principal_id"])
        results.append(r)
        print(r)
    ok_ids = {r.principal_id for r in results if r.success}
    findings["auto_remediated"] = findings.apply(
        lambda x: x["finding_type"] == "account_admin" and x["principal_id"] in ok_ids, axis=1
    )
    ws_admin_n = int((findings["finding_type"] == "workspace_admin").sum())
    if ws_admin_n:
        print(f"\nℹ {ws_admin_n} workspace-admin finding(s) not auto-remediated "
              "(remove from the workspace 'admins' group manually).")
elif REMEDIATE:
    print("Remediation enabled, but no findings to remediate.")
else:
    print("Remediation not enabled — set the 'remediate' widget to 'yes' to take action.")

# COMMAND ----------

# DBTITLE 1,Persist Findings to Delta
import json as _json
import uuid
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, BooleanType,
)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
DETECTION_TIME = datetime.now(timezone.utc)
print(f"Run ID: {RUN_ID}")

findings_schema = StructType([
    StructField("run_id",              StringType(),    False),
    StructField("detection_timestamp", TimestampType(), False),
    StructField("finding_type",        StringType(),    False),
    StructField("principal_type",      StringType(),    True),
    StructField("principal_id",        StringType(),    True),
    StructField("principal_name",      StringType(),    True),
    StructField("principal_email",     StringType(),    True),
    StructField("application_id",      StringType(),    True),
    StructField("is_idp_managed",      BooleanType(),   True),
    StructField("external_id",         StringType(),    True),
    StructField("scope",               StringType(),    True),
    StructField("workspace_id",        StringType(),    True),
    StructField("workspace_name",      StringType(),    True),
    StructField("workspaces_scanned",  StringType(),    True),
    StructField("auto_remediated",     BooleanType(),   True),
])

_cols = [
    "run_id", "detection_timestamp", "finding_type", "principal_type", "principal_id",
    "principal_name", "principal_email", "application_id", "is_idp_managed", "external_id",
    "scope", "workspace_id", "workspace_name", "workspaces_scanned", "auto_remediated",
]

_scanned_json = _json.dumps(workspaces_scanned)

if findings.empty:
    findings_df = spark.createDataFrame([], schema=findings_schema)
else:
    out = findings.copy()
    out["run_id"]              = RUN_ID
    out["detection_timestamp"] = DETECTION_TIME
    out["workspaces_scanned"]  = _scanned_json
    out["principal_id"]        = out["principal_id"].astype(str)
    out["workspace_id"]        = out["workspace_id"].astype("object").where(out["workspace_id"].notna(), None)
    findings_df = spark.createDataFrame(out[_cols], schema=findings_schema)

findings_df.write.format("delta").mode("append") \
    .option("mergeSchema", "true") \
    .saveAsTable(PRIVILEGED_NON_IDP_TABLE)

spark.sql(
    f"COMMENT ON TABLE {PRIVILEGED_NON_IDP_TABLE} IS "
    "'SAT Permissions Analysis — privileged identities (Account Admin / Workspace Admin) that are not "
    "IdP-managed (no externalId), plus users/service principals with those roles assigned directly. "
    "auto_remediated captures opt-in remediation outcomes. Stamped with run_id for point-in-time snapshots.'"
)
for _col, _comment in {
    "run_id":              "Detection run identifier in format YYYYMMDD_HHMMSS_hash",
    "detection_timestamp": "UTC timestamp when this detection run executed",
    "finding_type":        "account_admin or workspace_admin",
    "principal_type":      "AccountGroup, AccountUser, AccountServicePrincipal, Group, User, or ServicePrincipal",
    "principal_id":        "SCIM id of the principal",
    "principal_name":      "Display name of the principal",
    "principal_email":     "Email / userName (users only)",
    "application_id":      "OAuth application id (service principals only)",
    "is_idp_managed":      "True if the principal carries an externalId (provisioned from an IdP)",
    "external_id":         "The SCIM externalId, when present",
    "scope":               "account or workspace",
    "workspace_id":        "Workspace id (workspace-admin findings only)",
    "workspace_name":      "Workspace name (workspace-admin findings only)",
    "workspaces_scanned":  "JSON array of workspace names scanned for workspace-admin membership this run",
    "auto_remediated":     "True if the privileged role/membership was removed in this run",
}.items():
    spark.sql(f"ALTER TABLE {PRIVILEGED_NON_IDP_TABLE} ALTER COLUMN `{_col}` COMMENT '{_comment}'")

print(f"Wrote {findings_df.count()} finding(s) to {PRIVILEGED_NON_IDP_TABLE} (run_id={RUN_ID})")

# COMMAND ----------

# DBTITLE 1,Display Findings
if findings.empty:
    print("✓ No privileged non-IdP-managed identities found for the selected finding types.")
else:
    display(findings_df.orderBy("finding_type", F.desc("is_idp_managed")))

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Understanding Results
# MAGIC
# MAGIC Each row is a privileged assignment. **`is_idp_managed = false`** are the primary concern:
# MAGIC privileged access held by locally-managed identities that bypass your IdP's governance.
# MAGIC
# MAGIC ### Recommended workflow
# MAGIC
# MAGIC 1. Run **report-only** (`remediate = no`) and review findings.
# MAGIC 2. For non-IdP groups, prefer replacing them with IdP-provisioned groups that carry the role.
# MAGIC 3. For direct user/SP `account_admin`, confirm the assignment is justified; otherwise re-run with
# MAGIC    `remediate = yes` to remove it.
# MAGIC 4. Workspace-admin membership is **not** auto-removed in v1 — remove members from the workspace
# MAGIC    `admins` group manually.
