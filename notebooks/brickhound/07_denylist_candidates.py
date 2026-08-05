# Databricks notebook source
# MAGIC %md
# MAGIC # Account Denylist Builder — Inactive-User Group Candidates
# MAGIC *Find IdP groups whose members mostly aren't using Databricks — good denylist candidates*
# MAGIC
# MAGIC <div style="background-color: #fff3e0; border-left: 4px solid #d32f2f; padding: 12px; margin: 16px 0;">
# MAGIC   <p style="margin: 0; font-size: 0.85em; color: #d32f2f; font-weight: bold;">⚠️ DISCLAIMER</p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #555;">
# MAGIC     "Inactive" here is a <b>heuristic</b>: a user with no <code>system.access.audit</code> activity
# MAGIC     in the look-back window. This approximates the Automatic Identity Management "Inactive: No usage"
# MAGIC     status, which is not exposed programmatically. Use outputs as a starting point for denylist
# MAGIC     decisions, not as an authoritative activity record.
# MAGIC   </p>
# MAGIC   <p style="margin: 8px 0 0 0; font-size: 0.8em; color: #d32f2f;">
# MAGIC     <b>AIM limitation:</b> With Automatic Identity Management, external/IdP group memberships are
# MAGIC     resolved just-in-time and are <b>not returned by the account SCIM Groups API</b> (members come
# MAGIC     back empty) — even though the account console <i>does</i> show those members (it reads them
# MAGIC     live from Entra). So a group can look populated in the console yet return zero members here.
# MAGIC     Because this report ranks groups by their inactive <i>members</i>, IdP groups under AIM may
# MAGIC     yield <b>no candidates even when they have many users</b>. It works for groups whose membership
# MAGIC     IS available via SCIM (e.g. traditional SCIM-provisioned groups). For AIM accounts, use the
# MAGIC     Entra ID dynamic-group rule helper in the app tab to build denylist groups instead.
# MAGIC   </p>
# MAGIC </div>
# MAGIC
# MAGIC ## What This Analysis Does
# MAGIC
# MAGIC The [account access denylist](https://learn.microsoft.com/en-gb/azure/databricks/admin/users-groups/automatic-identity-management/account-access-denylist)
# MAGIC lets you block groups of identities from accessing Databricks. Good denylist candidates are IdP
# MAGIC groups whose members largely **aren't logging into Databricks** — you can deny them without
# MAGIC disrupting active users.
# MAGIC
# MAGIC This notebook ranks **IdP-managed (external) groups** by their count of **inactive members** —
# MAGIC account users with no `system.access.audit` activity in the look-back window. Only groups that
# MAGIC carry an `externalId` (provisioned from an identity provider) are considered, since the account
# MAGIC access denylist operates on IdP groups; the built-in `account users` group and any local/system
# MAGIC groups are excluded. Findings are written to **`brickhound_denylist_candidates`**; the SAT
# MAGIC Permissions Analysis app surfaces them in the "Account Denylist Builder" tab.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC
# MAGIC - SAT installed (`sat_scope`); service principal with **Account Admin**.
# MAGIC - Access to `system.access.audit`.
# MAGIC - **Azure only:** the compute needs network egress to `login.microsoftonline.com` (Entra ID) for
# MAGIC   MSAL token minting. If serverless egress is restricted, run on a classic cluster.

# COMMAND ----------

# DBTITLE 1,Run Configuration
# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Define Widgets
dbutils.widgets.text("inactive_days", "90", "Inactive threshold (days without activity)")
dbutils.widgets.text("min_inactive", "1", "Minimum inactive members to report a group")

INACTIVE_DAYS = int(dbutils.widgets.get("inactive_days"))
MIN_INACTIVE  = int(dbutils.widgets.get("min_inactive"))
print(f"Inactive threshold: {INACTIVE_DAYS} days")
print(f"Min inactive members to report: {MIN_INACTIVE}")

# COMMAND ----------

# DBTITLE 1,Resolve Host, Credentials, Output Table
def _domain_from_url(url: str) -> str:
    host = url.split("://")[-1].split("/")[0]
    return host.split(".")[-1] if "." in host else "com"

def resolve_accounts_host(cloud: str, workspace_url: str, override: str = "") -> str:
    if override:
        return override.rstrip("/")
    domain = _domain_from_url(workspace_url)
    return {
        "aws":   f"https://accounts.cloud.databricks.{domain}",
        "gcp":   f"https://accounts.gcp.databricks.{domain}",
        "azure": f"https://accounts.azuredatabricks.{domain}",
    }[cloud]

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

