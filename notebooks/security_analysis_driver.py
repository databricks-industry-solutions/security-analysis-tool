# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** security_analysis_driver.
# MAGIC **Functionality:** Main notebook to analyze and generate report of configured workspaces
# MAGIC

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

import logging

from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

use_parallel_runs = json_.get("use_parallel_runs", False)

# COMMAND ----------

if cloud_type == "gcp":
    # refresh account level tokens
    gcp_status1 = dbutils.notebook.run(
        f"{basePath()}/notebooks/Setup/gcp/configure_sa_auth_tokens", 3000
    )
    if gcp_status1 != "OK":
        loggr.exception("Error Encountered in GCP Step#1", gcp_status1)
        dbutils.notebook.exit()


# COMMAND ----------

import json

out = dbutils.notebook.run(
    f"{basePath()}/notebooks/Utils/accounts_bootstrap",
    300,
    {"json_": json.dumps(json_)},
)
loggr.info(out)

# COMMAND ----------

readBestPracticesConfigsFile()

# COMMAND ----------

load_sat_dasf_mapping()

# COMMAND ----------

dfexist = getWorkspaceConfig()
dfexist.filter(dfexist.analysis_enabled == True).createOrReplaceGlobalTempView(
    "all_workspaces"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### These are the workspaces we will run the analysis on
# MAGIC ##### Check the workspace_configs.csv and security_analysis.account_workspaces if analysis_enabled and see if analysis_enabled flag is enabled to True if you don't see your workspace

# COMMAND ----------

workspacesdf = spark.sql("select * from `global_temp`.`all_workspaces`")
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


def renewWorkspaceTokens(workspace_id):
    if cloud_type == "gcp":
        # refesh workspace level tokens if PAT tokens are not used as the temp tokens expire in 10 hours
        gcp_status2 = dbutils.notebook.run(
            f"{basePath()}/notebooks/Setup/gcp/configure_tokens_for_worksaces",
            3000,
            {"workspace_id": workspace_id},
        )
        if gcp_status2 != "OK":
            loggr.exception("Error Encountered in GCP Step#2", gcp_status2)
            dbutils.notebook.exit()


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
        {"json_": json.dumps(ws_json)},
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

from concurrent.futures import ThreadPoolExecutor


def combine(ws):
    renewWorkspaceTokens(ws.workspace_id)
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
            renewWorkspaceTokens(ws.workspace_id)
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
