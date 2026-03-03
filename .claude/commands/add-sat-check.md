A new security check row has been added to `configs/security_best_practices.csv`.
Implement it end-to-end by following these steps in order.

---

## Step 1 — Read the new check definition

Find the newly added row (the one with the highest `id` value) in
`configs/security_best_practices.csv`. Extract:
- `id` (integer), `check_id` (e.g. INFO-42), `category`, `check` (display name)
- `evaluation_value`, `severity`, `aws`, `azure`, `gcp`, `enable`
- `logic` field — this describes the data source (workspace-conf key, Settings V2 type, or table name)
- `api` field — the API endpoint being called

---

## Step 2 — Determine the implementation file and data source type

Choose based on the `logic`/`api` fields:

| Data source | Implementation file |
|---|---|
| `workspacesettings` table (workspace-conf key via `GET /preview/workspace-conf?keys=...`) | `notebooks/Includes/workspace_settings.py` |
| Dedicated Settings V2 table (`automatic_cluster_update`, `compliance_security_profile`, etc.) | `notebooks/Includes/workspace_analysis.py` |
| Data table (clusters, jobs, tokens, secretscopes, etc.) | `notebooks/Includes/workspace_analysis.py` |

Note: `workspace_settings.py` uses variable `id`; `workspace_analysis.py` uses `check_id`.

---

## Step 3 — Verify data collection; add to SDK if missing

### For workspace-conf keys (workspace_settings.py path):
Check if the key exists in `ws_keymap` in
`src/securityanalysistoolproject/clientpkgs/ws_settings_client.py`.

If the key is missing, add it to `ws_keymap`:
```python
{"name": "<key_name>", "defn": "<description of what this setting controls>"},
```
Insert near related keys. Then rebuild the wheel (see Step 6).

### For Settings V2 types (workspace_analysis.py path):
Check if a getter method exists in `ws_settings_client.py` (workspace-level) or
`accounts_settings.py` (account-level), AND a corresponding `bootstrap(...)` call exists in
`workspace_bootstrap.py` or `accounts_bootstrap.py`.

If missing, add both the method and the bootstrap call. Then rebuild the wheel.

### For data tables (workspace_analysis.py path):
Check if the table is already bootstrapped in `workspace_bootstrap.py` or
`accounts_bootstrap.py`. If already present, no SDK change is needed.

---

## Step 4 — Implement the check block

Insert a new `# COMMAND ----------` block **before** the final timing/exit block at the end of
the target file.

### Pattern A — workspace_settings.py, boolean check where TRUE = good (PASS)
(Mirror: `enforceUserIsolation` id=40, `enableEnforceImdsV2` id=43, `enableProjectsAllowList` id=113)

```python
# COMMAND ----------

id = '<id>' # <check name>
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def <camelCaseFunctionName>(df):
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value if row.value else 'false'
        defn = {'defn' : row.defn.replace("'", '')}
    if value == 'true':
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f\'\'\'
        SELECT * FROM {tbl_name}
        WHERE name="<workspace_conf_key>"
    \'\'\'
    sqlctrl(workspace_id, sql, <camelCaseFunctionName>)
```

### Pattern B — workspace_settings.py, boolean check where TRUE = bad (VIOLATION)
(Mirror: `enableDeprecatedGlobalInitScripts` id=63, `enableDeprecatedClusterNamedInitScripts` id=65)

Same as Pattern A but swap the return scores:
```python
    if value == 'true':
        return (id, 1, defn)   # true = violation
    else:
        return (id, 0, defn)   # false = pass
```

### Pattern C — workspace_analysis.py, Settings V2 table check
(Mirror: `enhanced_security_monitoring` id=109, `automatic_cluster_update` id=107)

```python
# COMMAND ----------

check_id = '<id>' # <check name>
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def <snake_case_function_name>(df):
    if df is not None and not isEmpty(df):
        return (check_id, 0, {'<setting_name>': 'True'})
    else:
        return (check_id, 1, {'<setting_name>': 'False'})

if enabled:
    tbl_name = '<settings_table_name>' + '_' + workspace_id
    sql = f\'\'\'
        SELECT * FROM {tbl_name}
        WHERE <condition_column> = true
    \'\'\'
    sqlctrl(workspace_id, sql, <snake_case_function_name>)
```

### Pattern D — workspace_analysis.py, data table check (count-based violation)
(Mirror: NS-1 clusters SSH keys, IA-4 tokens with no lifetime)

```python
# COMMAND ----------

check_id = '<id>' # <check name>
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def <snake_case_function_name>(df):
    if df is not None and not isEmpty(df):
        violations = {}
        for row in df.collect():
            violations[row['<id_column>']] = row['<name_column>']
        return (check_id, len(violations), violations)
    else:
        return (check_id, 0, {})

if enabled:
    tbl_name = '<table_name>' + '_' + workspace_id
    sql = f\'\'\'
        SELECT <id_column>, <name_column>
        FROM {tbl_name}
        WHERE <violation_condition>
    \'\'\'
    sqlctrl(workspace_id, sql, <snake_case_function_name>)
```

---

## Step 5 — Add DASF mapping

Append to `configs/sat_dasf_mapping.csv` if the check maps to a DASF control:
```
<id>,DASF-XX:<control name>,
```
If no clear DASF mapping applies, skip this step.

---

## Step 6 — Rebuild wheel (only if SDK was changed in Step 3)

```bash
cd src/securityanalysistoolproject
python setup.py sdist bdist_wheel
cp dist/dbl_sat_sdk-*.whl ../../lib/
cd ../..
```

Note: The wheel version in `setup.py` should already reflect the current version. Only bump
the patch version (e.g. 0.1.41 → 0.1.42) if explicitly asked.

---

## Step 7 — Run validations (always)

```bash
# CSV uniqueness — must pass before committing
python3 - <<'EOF'
import csv, sys
ids, check_ids = {}, {}
errors = []
with open("configs/security_best_practices.csv") as f:
    for i, row in enumerate(csv.DictReader(f), start=2):
        if row["id"] in ids:
            errors.append(f"  Duplicate id={row['id']} on rows {ids[row['id']]} and {i}")
        else:
            ids[row["id"]] = i
        if row["check_id"] in check_ids:
            errors.append(f"  Duplicate check_id={row['check_id']} on rows {check_ids[row['check_id']]} and {i}")
        else:
            check_ids[row["check_id"]] = i
if errors:
    print("VIOLATIONS — fix before committing:"); print("\n".join(errors)); sys.exit(1)
else:
    print(f"OK — {len(ids)} rows, all unique")
EOF

# Codespell — report pre-existing typos separately from new ones; do not commit if new ones found
codespell configs/security_best_practices.csv configs/sat_dasf_mapping.csv \
          notebooks/Includes/workspace_settings.py notebooks/Includes/workspace_analysis.py \
          src/securityanalysistoolproject/clientpkgs/ws_settings_client.py 2>/dev/null || true
```

---

## Step 8 — Summarise

Report what was done in this format:

**Files changed:**
- List each file and the specific change (e.g. "added id=113 row", "added enableProjectsAllowList to ws_keymap")

**Wheel rebuilt:** yes/no

**Validations:** CSV OK (N rows, all unique) | codespell: N findings (pre-existing / new)

Ask the user if they want to commit before running `git commit`.
