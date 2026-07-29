# Databricks notebook source
# MAGIC %md
# MAGIC # Shared to All Account Users — Detection & Remediation
# MAGIC *Detect (and optionally undo) resources shared with every user in the account*
# MAGIC
# MAGIC <div style="background-color: #fff3e0; border-left: 4px solid #d32f2f; padding: 12px; margin: 16px 0;">
# MAGIC   <p style="margin: 0; font-size: 0.85em; color: #d32f2f; font-weight: bold;">⚠️ DISCLAIMER</p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #555;">
# MAGIC     This tool may have incomplete data. Outputs are visibility and audit aids, not authoritative compliance determinations.
# MAGIC     Remediation (removing an ACL entry) is a <b>destructive, opt-in</b> action — review findings before enabling it.
# MAGIC   </p>
# MAGIC </div>
# MAGIC
# MAGIC ## What This Analysis Does
# MAGIC
# MAGIC Sharing a resource with the built-in **account users** group grants access to *every user in the
# MAGIC Databricks account* — a common, high-impact over-sharing / privilege-escalation path. This notebook
# MAGIC detects such shares from the audit log and can optionally remove the offending ACL entry.
# MAGIC
# MAGIC Supported resource types:
# MAGIC
# MAGIC | Resource | Audit action | ACL resource prefix |
# MAGIC |---|---|---|
# MAGIC | Lakeview dashboards | `changeWorkspaceAcl` | `dashboardsv3/` |
# MAGIC | AI/BI Genie Agents  | `changeWorkspaceAcl` | `genie/` or `datarooms/` |
# MAGIC | Databricks Apps     | `changeAppsAcl`      | *(full ACL JSON)* |
# MAGIC
# MAGIC Workspace metadata is sourced from `system.access.workspaces_latest`. Only workspaces with
# MAGIC `status = RUNNING` in the same account as the audit event are included.
# MAGIC
# MAGIC ### Detection vs. Remediation
# MAGIC
# MAGIC - **Detection** works account-wide via the audit log and needs no per-workspace access.
# MAGIC - **Remediation** mints a workspace-scoped OAuth token from SAT's account-admin service principal,
# MAGIC   so the SP (`client-id` in `sat_scope`) must be a **member of each workspace** it needs to remediate.
# MAGIC
# MAGIC Findings (and remediation outcomes) are written to **`brickhound_shared_to_account`** in SAT's
# MAGIC analysis schema, stamped with a `run_id` for point-in-time snapshots. The SAT Permissions Analysis
# MAGIC app reads this table to surface findings in the UI.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC - SAT installed (`sat_scope` secret scope with `account-console-id`, `client-id`, `client-secret`,
# MAGIC   `analysis_schema_name`).
# MAGIC - The service principal must have **Account Admin** and be a member of any workspace you want to
# MAGIC   remediate.
# MAGIC - Access to `system.access.audit` and `system.access.workspaces_latest` system tables.
# MAGIC - **Azure only:** the compute running this notebook needs network egress to
# MAGIC   `login.microsoftonline.com` (Entra ID) to mint the account token via MSAL. If serverless egress
# MAGIC   is restricted, run this on a classic cluster (or allowlist that host).

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
# MAGIC | `resource_types` | Comma-separated list: `dashboards`, `genie`, `apps`. |
# MAGIC | `remediate` | `yes` removes the 'account users' ACL entry from every detected resource. Defaults to `no` (report-only). |

# COMMAND ----------

# DBTITLE 1,Define Widgets
dbutils.widgets.text("last_n_days", "30", "Look-back window (days)")
dbutils.widgets.text("resource_types", "dashboards,genie,apps", "Resource types (comma-separated)")
dbutils.widgets.dropdown("remediate", "no", ["no", "yes"], "Remove account users access")

LAST_N_DAYS    = int(dbutils.widgets.get("last_n_days"))
RESOURCE_TYPES = [t.strip() for t in dbutils.widgets.get("resource_types").split(",") if t.strip()]
REMEDIATE      = dbutils.widgets.get("remediate") == "yes"

print(f"Look-back window: {LAST_N_DAYS} days")
print(f"Resource types:   {RESOURCE_TYPES}")
print(f"Remediate:        {REMEDIATE}")