DENYLIST_CANDIDATES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_denylist_candidates"
print(f"Accounts host: {ACCOUNTS_HOST}")
print(f"Output table:  {DENYLIST_CANDIDATES_TABLE}")

# COMMAND ----------

# DBTITLE 1,Collect Groups, Memberships, and Activity
import urllib.parse
from datetime import datetime, timezone

import pandas as pd
import requests
from pyspark.sql import functions as F


def mint_account_token() -> str:
    # Azure authenticates via Entra/MSAL; AWS/GCP via the Databricks OIDC path.
    if cloud_type == "azure":
        import msal
        app = msal.ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        )
        token = app.acquire_token_for_client(scopes=["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"])
        if not token or not token.get("access_token"):
            raise Exception(f"MSAL token acquisition failed: {token.get('error_description') if token else 'no token'}")
        return token["access_token"]
    resp = requests.post(
        f"{ACCOUNTS_HOST}/oidc/accounts/{ACCOUNT_ID}/v1/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": CLIENT_ID,
              "client_secret": CLIENT_SECRET, "scope": "all-apis"},
        proxies=json_.get("proxies", {}),
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

TOKEN = mint_account_token()
HDRS  = {"Authorization": f"Bearer {TOKEN}"}


def scim_list(resource: str, attributes: str) -> list:
    items, start, count = [], 1, 100
    while True:
        resp = requests.get(
            f"{ACCOUNTS_HOST}/api/2.0/accounts/{ACCOUNT_ID}/scim/v2/{resource}"
            f"?attributes={urllib.parse.quote(attributes)}&startIndex={start}&count={count}",
            headers=HDRS, proxies=json_.get("proxies", {}),
        )
        resp.raise_for_status()
        body = resp.json()
        page = body.get("Resources", [])
        items.extend(page)
        total = body.get("totalResults", len(items))
        if start + count > total or not page:
            break
        start += count
    return items

# Account users: id -> (userName, active, externalId)
users = scim_list("Users", "id,userName,active,externalId")
user_by_id = {str(u["id"]): u for u in users}
print(f"Account users: {len(users)}")

# Account groups with members + externalId (IdP signal)
groups = scim_list("Groups", "id,displayName,externalId,members")
print(f"Account groups: {len(groups)}")

# COMMAND ----------

# DBTITLE 1,Determine Active Users from Audit Log
active_df = spark.sql(f"""
    SELECT DISTINCT lower(user_identity.email) AS email
    FROM system.access.audit
    WHERE event_time >= current_timestamp() - INTERVAL {INACTIVE_DAYS} DAYS
      AND user_identity.email IS NOT NULL
      AND user_identity.email != 'System-User'
""")
active_emails = {r["email"] for r in active_df.collect()}
print(f"Distinct active users (last {INACTIVE_DAYS}d): {len(active_emails)}")

def is_inactive(user: dict) -> bool:
    email = (user.get("userName") or "").lower()
    return bool(email) and email not in active_emails

# COMMAND ----------

# DBTITLE 1,Rank Groups by Inactive Members
# Only IdP-managed (external) groups are eligible for the account access denylist —
# the denylist operates on identity-provider groups. This also naturally excludes
# the built-in 'account users' group and any local/system groups.
rows = []
skipped_local = 0
for g in groups:
    if not g.get("externalId"):
        skipped_local += 1
        continue
    members = g.get("members", []) or []
    total_members = 0
    inactive_members = 0
    for m in members:
        ref = m.get("$ref", "") or ""
        # Only count user members toward activity (groups/SPs excluded from the ratio)
        if "Users" not in ref:
            continue
        u = user_by_id.get(str(m.get("value")))
        if not u:
            continue
        total_members += 1
        if is_inactive(u):
            inactive_members += 1

    # An IdP group is a denylist candidate if it has inactive members OR has no
    # user members at all. A zero-member group is a strong candidate: an IdP
    # group with no active Databricks users is safe to deny. (Under AIM, SCIM
    # returns members empty for external groups, so most land here — see the AIM
    # note above.)
    if inactive_members >= MIN_INACTIVE or total_members == 0:
        gid = str(g["id"])
        reason = "no members via SCIM" if total_members == 0 else "has inactive members"
        rows.append({
            "group_id":         gid,
            "group_name":       g.get("displayName"),
            "is_idp_managed":   bool(g.get("externalId")),
            "total_members":    total_members,
            "inactive_members": inactive_members,
            "active_members":   total_members - inactive_members,
            "inactive_pct":     round(100.0 * inactive_members / total_members, 1) if total_members else 0.0,
            "candidate_reason": reason,
            # Deep link to the account-console group detail page for investigation.
            "console_url":      f"{ACCOUNTS_HOST}/user-management/groups/{gid}?account_id={ACCOUNT_ID}",
        })

