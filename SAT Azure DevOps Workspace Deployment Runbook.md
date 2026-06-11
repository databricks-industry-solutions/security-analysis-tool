# SAT Azure DevOps POC Runbook for a Workspace-Only Service Principal

## Scope

This runbook is for a **single Azure Databricks workspace** where SAT is deployed and run by a **service principal** that has **workspace admin** permission, but **does not** have:

- Databricks **Accounts Admin**  
- Azure subscription **Reader**  
- **metastore admin**

This means the POC is intentionally **workspace-scoped**:

- deploy SAT into one workspace  
- store SAT outputs in **your own Unity Catalog catalog/schema**  
- run **workspace-level** checks  
- skip or ignore **account-level** and **metastore-wide** checks

SAT supports choosing your own catalog instead of `hive_metastore`, uses a **one-time initializer** followed by recurring **driver** runs, and stores results in Delta tables for dashboarding.

## What is in scope

Use this POC to validate:

- Azure DevOps deployment with **Databricks Asset Bundles**  
- jobs running as the **service principal**  
- SAT writing to **your UC catalog/schema**  
- useful **workspace-level** findings

Examples of workspace-oriented checks that should still be useful include:

- workspace configuration checks  
- jobs checks  
- cluster/runtime checks  
- repo allowlist checks  
- workspace IP access list enforcement checks

## What is out of scope

The published Azure SAT guidance for full deployment expects broader permissions including **subscription Reader**, **Accounts Admin**, **workspace Admin**, and **metastore admin**.

For this POC, treat these as out of scope:

- account settings checks such as **GOV-37**  
- account network policy checks such as **NS-12**  
- account console IP access list checks such as **NS-13**  
- account-level SP secret checks such as **IA-9**; for Azure, IA-9 is disabled anyway

## Required permissions

### On the workspace

Your service principal should have:

- **Workspace Admin**  
- permission to create and update **Jobs**  
- permission to read and run notebooks from the SAT deployment path  
- permission to use the target **SQL warehouse**

### On your Unity Catalog objects

Because SAT writes into **your own catalog/schema**, the service principal should have at minimum:

- `USE CATALOG` on the target catalog  
- `USE SCHEMA` on the target schema  
- permission to create tables in that schema  
- permission to read and write SAT tables in that schema

If the schema does not exist yet, either pre-create it or grant create rights at the catalog/schema level.

### Not required for this POC

- Databricks **Accounts Admin**  
- Azure subscription **Reader**  
- **metastore admin**

## Design decision: no Databricks secret scope

This runbook removes the **secret scope** dependency on purpose.

The current SAT setup and related notebook patterns use secret-scope based configuration and direct `dbutils.secrets.get(...)` calls. For this POC, replace that model with:

**Bundle variables \-\> job base parameters \-\> notebook widgets**

This is the target state:

- **no Databricks secret scope**  
- **no SP secret read inside the notebook**  
- runtime config passed as **job parameters**  
- notebooks use the **run-as service principal** identity

## Variable split

### Azure DevOps pipeline variables

Keep these in the Azure DevOps variable group because they are deployment/auth concerns:

- `DATABRICKS_HOST`  
- `DATABRICKS_TOKEN` or SP auth values  
- `SAT_REPO_REF`

### Bundle variables

Model these as bundle variables because they are deployed SAT configuration:

- `analysis_catalog`  
- `analysis_schema`  
- `enable_account_checks`  
- optionally schedule settings

The SQL warehouse is managed as a bundle resource (no variable needed).

### Notebook widgets / base parameters

Pass these into the notebooks:

- `warehouse_id` (auto-resolved from the bundle-managed warehouse resource)  
- `analysis_catalog`  
- `analysis_schema`  
- `enable_account_checks`

## Inputs to collect

Before deployment, collect:

- `DATABRICKS_HOST`  
- service principal auth details for Azure DevOps  
- `analysis_catalog`  
- `analysis_schema`