# COMMAND ----------

# DBTITLE 1,Resolve Account Host, Credentials, and Output Table
# `00_config` chains through Utils/initialize -> Utils/common, exposing:
#   - SECRETS_SCOPE, CATALOG, SCHEMA
#   - json_ (account_id, accounts_console, ...), cloud_type, getCloudType()
# We derive the accounts host per cloud (mirrors core/dbclient.py) rather than
# hardcoding a single cloud, honoring the accounts_console override for GovCloud/DoD.

def _domain_from_url(url: str) -> str:
    """Extract the top-level domain suffix (e.g. 'com', 'net', 'us') from a workspace URL."""
    host = url.split("://")[-1].split("/")[0]
    return host.split(".")[-1] if "." in host else "com"

def resolve_accounts_host(cloud: str, workspace_url: str, accounts_console_override: str = "") -> str:
    """Return the accounts console base URL for the given cloud.

    Prefers an explicit accounts_console override (required for GovCloud/DoD),
    otherwise constructs the standard host from the workspace URL's domain.
    """
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

# Current workspace URL (used to derive the domain suffix)
WORKSPACE_URL = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook().getContext().apiUrl().getOrElse(None)
)

ACCOUNTS_HOST = resolve_accounts_host(
    cloud_type, WORKSPACE_URL, json_.get("accounts_console", "")
)
ACCOUNT_ID    = json_["account_id"]
CLIENT_ID     = dbutils.secrets.get(scope=SECRETS_SCOPE, key="client-id")
CLIENT_SECRET = dbutils.secrets.get(scope=SECRETS_SCOPE, key="client-secret")

# tenant-id is required for Azure (Entra/MSAL auth); absent on AWS/GCP.
TENANT_ID = None
if cloud_type == "azure":
    TENANT_ID = json_.get("tenant_id") or dbutils.secrets.get(scope=SECRETS_SCOPE, key="tenant-id")

SHARED_TO_ACCOUNT_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_shared_to_account"

print(f"Cloud type:     {cloud_type}")
print(f"Accounts host:  {ACCOUNTS_HOST}")
print(f"Output table:   {SHARED_TO_ACCOUNT_TABLE}")

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


@dataclass(frozen=True)
class RemediationResult:
    workspace_id:  str
    resource_id:   str
    resource_type: str
    success:       bool
    message:       str

    def __str__(self) -> str:
        icon = "✓" if self.success else "✗"
        return f"{icon} [{self.resource_type}] {self.resource_id} (ws={self.workspace_id}): {self.message}"


