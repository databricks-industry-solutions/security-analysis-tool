# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 1. list_account_workspaces_to_conf_file
# MAGIC **Functionality:** generates all the workspaces in the account (subscription in case of azure) and writes into a config file

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

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

from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

import json

dbutils.notebook.run(
    f"{basePath()}/notebooks/Utils/accounts_bootstrap",
    300,
    {"json_": json.dumps(json_)},
)

# COMMAND ----------


# this logic does not overwrite the previous config file. It just appends new lines so users can
# easily modify the new lines for new workspaces.
def generateWorkspaceConfigFile(workspace_prefix):
    from pyspark.sql.functions import col, concat, lit

    dfexist = readWorkspaceConfigFile()
    excluded_configured_workspace = ""
    header_value = True
    if dfexist is not None:
        dfexist.createOrReplaceTempView("configured_workspaces")
        excluded_configured_workspace = " AND workspace_id not in (select workspace_id from `configured_workspaces`)"
        # don't append header to an existing file
        header_value = False
    else:
        excluded_configured_workspace = ""  # running first time
    # get current workspaces that are not yet configured for analysis
    spsql = f"""select workspace_id, deployment_name as deployment_url, workspace_name, workspace_status from `global_temp`.`acctworkspaces` 
            where workspace_status = "RUNNING" {excluded_configured_workspace}"""
    df = spark.sql(spsql)
    if not df.rdd.isEmpty():
        if cloud_type == "azure":
            df = df.withColumn(
                "deployment_url",
                concat(col("deployment_url"), lit(".azuredatabricks.net")),
            )  # Azure
        elif cloud_type == "aws":
            df = df.withColumn(
                "deployment_url",
                concat(col("deployment_url"), lit(".cloud.databricks.com")),
            )  # AWS
        else:
            df = df.withColumn(
                "deployment_url",
                concat(col("deployment_url"), lit(".gcp.databricks.com")),
            )  # GCP

        df = df.withColumn(
            "ws_token", concat(lit(workspace_prefix), lit("-"), col("workspace_id"))
        )  # added with workspace prfeix
        #both azure and gcp require sso
        if cloud_type == "azure" or cloud_type == "gcp" :
            df = df.withColumn("sso_enabled", lit(True))
        else:
            df = df.withColumn("sso_enabled", lit(False))
        df = df.withColumn("scim_enabled", lit(False))
        df = df.withColumn("vpc_peering_done", lit(False))
        df = df.withColumn("object_storage_encrypted", lit(True))
        df = df.withColumn("table_access_control_enabled", lit(False))
        df = df.withColumn("connection_test", lit(False))
        df = df.withColumn("analysis_enabled", lit(True))

        loggr.info("Appending following workspaces to configurations ...")
        display(df)
        prefix = getConfigPath()
        df.toPandas().to_csv(
            f"{prefix}/workspace_configs.csv",
            mode="a+",
            index=False,
            header=header_value,
        )  # Databricks Runtime 11.2 or above.
    else:
        loggr.info("No new workspaces found for appending into configurations")


# COMMAND ----------

generateWorkspaceConfigFile(json_["workspace_pat_token_prefix"])
dbutils.notebook.exit("OK")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Look in the Configs folder for generated Files
# MAGIC * ##### Modify workspace_configs.csv. Update the analysis_enabled flag and verify sso_enabled,scim_enabled,vpc_peering_done,object_storage_encrypted,table_access_control_enabled for each workspace.
# MAGIC * ##### New workspaces will be added to end of the file
