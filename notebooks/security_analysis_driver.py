# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** security_analysis_driver.
# MAGIC **Functionality:** Main notebook to analyze and generate report of configured workspaces
# MAGIC

# COMMAND ----------

# MAGIC %run ./diagnosis/pre_run_config_check

# COMMAND ----------

# MAGIC %run ./Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ./Utils/initialize

# COMMAND ----------

# MAGIC %run ./Utils/common

# COMMAND ----------

# replace values for accounts exec
hostname = (
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .apiUrl()
    .getOrElse(None)
)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")
# dont know workspace token yet.
json_.update(
    {
        "url": hostname,
        "workspace_id": "accounts",
        "cloud_type": cloud_type,
        "clusterid": clusterid,
    }
)

# COMMAND ----------

use_parallel_runs = json_.get("use_parallel_runs", False)

# COMMAND ----------

import json

out = dbutils.notebook.run(
    f"{basePath()}/notebooks/Utils/accounts_bootstrap",
    300,
    {"json_": json.dumps(json_), "origin": "driver"},
)
loggr.info(out)

# COMMAND ----------

readBestPracticesConfigsFile()

# COMMAND ----------

load_sat_dasf_mapping()

# COMMAND ----------

dfexist = getWorkspaceConfig()
dfexist.filter(dfexist.analysis_enabled == True ).createOrReplaceTempView(
    "all_workspaces"
)

# COMMAND ----------

import json
from dbruntime.databricks_repl_context import get_context
#Get current workspace id
current_workspace = get_context().workspaceId

# COMMAND ----------

# MAGIC %md
# MAGIC ##### These are the workspaces we will run the analysis on
# MAGIC ##### Check the workspace_configs.csv and security_analysis.account_workspaces if analysis_enabled and see if analysis_enabled flag is enabled to True if you don't see your workspace
# MAGIC ##### If the analysis is serverless compute only run the analysis for the current workspace

# COMMAND ----------

#if the analysis is happening on serverless compute let us ignore all workspaces except the current workspace
serverless_filter=""
if is_serverless:
    serverless_filter = " where workspace_id = '" + current_workspace + "'"

workspacesdf = spark.sql(f"select * from `all_workspaces` {serverless_filter}")
display(workspacesdf)
workspaces = workspacesdf.collect()
if workspaces is None or len(workspaces) == 0:
    loggr.info(
        "Workspaes are not configured for analyis, check the workspace_configs.csv and "
        + json_["analysis_schema_name"]
        + ".account_workspaces if analysis_enabled flag is enabled to True. Use security_analysis_initializer to auto configure workspaces for analysis. "
    )
    # dbutils.notebook.exit("Unsuccessful analysis.")

# COMMAND ----------

insertNewBatchRun()  # common batch number for each run


def processWorkspace(wsrow):
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
    loggr.info(ws_json)
    retstr = dbutils.notebook.run(
        f"{basePath()}/notebooks/Utils/workspace_bootstrap",
        3000,
        {"json_": json.dumps(ws_json),"origin": "driver"},
    )
    if "Completed SAT" not in retstr:
        raise Exception("Workspace Bootstrap failed. Skipping workspace analysis")
    else:
        dbutils.notebook.run(
            f"{basePath()}/notebooks/Includes/workspace_analysis",
            3000,
            {"json_": json.dumps(ws_json)},
        )
        dbutils.notebook.run(
            f"{basePath()}/notebooks/Includes/workspace_stats",
            1000,
            {"json_": json.dumps(ws_json)},
        )
        dbutils.notebook.run(
            f"{basePath()}/notebooks/Includes/workspace_settings",
            3000,
            {"json_": json.dumps(ws_json)},
        )


# COMMAND ----------

import time
from concurrent.futures import ThreadPoolExecutor


def combine(ws):
    processWorkspace(ws)
    notifyworkspaceCompleted(ws.workspace_id, True)


if use_parallel_runs == True:
    loggr.info("Running in parallel")
    with ThreadPoolExecutor(max_workers=4) as executor:
        try:
            result = executor.map(combine, workspaces)
            for r in result:
                print(r)
        except Exception as e:
            loggr.info(e)
else:
    loggr.info("Running in sequence")
    for ws in workspaces:
        try:
            processWorkspace(ws)
            notifyworkspaceCompleted(ws.workspace_id, True)
            loggr.info(f"Completed analyzing {ws.workspace_id}!")
        except Exception as e:
            loggr.info(e)
            notifyworkspaceCompleted(ws.workspace_id, False)

# COMMAND ----------

display(
    spark.sql(
        f'select * from {json_["analysis_schema_name"]}.security_checks order by run_id desc, workspaceid asc, check_time asc'
    )
)

# COMMAND ----------


display(
    spark.sql(
        f'select * from {json_["analysis_schema_name"]}.workspace_run_complete order by run_id desc'
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### TruffleHog Secret Scanning
# MAGIC ##### Run TruffleHog secret scanning on configured workspaces to detect exposed secrets in notebooks

# COMMAND ----------

def processTruffleHogScan(wsrow):
    """
    Process TruffleHog secret scanning for a single workspace.
    Similar to processWorkspace but focused on secret detection.
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
        3600,  # 1 hour timeout for secret scanning
        {"json_": json.dumps(ws_json)},
    )
    loggr.info(f"TruffleHog scan completed for workspace: {workspace_id}")
    return scan_result


def runTruffleHogScanForAllWorkspaces():
    """
    Run TruffleHog secret scanning for all configured workspaces.
    """
    loggr.info("Starting TruffleHog secret scanning for all configured workspaces")
    
    # Get the same workspaces that were configured for analysis
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



# COMMAND ----------

if json_.get("scan_for_secrets", False):
    runTruffleHogScanForAllWorkspaces()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Drop the staging database after SAT run that holds temporary tables

# COMMAND ----------

spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")