class ResourceShareAuditor:
    """Audit and optionally remediate Lakeview dashboards, Genie Agents, and
    Databricks Apps shared with the 'account users' group.

    Detection reads the audit log account-wide. Remediation mints one
    workspace-scoped OAuth token per workspace in parallel, then removes the
    offending ACL entry per resource in parallel.
    """

    # Resource type -> permissions API path template ({host}/api/2.0/...)
    PERMISSIONS_API = {
        "dashboards": "/api/2.0/permissions/dashboards/{id}",
        "genie":      "/api/2.0/permissions/genie/{id}",
        "apps":       "/api/2.0/permissions/apps/{id}",
    }

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
        self.group_id, self.group_name = self._resolve_group()

    # ── Token / group helpers ──────────────────────────────────────────────

    def _mint_azure_msal_token(self) -> str:
        """AAD token for the Databricks resource — valid for account SCIM and
        workspace REST calls on Azure (matches SatDBClient.getAzureTokenWithMSAL)."""
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
        )
        # Databricks programmatic scope.
        token = app.acquire_token_for_client(scopes=["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"])
        if not token or not token.get("access_token"):
            raise Exception(f"MSAL token acquisition failed: {token.get('error_description') if token else 'no token'}")
        return token["access_token"]

    def _mint_account_token(self) -> str:
        # Azure authenticates via Entra/MSAL; AWS/GCP via the Databricks OIDC path.
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

    def _resolve_group(self) -> tuple[str, str]:
        filter_q = urllib.parse.quote('displayName co "account users"')
        resp = requests.get(
            f"{self._accounts_host}/api/2.0/accounts/{self._account_id}/scim/v2/Groups"
            f"?filter={filter_q}&attributes=id,displayName",
            headers=self._acct_hdrs,
            proxies=self._proxies,
        )
        resp.raise_for_status()
        groups = resp.json().get("Resources", [])
        if not groups:
            raise ValueError("Could not find 'account users' group in account SCIM")
        return groups[0]["id"], groups[0]["displayName"]

    def _mint_workspace_token(self, host: str) -> Optional[str]:
        # On Azure the Databricks-scoped MSAL token is valid for workspace REST
        # calls too, so reuse it. AWS/GCP mint a per-workspace OIDC token.
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

    def _resolve_display_names(self, emails: list[str]) -> dict[str, str]:
        """Map user email -> display name via account SCIM Users.

        The audit log only records the sharer's email; the UI wants
        "Full Name (email)" like the other reports. Best-effort: any email we
        can't resolve is simply omitted (the UI falls back to the email).
        """
        name_map: dict[str, str] = {}
        for email in emails:
            try:
                filter_q = urllib.parse.quote(f'userName eq "{email}"')
                resp = requests.get(
                    f"{self._accounts_host}/api/2.0/accounts/{self._account_id}/scim/v2/Users"
                    f"?filter={filter_q}&attributes=displayName,userName",
                    headers=self._acct_hdrs,
                    proxies=self._proxies,
                )
                if resp.ok:
                    users = resp.json().get("Resources", [])
                    if users and users[0].get("displayName"):
                        name_map[email] = users[0]["displayName"]
            except Exception:
                pass  # best-effort; UI falls back to email
        return name_map

    # ── Remediation ────────────────────────────────────────────────────────

    def _remove_permission(self, workspace_id: str, host: str, token: str,
                           resource_id: str, resource_type: str) -> RemediationResult:
        """Remove 'account users' from a resource's ACL via GET -> filter -> PUT."""
        path = self.PERMISSIONS_API.get(resource_type, "").format(id=resource_id)
        if not path:
            return RemediationResult(workspace_id, resource_id, resource_type, False, "unknown resource type")

        url  = f"{host}{path}"
        hdrs = {"Authorization": f"Bearer {token}"}

        get_resp = requests.get(url, headers=hdrs, proxies=self._proxies)
        if not get_resp.ok:
            return RemediationResult(
                workspace_id, resource_id, resource_type, False,
                f"GET {get_resp.status_code}: {get_resp.text[:200]}",
            )

        data    = get_resp.json()
        acl_key = "access_control_list"
        acl     = data.get(acl_key, [])

        new_acl: list[dict] = []
        removed = False
        for entry in acl:
            principal = {
                k: entry[k]
                for k in ("user_name", "group_name", "service_principal_name")
                if k in entry
            }
            if not principal:
                continue
            if entry.get("group_name") == self.group_name:
                removed = True
                continue
            # Flatten all_permissions (dashboards/genie) or keep permission_level (apps)
            if "all_permissions" in entry:
                for perm in entry["all_permissions"]:
                    if not perm.get("inherited", False):
                        new_acl.append({**principal, "permission_level": perm["permission_level"]})
            elif "permission_level" in entry:
                new_acl.append({**principal, "permission_level": entry["permission_level"]})

        if not removed:
            return RemediationResult(workspace_id, resource_id, resource_type, True, "already removed")

        put_resp = requests.put(url, headers=hdrs, json={acl_key: new_acl}, proxies=self._proxies)
        return RemediationResult(
            workspace_id, resource_id, resource_type, put_resp.ok,
            "permission removed" if put_resp.ok else f"PUT {put_resp.status_code}: {put_resp.text[:200]}",
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def query_events(self, last_n_days: int, resource_types: list[str]) -> pd.DataFrame:
        """Query share events for the selected resource types from the audit log."""
        since       = (datetime.now(timezone.utc) - timedelta(days=last_n_days)).strftime("%Y-%m-%d")
        subqueries: list[str] = []

        if "dashboards" in resource_types:
            subqueries.append(f"""
                SELECT
                    'dashboards' AS resource_type,
                    a.event_time,
                    a.event_date,
                    a.workspace_id,
                    w.workspace_name,
                    w.workspace_url,
                    a.user_identity.email                                         AS shared_by,
                    split_part(a.request_params['aclChangeResourceName'], '/', 2) AS resource_id,
                    a.request_params['aclPermissionSet']                          AS permission
                FROM system.access.audit a
                INNER JOIN system.access.workspaces_latest w
                        ON a.workspace_id = w.workspace_id
                       AND a.account_id   = w.account_id
                       AND w.status       = 'RUNNING'
                WHERE a.action_name = 'changeWorkspaceAcl'
                  AND a.request_params['targetUserId'] = '{self.group_id}'
                  AND a.request_params['aclChangeResourceName'] LIKE 'dashboardsv3/%'
                  AND a.request_params['aclPermissionSet'] != ''
                  AND a.event_time >= '{since}'
            """)

        if "genie" in resource_types:
            subqueries.append(f"""
                SELECT
                    'genie' AS resource_type,
                    a.event_time,
                    a.event_date,
                    a.workspace_id,
                    w.workspace_name,
                    w.workspace_url,
                    a.user_identity.email                                         AS shared_by,
                    split_part(a.request_params['aclChangeResourceName'], '/', 2) AS resource_id,
                    a.request_params['aclPermissionSet']                          AS permission
                FROM system.access.audit a
                INNER JOIN system.access.workspaces_latest w
                        ON a.workspace_id = w.workspace_id
                       AND a.account_id   = w.account_id
                       AND w.status       = 'RUNNING'
                WHERE a.action_name = 'changeWorkspaceAcl'
                  AND a.request_params['targetUserId'] = '{self.group_id}'
                  AND (   a.request_params['aclChangeResourceName'] LIKE 'genie/%'
                       OR a.request_params['aclChangeResourceName'] LIKE 'datarooms/%')
                  AND a.request_params['aclPermissionSet'] != ''
                  AND a.event_time >= '{since}'
            """)

        if "apps" in resource_types:
            subqueries.append(f"""
                SELECT
                    'apps' AS resource_type,
                    a.event_time,
                    a.event_date,
                    a.workspace_id,
                    w.workspace_name,
                    w.workspace_url,
                    a.user_identity.email                 AS shared_by,
                    a.request_params['request_object_id'] AS resource_id,
                    'CAN_USE'                             AS permission
                FROM system.access.audit a
                INNER JOIN system.access.workspaces_latest w
                        ON a.workspace_id = w.workspace_id
                       AND a.account_id   = w.account_id
                       AND w.status       = 'RUNNING'
                WHERE a.action_name = 'changeAppsAcl'
                  AND a.request_params['access_control_list'] LIKE '%{self.group_name}%'
                  AND a.event_time >= '{since}'
            """)

        if not subqueries:
            return pd.DataFrame()

        sql = " UNION ALL ".join(subqueries) + " ORDER BY event_time DESC"
        df  = spark.sql(sql).toPandas()

        if df.empty:
            return df

        df["group_name"]      = self.group_name
        df["group_id"]        = self.group_id
        df["auto_remediated"] = False

        # Resolve the sharer's email -> display name (audit log only has email)
        # so the UI can show "Full Name (email)" like the other reports.
        unique_emails = [e for e in df["shared_by"].dropna().unique() if e]
        name_map = self._resolve_display_names(unique_emails)
        df["shared_by_display_name"] = df["shared_by"].map(lambda e: name_map.get(e))

        def make_url(row):
            base = row["workspace_url"].rstrip("/") if row.get("workspace_url") else ""
            if row["resource_type"] == "dashboards":
                return f"{base}/dashboardsv3/{row['resource_id']}"
            elif row["resource_type"] == "genie":
                return f"{base}/genie/rooms/{row['resource_id']}"
            elif row["resource_type"] == "apps":
                return f"{base}/apps/{row['resource_id']}"
            return ""
        df["resource_url"] = df.apply(make_url, axis=1)

        return df

    def remediate(self, events: pd.DataFrame, pilot_user: Optional[str] = None,
                  max_workers: int = 8) -> list[RemediationResult]:
        """Remove 'account users' access from all resources in `events`.

        `pilot_user` (optional) limits remediation to events shared by that user —
        useful for a controlled first pass before a full sweep.
        """
        to_process = (
            events[events["shared_by"] == pilot_user].copy()
            if pilot_user else events.copy()
        )
        skipped = len(events) - len(to_process)
        if skipped:
            print(f"  Skipping {skipped} row(s) (pilot guard: '{pilot_user}').")
        if to_process.empty:
            print("  No events to remediate.")
            return []

        # Phase 1 — mint one token per unique workspace
        ws_hosts: dict[str, str] = {
            str(row["workspace_id"]): row["workspace_url"]
            for _, row in to_process.drop_duplicates("workspace_id").iterrows()
            if row.get("workspace_url")
        }
        token_map: dict[str, Optional[str]] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(ws_hosts) or 1)) as pool:
            futures = {
                pool.submit(self._mint_workspace_token, host): ws_id
                for ws_id, host in ws_hosts.items()
            }
            for future in as_completed(futures):
                ws_id = futures[future]
                token = future.result()
                if not token:
                    print(f"  Token mint failed for workspace {ws_id} — SP may not be a member.")
                token_map[ws_id] = token

        # Phase 2 — remove permissions in parallel
        tasks:          list[tuple[str, str, str, str, str]] = []
        early_failures: list[RemediationResult]              = []
        for _, row in to_process.iterrows():
            ws_id  = str(row["workspace_id"])
            res_id = row["resource_id"]
            rtype  = row["resource_type"]
            host   = ws_hosts.get(ws_id)
            token  = token_map.get(ws_id)
            if not host:
                early_failures.append(RemediationResult(ws_id, res_id, rtype, False, "no workspace URL"))
            elif not token:
                early_failures.append(RemediationResult(ws_id, res_id, rtype, False, "token unavailable"))
            else:
                tasks.append((ws_id, host, token, res_id, rtype))

        results: list[RemediationResult] = list(early_failures)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures_map = {
                pool.submit(self._remove_permission, ws_id, host, token, res_id, rtype): None
                for ws_id, host, token, res_id, rtype in tasks
            }
            for future in as_completed(futures_map):
                results.append(future.result())

        for result in sorted(results, key=lambda r: (r.resource_type, r.workspace_id, r.resource_id)):
            print(result)
        return results

