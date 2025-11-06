# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Analyzes all configured workspaces and generates a report of key metrics and security findings.
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
        "Workspaes are not configured for analyis, check the workspace_configs.csv and "
        + json_["analysis_schema_name"]
        + ".account_workspaces if analysis_enabled flag is enabled to True. Use security_analysis_initializer to auto configure workspaces for analysis. "
    )
    # dbutils.notebook.exit("Unsuccessful analysis.")

# COMMAND ----------

insertNewBatchRun()


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
# MAGIC #### After the SAT run completes, drop the **staging database** used to store temporary tables. This ensures no residual data persists between runs and maintains a clean environment for subsequent analyses.

# COMMAND ----------

spark.sql(f"DROP DATABASE IF EXISTS {json_['intermediate_schema']} CASCADE")