The SQL warehouse and notebook paths are managed by the bundle automatically.

## Step 1: Prepare catalog and schema

Pick a dedicated location for SAT results, for example:

```
catalog: security_tools
schema: sat_poc
```

Grant the service principal access:

```sql
GRANT USE CATALOG ON CATALOG `security_tools` TO `<service-principal>`;
GRANT USE SCHEMA ON SCHEMA `security_tools`.`sat_poc` TO `<service-principal>`;
GRANT CREATE TABLE ON SCHEMA `security_tools`.`sat_poc` TO `<service-principal>`;
```

If SAT needs to overwrite or update existing tables, grant the additional write privileges required in your environment.

## Step 2: Mirror SAT into Azure DevOps

Push your SAT mirror into Azure DevOps.

Recommended branch model:

- `main` for stable internal copy  
- `release/<version>` for controlled validation

Deploy from a **tag** or release branch.

## Step 3: Repository structure

Suggested structure:

```
/deployment
  /bundle
    databricks.yml
    resources/
      sat_warehouse.sql_warehouse.yml
      sat_initializer.job.yml
      sat_driver.job.yml
  /pipelines
    azure-pipelines.yml
```

## Step 4: Azure DevOps variable group

Example variable group:

```
sat-ws-poc
```

Keep only deployment/auth values there:

- `DATABRICKS_HOST`  
- `DATABRICKS_TOKEN`  
- `SAT_REPO_REF`

## Step 5: Bundle definition

`deployment/bundle/databricks.yml`

```yaml
bundle:
  name: sat-poc

variables:
  analysis_catalog:
    default: ""
  analysis_schema:
    default: ""
  enable_account_checks:
    default: "false"
  sat_repo_root:
    default: "/Workspace/Shared/sat"

include:
  - resources/*.yml

targets:
  poc:
    mode: development
    workspace:
      host: ${env.DATABRICKS_HOST}
```

`deployment/bundle/resources/sat_warehouse.sql_warehouse.yml`

```yaml
resources:
  sql_warehouses:
    sat_warehouse:
      name: SAT POC Warehouse
      cluster_size: "2X-Small"
      auto_stop_mins: 1
      warehouse_type: PRO
      enable_serverless_compute: true
```

`deployment/bundle/resources/sat_initializer.job.yml`

```yaml
resources:
  jobs:
    sat_initializer:
      name: SAT Initializer POC
      tasks:
        - task_key: initialize
          notebook_task:
            notebook_path: ${var.sat_repo_root}/notebooks/security_analysis_initializer
            base_parameters:
              warehouse_id: ${resources.sql_warehouses.sat_warehouse.id}
              analysis_catalog: ${var.analysis_catalog}
              analysis_schema: ${var.analysis_schema}
              enable_account_checks: ${var.enable_account_checks}
      queue:
        enabled: true
```

`deployment/bundle/resources/sat_driver.job.yml`

```yaml
resources:
  jobs:
    sat_driver:
      name: SAT Driver POC
      tasks:
        - task_key: run_driver
          notebook_task:
            notebook_path: ${var.sat_repo_root}/notebooks/security_analysis_driver
            base_parameters:
              warehouse_id: ${resources.sql_warehouses.sat_warehouse.id}
              analysis_catalog: ${var.analysis_catalog}
              analysis_schema: ${var.analysis_schema}
              enable_account_checks: ${var.enable_account_checks}
      queue:
        enabled: true
```

Jobs run on **serverless compute** (no cluster specification). The SQL warehouse is created by the bundle with serverless enabled and 1-minute auto-stop.

For this POC, keep `enable_account_checks` set to `false`.

## Step 6: Patch notebook configuration loading

The current SAT setup uses secret-scope based config in notebooks and related setup guidance. Three notebooks require patching:

