# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Analyzes all configured workspaces and generates a report of hardcoded secrets.

# COMMAND ----------

# MAGIC %run ./diagnosis/pre_run_config_check

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
json_.update(
    {
        "url": hostname,
        "workspace_id": "accounts",
        "cloud_type": cloud_type,
        "clusterid": clusterid,
    }
)

# COMMAND ----------

dfexist = getWorkspaceConfig()
dfexist.filter(dfexist.analysis_enabled == True ).createOrReplaceTempView(
    "all_workspaces"
)

# COMMAND ----------

import json
from dbruntime.databricks_repl_context import get_context
current_workspace = get_context().workspaceId

# COMMAND ----------

# MAGIC %md
# MAGIC ##### The analysis executes across all Databricks workspaces configured for SAT. Eligible workspaces are determined based on entries in **`workspace_configs.csv`** and the **`security_analysis.account_workspaces`** table where the **`analysis_enabled`** flag is set to **`True`**.
# MAGIC ##### If a workspace does not appear in the results, verify that it is correctly listed and that **`analysis_enabled = True`** in both configuration sources.
# MAGIC ##### When running the job/notebook using **Serverless Compute**, the analysis is limited to the **current workspace**. To scan all eligible workspaces, use a Classic Compute cluster.

# COMMAND ----------

serverless_filter=""
if is_serverless:
    serverless_filter = " where workspace_id = '" + current_workspace + "'"

workspacesdf = spark.sql(f"select * from `all_workspaces` {serverless_filter}")
display(workspacesdf)
workspaces = workspacesdf.collect()
if workspaces is None or len(workspaces) == 0:
    loggr.info(
        "Workspaces are not configured for analysis, check the workspace_configs.csv and "
        + json_["analysis_schema_name"]
        + ".account_workspaces if analysis_enabled flag is enabled to True. Use security_analysis_initializer to auto configure workspaces for analysis. "
    )
    # dbutils.notebook.exit("Unsuccessful analysis.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### TruffleHog Secret Scanning
# MAGIC ##### Runs TruffleHog secret scanning across all configured workspaces to detect exposed credentials and secrets in notebooks.
# COMMAND ----------

def processTruffleHogScan(wsrow):
    """
    Process TruffleHog secret scanning for a single workspace.
    Similar to processWorkspace but focused on secrets detection.
    """
    import json

    hostname = "https://" + wsrow.deployment_url
    cloud_type = getCloudType(hostname)
    workspace_id = wsrow.workspace_id
    sso = wsrow.sso_enabled
    scim = wsrow.scim_enabled
    vpc_peering_done = wsrow.vpc_peering_done
    object_storage_encrypted = wsrow.object_storage_encrypted
    table_access_control_enabled = wsrow.table_access_control_enabled

    clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
    ws_json = dict(json_)
    ws_json.update(
        {
            "sso": sso,
            "scim": scim,
            "object_storage_encryption": object_storage_encrypted,
            "vpc_peering": vpc_peering_done,
            "table_access_control_enabled": table_access_control_enabled,
            "url": hostname,
            "workspace_id": workspace_id,
            "cloud_type": cloud_type,
            "clusterid": clusterid,
        }
    )
    
    loggr.info(f"Starting TruffleHog scan for workspace: {workspace_id}")
    loggr.info(ws_json)
    
    # Run TruffleHog secret scanning
    loggr.info(f"Running TruffleHog secret scan for workspace: {workspace_id}")
    scan_result = dbutils.notebook.run(
        f"{basePath()}/notebooks/Includes/scan_secrets/trufflehog_scan",
        3600,  # 1 hour timeout for secrets scanning
        {"json_": json.dumps(ws_json)},
    )
    loggr.info(f"TruffleHog scan completed for workspace: {workspace_id}")
    return scan_result


def runTruffleHogScanForAllWorkspaces():
    """
    Run TruffleHog secret scanning for all configured workspaces.
    """
    loggr.info("Starting TruffleHog secret scanning for all configured workspaces")
    
    scan_workspaces = workspaces
    
    if scan_workspaces is None or len(scan_workspaces) == 0:
        loggr.info("No workspaces configured for TruffleHog scanning")
        return
    
    loggr.info(f"Running TruffleHog scan on {len(scan_workspaces)} workspace(s)")
    
    # Run TruffleHog scanning (sequential for now to avoid overwhelming the system)
    for ws in scan_workspaces:
        try:
            loggr.info(f"Starting TruffleHog scan for workspace: {ws.workspace_id}")
            scan_result = processTruffleHogScan(ws)
            loggr.info(f"TruffleHog scan completed successfully for workspace: {ws.workspace_id}")
            print(f"✅ TruffleHog scan completed for workspace: {ws.workspace_id}")
        except Exception as e:
            loggr.error(f"TruffleHog scan failed for workspace {ws.workspace_id}: {str(e)}")
            print(f"❌ TruffleHog scan failed for workspace: {ws.workspace_id}")
            continue


runTruffleHogScanForAllWorkspaces()