# COMMAND ----------

# DBTITLE 1,Initialize Auditor
auditor = ResourceShareAuditor(
    accounts_host = ACCOUNTS_HOST,
    account_id    = ACCOUNT_ID,
    client_id     = CLIENT_ID,
    client_secret = CLIENT_SECRET,
    cloud_type    = cloud_type,
    tenant_id     = TENANT_ID,
    proxies       = json_.get("proxies", {}),
)
print(f"Group: '{auditor.group_name}'  (id={auditor.group_id})")

# COMMAND ----------

# DBTITLE 1,Detect Share Events
events = auditor.query_events(LAST_N_DAYS, RESOURCE_TYPES)
print(f"Found {len(events)} share event(s) in the last {LAST_N_DAYS} days.")

# COMMAND ----------

# DBTITLE 1,Remediate (opt-in)
if REMEDIATE and not events.empty:
    print("Remediating...\n")
    results       = auditor.remediate(events)
    result_lookup = {r.resource_id: r for r in results}

    def _status(resource_id, want_message):
        r = result_lookup.get(resource_id)
        return bool(r and r.success and r.message == want_message)

    # Treat both "permission removed" (removed now) and "already removed"
    # (target ACL absent at PUT time) as remediated — we can't reliably tell
    # them apart, so we don't track a separate previously_remediated flag.
    events["auto_remediated"] = events["resource_id"].map(
        lambda x: _status(x, "permission removed") or _status(x, "already removed")
    )
