# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 6. create_sat_genie_space.
# MAGIC **Functionality:** Creates or refreshes the SAT AI/BI Genie space. Loads
# MAGIC `configs/sat_genie_space_template.json`, substitutes the customer's SAT catalog+schema for the
# MAGIC `{UC_SCHEMA}` placeholder, and POSTs to `/api/2.0/genie/spaces`. Runs only when `enable_genie_space` was
# MAGIC set to true during installation. Pattern mirrors `5. import_dashboard_template_lakeview.py`.

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

if not json_.get("enable_genie_space", False):
    print("Genie space creation disabled (enable_genie_space is false). Skipping.")
    dbutils.notebook.exit("OK")

# COMMAND ----------

# The Genie space is created in the CURRENT workspace (where this notebook runs), so we just need
# the local API host and a bearer token. The notebook execution context provides both — whether
# the notebook runs interactively or as the job's run_as principal.
import json
import requests

_ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
DOMAIN = _ctx.apiUrl().getOrElse(None).replace("https://", "")
token = _ctx.apiToken().getOrElse(None)

GENIE_SPACE_TITLE = "Security Analysis Tool [SAT]"
GENIE_PARENT_PATH = f"{basePath()}/genie"
TEMPLATE_PATH = f"{basePath()}/configs/sat_genie_space_template.json"

# analysis_schema_name is stored as `catalog`.schema — strip backticks so the three-part FQN
# in the template identifiers (e.g. catalog.schema.security_checks) is a clean UC name.
uc_schema = json_["analysis_schema_name"].replace("`", "")

with open(TEMPLATE_PATH, "r") as f:
    serialized_space_raw = f.read().replace("{UC_SCHEMA}", uc_schema)

# The Genie export proto enforces alphabetical order on a few nested lists (undocumented;
# surfaces as 400 "must be sorted by <field>"). Sort here so template authors don't have
# to remember the constraint.
_parsed = json.loads(serialized_space_raw)
_parsed["data_sources"]["tables"].sort(key=lambda t: t["identifier"])
for _t in _parsed["data_sources"]["tables"]:
    _t.get("column_configs", []).sort(key=lambda c: c["column_name"])
serialized_space = json.dumps(_parsed)
print(f"Loaded template, substituted UC_SCHEMA -> {uc_schema}")

# COMMAND ----------

# Ensure the parent path exists in the workspace (mirror pixels notebook pattern).
try:
    dbutils.fs.mkdirs(f"file:{GENIE_PARENT_PATH}")
except Exception:
    pass

# COMMAND ----------

# Idempotency: find and delete any existing SAT Genie space with the same title.
list_url = f"https://{DOMAIN}/api/2.0/genie/spaces"
existing_id = None
page_token = None
while True:
    params = {"page_token": page_token} if page_token else {}
    resp = requests.get(list_url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"list_spaces failed ({resp.status_code}): {resp.text}")
        break
    payload = resp.json()
    for space in payload.get("spaces", []):
        if space.get("title") == GENIE_SPACE_TITLE:
            existing_id = space.get("space_id")
            break
    if existing_id:
        break
    page_token = payload.get("next_page_token")
    if not page_token:
        break

if existing_id:
    print(f"Deleting existing SAT Genie space: {existing_id}")
    del_resp = requests.delete(
        f"https://{DOMAIN}/api/2.0/genie/spaces/{existing_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if del_resp.status_code >= 300:
        print(f"Delete failed ({del_resp.status_code}): {del_resp.text}. Continuing to create anyway.")

# COMMAND ----------

body = {
    "title": GENIE_SPACE_TITLE,
    "description": "AI/BI Genie space for natural-language queries over Security Analysis Tool findings.",
    "serialized_space": serialized_space,
    "warehouse_id": json_["sql_warehouse_id"],
    "parent_path": GENIE_PARENT_PATH,
}

create_resp = requests.post(
    list_url,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json=body,
    timeout=60,
)

if create_resp.status_code >= 300:
    raise Exception(f"Error creating Genie space ({create_resp.status_code}): {create_resp.text}")

created = create_resp.json()
print(f"✅ Created SAT Genie space: {created.get('space_id')} — {created.get('title')}")

# COMMAND ----------

dbutils.notebook.exit("OK")