# Order: groups with inactive members first (by count, then %), then zero-member groups.
candidates = pd.DataFrame(rows).sort_values(
    ["inactive_members", "inactive_pct"], ascending=False
) if rows else pd.DataFrame()
print(f"Skipped {skipped_local} local/non-IdP group(s) (not denylist-eligible).")
print(f"Candidate IdP groups (inactive members or zero members): {len(candidates)}")

# COMMAND ----------

# DBTITLE 1,Persist to Delta
import uuid
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, BooleanType, IntegerType, DoubleType,
)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
DETECTION_TIME = datetime.now(timezone.utc)
print(f"Run ID: {RUN_ID}")

schema = StructType([
    StructField("run_id",              StringType(),    False),
    StructField("detection_timestamp", TimestampType(), False),
    StructField("inactive_days",       IntegerType(),   True),
    StructField("group_id",            StringType(),    True),
    StructField("group_name",          StringType(),    True),
    StructField("is_idp_managed",      BooleanType(),   True),
    StructField("total_members",       IntegerType(),   True),
    StructField("inactive_members",    IntegerType(),   True),
    StructField("active_members",      IntegerType(),   True),
    StructField("inactive_pct",        DoubleType(),    True),
    StructField("candidate_reason",    StringType(),    True),
    StructField("console_url",         StringType(),    True),
])
_cols = ["run_id", "detection_timestamp", "inactive_days", "group_id", "group_name",
         "is_idp_managed", "total_members", "inactive_members", "active_members", "inactive_pct",
         "candidate_reason", "console_url"]

if candidates.empty:
    cand_df = spark.createDataFrame([], schema=schema)
else:
    out = candidates.copy()
    out["run_id"]              = RUN_ID
    out["detection_timestamp"] = DETECTION_TIME
    out["inactive_days"]       = INACTIVE_DAYS
    cand_df = spark.createDataFrame(out[_cols], schema=schema)

cand_df.write.format("delta").mode("append").option("mergeSchema", "true") \
    .saveAsTable(DENYLIST_CANDIDATES_TABLE)

spark.sql(
    f"COMMENT ON TABLE {DENYLIST_CANDIDATES_TABLE} IS "
    "'SAT Permissions Analysis — account groups ranked by inactive-member count, as candidates for the "
    "account access denylist. Inactive = no system.access.audit activity within inactive_days (a heuristic "
    "approximating the Automatic Identity Management No-usage status). Stamped with run_id.'"
)
for _col, _comment in {
    "run_id":              "Detection run identifier in format YYYYMMDD_HHMMSS_hash",
    "detection_timestamp": "UTC timestamp when this detection run executed",
    "inactive_days":       "Look-back window (days) used to classify a user as inactive",
    "group_id":            "Account SCIM group id",
    "group_name":          "Account group display name",
    "is_idp_managed":      "True if the group carries an externalId (provisioned from an IdP)",
    "total_members":       "Count of user members in the group",
    "inactive_members":    "User members with no audit activity in the window",
    "active_members":      "User members with audit activity in the window",
    "inactive_pct":        "inactive_members / total_members as a percentage",
    "candidate_reason":    "Why the group is a candidate: has inactive members, or no members via SCIM",
    "console_url":         "Deep link to the account-console group detail page",
}.items():
    spark.sql(f"ALTER TABLE {DENYLIST_CANDIDATES_TABLE} ALTER COLUMN `{_col}` COMMENT '{_comment.replace(chr(39), chr(39)*2)}'")

print(f"Wrote {cand_df.count()} candidate group(s) to {DENYLIST_CANDIDATES_TABLE} (run_id={RUN_ID})")

# COMMAND ----------

# DBTITLE 1,Display
if candidates.empty:
    print("✓ No candidate groups found for the current threshold.")
else:
    display(cand_df.orderBy(F.desc("inactive_members"), F.desc("inactive_pct")))