elif REMEDIATE:
    print("Remediation enabled, but no events to remediate.")
else:
    print("Remediation not enabled — set the 'remediate' widget to 'yes' to take action.")

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
    StructField("run_id",                 StringType(),    False),
    StructField("detection_timestamp",    TimestampType(), False),
    StructField("resource_type",          StringType(),    False),
    StructField("resource_id",            StringType(),    True),
    StructField("workspace_id",           StringType(),    True),
    StructField("workspace_name",         StringType(),    True),
    StructField("resource_url",           StringType(),    True),
    StructField("shared_by",              StringType(),    True),
    StructField("shared_by_display_name", StringType(),    True),
    StructField("permission",             StringType(),    True),
    StructField("group_name",             StringType(),    True),
    StructField("group_id",               StringType(),    True),
    StructField("event_time",             TimestampType(), True),
    StructField("event_date",             DateType(),      True),
    StructField("auto_remediated",        BooleanType(),   True),
])

_cols = [
    "run_id", "detection_timestamp", "resource_type", "resource_id", "workspace_id",
    "workspace_name", "resource_url", "shared_by", "shared_by_display_name", "permission",
    "group_name", "group_id", "event_time", "event_date", "auto_remediated",
]

if events.empty:
    findings_df = spark.createDataFrame([], schema=findings_schema)