1. **`notebooks/Utils/initialize`** — primary config loading (replace secrets with widgets)
2. **`notebooks/Utils/workspace_bootstrap`** — auth setup (add native SP token fallback)
3. **`notebooks/diagnosis/pre_run_config_check`** — secret validation (add early exit when account checks disabled)

### 6a. Patch `notebooks/Utils/initialize`

Recommended minimal pattern:

```py
required_keys = [
    "warehouse_id",
    "analysis_catalog",
    "analysis_schema",
    "enable_account_checks"
]

for k in required_keys:
    dbutils.widgets.text(k, "")

def get_cfg(key, default=None, required=False):
    v = dbutils.widgets.get(key)
    if v is None or str(v).strip() == "":
        v = default
    if required and (v is None or str(v).strip() == ""):
        raise ValueError(f"Missing required config: {key}")
    return v

WAREHOUSE_ID = get_cfg("warehouse_id", required=True)
ANALYSIS_CATALOG = get_cfg("analysis_catalog", required=True)
ANALYSIS_SCHEMA = get_cfg("analysis_schema", required=True)
ENABLE_ACCOUNT_CHECKS = get_cfg("enable_account_checks", default="false").lower() == "true"
```

Then:

- replace direct `dbutils.secrets.get(...)` calls for **non-sensitive config**  
- use these resolved variables downstream  
- guard account-level logic behind `ENABLE_ACCOUNT_CHECKS`

Recommended behavior:

- if `ENABLE_ACCOUNT_CHECKS == False`, skip account-level API calls cleanly  
- log that those checks are intentionally out of scope for this POC

### 6b. Patch `notebooks/Utils/workspace_bootstrap`

The workspace bootstrap reads `client_secret` from the secret scope for OAuth. For the POC, add a try/except that falls back to the run-as SP native token:

```py
if cloud_type == 'azure':
    try:
        client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
        json_.update({'token': token, 'client_secret': client_secret})
    except Exception:
        # No secret scope — use run-as SP identity token
        token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().getOrElse(None)
        json_.update({'token': token, 'client_secret': ''})
```

Also remove or guard the `use_mastercreds is False` PAT-from-secrets fallback — it cannot work without a secret scope and is dead code for this POC (`use_mastercreds` is always `True`).

### 6c. Patch `notebooks/diagnosis/pre_run_config_check`

This notebook validates that the secret scope and required keys exist. When account checks are disabled, add an early exit before the scope check:

```py
if not ENABLE_ACCOUNT_CHECKS:
    print("[SAT POC] Secret scope validation SKIPPED — using widget-based config.")
    dbutils.notebook.exit("OK")
```

### 6d. Skip Setup notebooks in the initializer

The initializer calls Setup notebooks (`3. test_connections`, `5. import_dashboard_template_lakeview`) that read `client_secret` from the secret scope for OAuth. Rather than patching each one, guard the entire Setup block in `notebooks/security_analysis_initializer` behind `ENABLE_ACCOUNT_CHECKS`:

```py
if ENABLE_ACCOUNT_CHECKS:
    notebooks = [
        ("1. list_account_workspaces_to_conf_file", 3000),
        ("3. test_connections", 12000),
        ("4. enable_workspaces_for_sat", 3000),
        ("5. import_dashboard_template_lakeview", 3000),
    ]
    for notebook, timeout in notebooks:
        status = run_notebook(f"{basePath()}/notebooks/Setup/{notebook}", timeout)
else:
    loggr.info("[SAT POC] Setup notebooks SKIPPED — account checks disabled.")
```

The POC initializer flow becomes: `pre_run_config_check` (skip validation) → `install_sat_sdk` → `initialize` (widget config) → `common` (create schema/tables) → done.

## Step 7: Azure DevOps pipeline

`deployment/pipelines/azure-pipelines.yml`

```
trigger:
  branches:
    include:
      - main
      - release/*

pool:
  vmImage: ubuntu-latest

variables:
- group: sat-ws-poc

stages:
- stage: Deploy
  jobs:
  - job: DeploySAT
    steps:
    - checkout: self

    - script: pip install databricks-cli
      displayName: Install Databricks CLI

    - script: |
        mkdir -p ~/.databricks
        cat > ~/.databrickscfg <<EOF
        [DEFAULT]
        host = $(DATABRICKS_HOST)
        token = $(DATABRICKS_TOKEN)
        EOF
      displayName: Configure Databricks auth

    - script: |
        databricks workspace import-dir . /Workspace/Shared/sat --overwrite
      displayName: Upload SAT repo

    - script: |
        databricks bundle validate --target poc
      workingDirectory: deployment/bundle
      env:
        DATABRICKS_HOST: $(DATABRICKS_HOST)
        BUNDLE_VAR_warehouse_id: $(warehouse_id)
        BUNDLE_VAR_analysis_catalog: $(analysis_catalog)
        BUNDLE_VAR_analysis_schema: $(analysis_schema)
        BUNDLE_VAR_enable_account_checks: "false"
        BUNDLE_VAR_cluster_id: $(cluster_id)

    - script: |
        databricks bundle deploy --target poc
      workingDirectory: deployment/bundle
      env:
        DATABRICKS_HOST: $(DATABRICKS_HOST)
        BUNDLE_VAR_warehouse_id: $(warehouse_id)
        BUNDLE_VAR_analysis_catalog: $(analysis_catalog)
        BUNDLE_VAR_analysis_schema: $(analysis_schema)
        BUNDLE_VAR_enable_account_checks: "false"
        BUNDLE_VAR_cluster_id: $(cluster_id)

- stage: Test
  jobs:
  - job: RunPOC
    steps:
    - checkout: none

    - script: pip install databricks-cli
      displayName: Install Databricks CLI

    - script: |
        mkdir -p ~/.databricks
        cat > ~/.databrickscfg <<EOF
        [DEFAULT]
        host = $(DATABRICKS_HOST)
        token = $(DATABRICKS_TOKEN)
        EOF
      displayName: Configure Databricks auth

    - script: |
        databricks jobs run-now --job-id $(SAT_INITIALIZER_JOB_ID)
      displayName: Run initializer

    - script: |
        databricks jobs run-now --job-id $(SAT_DRIVER_JOB_ID)
      displayName: Run driver
```

## Step 8: Execution checklist

1. Create or prepare the UC catalog/schema.  
2. Grant the service principal access to the catalog/schema.  
3. Patch notebooks per Step 6 (initialize, workspace_bootstrap, pre_run_config_check, initializer).  
4. Confirm the service principal can authenticate from Azure DevOps.  
5. Confirm it can create jobs and SQL warehouses.  
6. Deploy SAT code to `/Workspace/Shared/sat`.  
7. Deploy the bundle (creates the SQL warehouse and jobs automatically).  
8. Run the **initializer** once.  
9. Review failures.  
10. If a failure is clearly account-level, keep it out of scope for this POC.  
11. Run the **driver** notebook.  
12. Verify SAT tables are created in your catalog/schema.  
13. Open the dashboard and confirm results appear.

Note: The SQL warehouse (2X-Small, serverless, 1-min auto-stop) is created by the bundle — no manual creation needed.

## Expected outcome

This POC is successful when:

- the service principal deploys SAT from Azure DevOps  
- initializer completes  
- driver completes  
- SAT tables are created in your catalog/schema  
- dashboard loads and shows findings  
- account-level gaps are documented as intentionally out of scope

## Notes

- The full Azure SAT guidance is broader than this POC and expects higher-scope permissions.  
- For your ownership boundary, the correct design is **workspace-level SAT plus your own UC catalog/schema**.  
- Removing the secret-scope dependency is reasonable here because the notebooks are being patched to use **bundle-driven runtime parameters** instead of notebook-side secret lookup.