else:
    out = events.copy()
    out["run_id"]              = RUN_ID
    out["detection_timestamp"] = DETECTION_TIME
    out["workspace_id"]        = out["workspace_id"].astype(str)
    findings_df = spark.createDataFrame(out[_cols], schema=findings_schema)

findings_df.write.format("delta").mode("append") \
    .option("mergeSchema", "true") \
    .saveAsTable(SHARED_TO_ACCOUNT_TABLE)

spark.sql(
    f"COMMENT ON TABLE {SHARED_TO_ACCOUNT_TABLE} IS "
    "'SAT Permissions Analysis — resources (Lakeview dashboards, AI/BI Genie Agents, Databricks Apps) "
    "shared with the built-in account users group, detected from system.access.audit. "
    "Each row is one share event; auto_remediated captures opt-in remediation outcomes. "
    "Stamped with run_id for point-in-time snapshots.'"
)
for _col, _comment in {
    "run_id":                 "Detection run identifier in format YYYYMMDD_HHMMSS_hash",
    "detection_timestamp":    "UTC timestamp when this detection run executed",
    "resource_type":          "Resource type: dashboards, genie, or apps",
    "resource_id":            "Resource UUID (dashboards/genie) or app name (apps)",
    "workspace_id":           "Databricks workspace ID where the resource lives",
    "workspace_name":         "Workspace display name from system.access.workspaces_latest",
    "resource_url":           "Direct link to the resource in its workspace",
    "shared_by":              "Email of the user who granted the account users access",
    "shared_by_display_name": "Display name of the sharing user, resolved from account SCIM (may be null)",
    "permission":             "Permission level granted to the account users group",
    "group_name":             "Display name of the account users group",
    "group_id":               "Account SCIM ID of the account users group",
    "event_time":             "Timestamp of the share event in the audit log",
    "event_date":             "Date of the share event in the audit log",
    "auto_remediated":        "True if the account users ACL entry was removed in this run",
}.items():
    spark.sql(f"ALTER TABLE {SHARED_TO_ACCOUNT_TABLE} ALTER COLUMN `{_col}` COMMENT '{_comment}'")

print(f"Wrote {findings_df.count()} finding(s) to {SHARED_TO_ACCOUNT_TABLE} (run_id={RUN_ID})")

# COMMAND ----------

# DBTITLE 1,Display Findings
if events.empty:
    print("✓ No resources shared to all account users in the selected window.")
else:
    display(findings_df.orderBy(F.desc("event_time")))

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC ## Understanding Results
# MAGIC
# MAGIC Each row is a share event where a resource was granted to the **account users** group
# MAGIC (every user in the account).
# MAGIC
# MAGIC ### Remediation status
# MAGIC
# MAGIC - **`auto_remediated = true`** — the 'account users' ACL entry is no longer present after this
# MAGIC   run (removed now, or already absent at the time we checked — we don't distinguish the two).
# MAGIC - **`auto_remediated = false`** — the resource is still shared to all account users (report-only
# MAGIC   run, or remediation failed — check the cell output for token/permission errors).
# MAGIC
# MAGIC ### Recommended workflow
# MAGIC
# MAGIC 1. Run **report-only** (`remediate = no`) and review findings.
# MAGIC 2. Confirm the SP is a member of the affected workspaces (remediation mints per-workspace tokens).
# MAGIC 3. Re-run with `remediate = yes` to remove the offending ACL entries.
# MAGIC 4. Schedule this notebook (see `terraform/common/brickhound_share_to_account_job.tf`) to keep
# MAGIC    detection fresh. Leave `remediate = no` in the job unless you intend continuous auto-remediation.
