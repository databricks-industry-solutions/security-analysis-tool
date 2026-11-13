# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** common.
# MAGIC **Functionality:** routines used across the project

# COMMAND ----------

def bootstrap(viewname, func, **kwargs):
    """bootstrap with function and store resulting dataframe as a global temp view
    if the function doesn't return a value, creates an empty dataframe and corresponding view
    :param str viewname - name of the view
    :param func - Name of the function to call
    :**kwargs - named args to pass to the function

    """
    import json
    import pandas as pd

    from pyspark.sql.types import StructType
    from pyspark.sql.functions import col, schema_of_json, from_json, concat_ws, collect_list

    apiDF = None
    try:
        lst = func(**kwargs)
        if lst:
            lstjson = [json.dumps(ifld) for ifld in lst]
            apiDF = spark.createDataFrame([(x,) for x in lstjson], ["json_string"])
            # Parse the JSON strings using the schema string
            apiDF = apiDF.select(from_json(col("json_string"), process_json_schema(apiDF)).alias("data")).select("data.*")
            #display(apiDF)
        else:
            apiDF = spark.createDataFrame([], StructType([]))
            loggr.info("No Results!")
        if len(apiDF.take(1)) > 0:
            apiDF.write.option("delta.columnMapping.mode", "name").mode("overwrite").saveAsTable(viewname)
            loggr.info(f"Table created: `{viewname}`")
    except Exception:
        loggr.exception("Exception encountered")

# COMMAND ----------


def getCloudType(url):
    if ".cloud." in url:
        return "aws"
    elif ".azuredatabricks." in url:
        return "azure"
    elif ".gcp." in url:
        return "gcp"
    return ""


# COMMAND ----------


def readWorkspaceConfigFile():
    import pandas as pd

    prefix = getConfigPath()

    dfa = pd.DataFrame()
    schema = "workspace_id string, deployment_url string, workspace_name string,workspace_status string, connection_test boolean, analysis_enabled boolean"
    dfexist = spark.createDataFrame([], schema)
    try:
        dict = {
            "workspace_id": "str",
            "connection_test": "bool",
            "analysis_enabled": "bool",
        }
        dfa = pd.read_csv(f"{prefix}/workspace_configs.csv", header=0, dtype=dict)
        if len(dfa) > 0:
            dfa = dfa.where(dfa.notna(), None)
            dfexist = spark.createDataFrame(dfa.values.tolist(), schema)
    except FileNotFoundError:
        print("Missing workspace Config file")
        return
    except pd.errors.EmptyDataError as e:
        pass
    return dfexist


# COMMAND ----------


def getWorkspaceConfig():
    df = spark.sql(
        f"""select * from {json_["analysis_schema_name"]}.account_workspaces"""
    )
    return df


# COMMAND ----------


def getConfigPath():
    return f"{basePath()}/configs"


# COMMAND ----------

def basePath():
    path = (
        dbutils.notebook.entry_point.getDbutils()
        .notebook()
        .getContext()
        .notebookPath()
        .get()
    )
    path = path[: path.find("/notebooks")]
    return f"/Workspace{path}"


# COMMAND ----------


def create_schema():
    schema = json_["analysis_schema_name"]
    df = spark.sql(f'CREATE DATABASE IF NOT EXISTS {schema}')
    df = spark.sql(f'CREATE DATABASE IF NOT EXISTS {json_["intermediate_schema"]}')
    spark.sql(
        f"COMMENT ON SCHEMA {schema} IS "
        f"'Databricks Security Analysis Tool (SAT) results. Contains security check findings, "
        f"workspace configurations, secret scan results, and Permission Analysis graph data (BrickHound), "
        f"all evaluated against Databricks best practices.'"
    )
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.run_number_table (
                        runID BIGINT GENERATED ALWAYS AS IDENTITY,
                        check_time TIMESTAMP
                        )
                        USING DELTA"""
    )
    _set_table_comment(
        schema, "run_number_table",
        "Sequence table that issues a unique run_id for each SAT analysis execution. "
        "Join all other tables to this on run_id to correlate findings from the same run. "
        "Typically has one row per SAT job execution."
    )
    _set_column_comments(schema, "run_number_table", {
        "runID":      "Auto-incrementing unique identifier for each SAT analysis run",
        "check_time": "Timestamp when this SAT run was initiated",
    })


# COMMAND ----------


def insertNewBatchRun():
    import time

    ts = time.time()
    df = spark.sql(
        f'insert into {json_["analysis_schema_name"]}.run_number_table (check_time) values ({ts})'
    )


# COMMAND ----------


def notifyworkspaceCompleted(workspaceID, completed):
    import time

    ts = time.time()
    runID = spark.sql(
        f'select max(runID) from {json_["analysis_schema_name"]}.run_number_table'
    ).collect()[0][0]
    spark.sql(
        f"""INSERT INTO {json_["analysis_schema_name"]}.workspace_run_complete (`workspace_id`,`run_id`, `completed`, `check_time`)  VALUES ({workspaceID}, {runID}, {completed}, cast({ts} as timestamp))"""
    )


# COMMAND ----------


def create_account_info_table():
    schema = json_["analysis_schema_name"]
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.account_info (
        workspaceid string,
        name string,
        value map<string, string>,
        category string,
        run_id bigint,
        check_time timestamp,
        chk_date date GENERATED ALWAYS AS (CAST(check_time AS DATE)),
        chk_hhmm integer GENERATED ALWAYS AS (CAST(CAST(hour(check_time) as STRING) || CAST(minute(check_time) as STRING) as INTEGER))
        )
        USING DELTA
        PARTITIONED BY (chk_date)"""
    )
    _set_table_comment(
        schema, "account_info",
        "Workspace-level statistics and properties collected during each SAT run. Each row is one named metric for a workspace. "
        "The name column uses coded keys: AS-1=account ID, AS-2=cloud region, AS-3=deployment name, AS-4=pricing tier, "
        "AS-5=workspace ID, AS-6=workspace status, WST-1=total job count, WST-2=orphaned external job count."
    )
    _set_column_comments(schema, "account_info", {
        "workspaceid": "Databricks workspace ID this metric belongs to",
        "name":        "Coded metric key (e.g. AS-1=account ID, AS-2=cloud region, AS-4=pricing tier, WST-1=job count)",
        "value":       'JSON-encoded metric value, always in format: {"value": "<metric_value>"}',
        "category":    "Metric category: Account Stats for account-level properties, Workspace Stats for workspace-level counts",
        "run_id":      "SAT run ID when this metric was collected — foreign key to run_number_table.runID",
        "check_time":  "Timestamp when this metric was collected",
        "chk_date":    "Date partition derived from check_time",
        "chk_hhmm":    "Hour and minute as integer (HHMM) derived from check_time",
    })


# COMMAND ----------


def create_account_workspaces_table():
    schema = json_["analysis_schema_name"]
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.account_workspaces (
            workspace_id string,
            deployment_url string,
            workspace_name string,
            workspace_status string,
            analysis_enabled boolean
            )
            USING DELTA"""
    )
    _set_table_comment(
        schema, "account_workspaces",
        "Registry of Databricks workspaces configured for SAT analysis, with high-level security posture flags set during "
        "workspace enablement. Used by Genie to answer questions like: which workspaces have SSO enabled?"
    )
    _set_column_comments(schema, "account_workspaces", {
        "workspace_id":                 "Databricks workspace ID",
        "deployment_url":               "Workspace hostname (e.g. myworkspace.cloud.databricks.com)",
        "workspace_name":               "Human-readable workspace name",
        "workspace_status":             "Current Databricks workspace status (e.g. RUNNING)",
        "analysis_enabled":             "True if SAT is configured to analyze this workspace",
    })


# COMMAND ----------


def create_notebooks_secret_scan_results_table():
    schema = json_["analysis_schema_name"]
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.notebooks_secret_scan_results (
        workspace_id STRING,
        notebook_id STRING,
        notebook_path STRING,
        notebook_name STRING,
        detector_name STRING,
        secret_sha256 STRING,
        source_file STRING,
        verified BOOLEAN,
        secrets_found INTEGER,
        run_id BIGINT,
        scan_time TIMESTAMP,
        scan_date DATE GENERATED ALWAYS AS (CAST(scan_time AS DATE)),
        scan_hhmm INTEGER GENERATED ALWAYS AS (CAST(CAST(hour(scan_time) as STRING) || CAST(minute(scan_time) as STRING) as INTEGER))
    )
    USING DELTA
    PARTITIONED BY (scan_date)
    """
    )
    _set_table_comment(
        schema, "notebooks_secret_scan_results",
        "TruffleHog secret scan results for Databricks notebooks. Identifies potential hardcoded secrets, API keys, "
        "and credentials in notebook source code. When secrets_found=0 and other fields are NULL, it means the "
        "workspace was scanned and no secrets were detected."
    )
    _set_column_comments(schema, "notebooks_secret_scan_results", {
        "workspace_id":  "Databricks workspace ID where the notebook resides",
        "notebook_id":   "Databricks notebook ID that was scanned",
        "notebook_path": "Full workspace path to the scanned notebook",
        "notebook_name": "Display name of the scanned notebook",
        "detector_name": "TruffleHog detector that matched (e.g. AWS, Slack, GitHub, GitLab)",
        "secret_sha256": "SHA-256 hash of the detected secret value — the actual secret is never stored",
        "source_file":   "Source file within the notebook where the secret was detected",
        "verified":      "True if TruffleHog confirmed the secret is currently active and valid",
        "secrets_found": "Count of secrets detected. 0 with NULL other fields means the workspace was clean.",
        "run_id":        "SAT secret scan run ID",
        "scan_time":     "Timestamp when the scan was performed",
        "scan_date":     "Date partition derived from scan_time",
        "scan_hhmm":     "Hour and minute as integer (HHMM) derived from scan_time",
    })


def create_clusters_secret_scan_results_table():
    schema = json_["analysis_schema_name"]
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.clusters_secret_scan_results (
        workspace_id STRING,
        cluster_id STRING,
        cluster_name STRING,
        config_field STRING,
        config_key STRING,
        detector_name STRING,
        secret_sha256 STRING,
        source_file STRING,
        verified BOOLEAN,
        secrets_found INTEGER,
        run_id BIGINT,
        scan_time TIMESTAMP,
        scan_date DATE GENERATED ALWAYS AS (CAST(scan_time AS DATE)),
        scan_hhmm INTEGER GENERATED ALWAYS AS (CAST(CAST(hour(scan_time) as STRING) || CAST(minute(scan_time) as STRING) as INTEGER))
    )
    USING DELTA
    PARTITIONED BY (scan_date)
    """
    )
    _set_table_comment(
        schema, "clusters_secret_scan_results",
        "TruffleHog secret scan results for Databricks cluster configurations. Detects hardcoded secrets in Spark config, "
        "environment variables, and init scripts. When secrets_found=0 and other fields are NULL, the workspace was "
        "scanned and found clean."
    )
    _set_column_comments(schema, "clusters_secret_scan_results", {
        "workspace_id":  "Databricks workspace ID where the cluster was found",
        "cluster_id":    "Databricks cluster ID that was scanned",
        "cluster_name":  "Display name of the scanned cluster",
        "config_field":  "Cluster configuration section where the secret was found (e.g. spark_conf, env_vars)",
        "config_key":    "Specific configuration key containing the potential secret",
        "detector_name": "TruffleHog detector that matched (e.g. AWS, Slack, GitHub, GitLab)",
        "secret_sha256": "SHA-256 hash of the detected secret value — the actual secret is never stored",
        "source_file":   "Source location within the cluster config where the secret was detected",
        "verified":      "True if TruffleHog confirmed the secret is currently active and valid",
        "secrets_found": "Count of secrets detected. 0 with NULL other fields means the cluster config was clean.",
        "run_id":        "SAT secret scan run ID",
        "scan_time":     "Timestamp when the scan was performed",
        "scan_date":     "Date partition derived from scan_time",
        "scan_hhmm":     "Hour and minute as integer (HHMM) derived from scan_time",
    })


# COMMAND ----------


def create_workspace_run_complete_table():
    schema = json_["analysis_schema_name"]
    df = spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema}.workspace_run_complete(
                    workspace_id string,
                    run_id bigint,
                    completed boolean,
                    check_time timestamp,
                    chk_date date GENERATED ALWAYS AS (CAST(check_time AS DATE))
                    )
                    USING DELTA"""
    )
    _set_table_comment(
        schema, "workspace_run_complete",
        "Tracks per-workspace completion status for each SAT run. Use to identify which workspaces completed "
        "successfully and which failed in a given run. Join to run_number_table on run_id."
    )
    _set_column_comments(schema, "workspace_run_complete", {
        "workspace_id": "Databricks workspace ID",
        "run_id":       "SAT run ID — foreign key to run_number_table.runID",
        "completed":    "True if the workspace analysis completed successfully in this run",
        "check_time":   "Timestamp when the workspace analysis completed",
        "chk_date":     "Date partition derived from check_time",
    })


# COMMAND ----------


# Comments are a metadata change on the table. Every notebook re-applies them at
# startup, so when collection jobs run concurrently one job's comment change can
# conflict with another job's write on the same shared table (e.g.
# run_number_table), raising DELTA_METADATA_CHANGED. Comments are cosmetic, so a
# failure here must never abort the run -- swallow it and move on.
def _set_table_comment(schema, table, comment):
    safe = comment.replace("'", "''")
    try:
        spark.sql(f"COMMENT ON TABLE {schema}.`{table}` IS '{safe}'")
    except Exception:
        pass


def _set_column_comments(schema, table, col_comments):
    for col, comment in col_comments.items():
        safe = comment.replace("'", "''")
        try:
            spark.sql(f"ALTER TABLE {schema}.`{table}` ALTER COLUMN `{col}` COMMENT '{safe}'")
        except Exception:
            pass


# COMMAND ----------

def generateGCPWSToken(deployment_url, cred_file_path,target_principal):
    from google.oauth2 import service_account
    import gcsfs
    import json 
    gcp_accounts_url = 'https://accounts.gcp.databricks.com'
    target_scopes = [deployment_url]
    print(target_scopes)
    # Reading gcs files with gcsfs
    gcs_file_system = gcsfs.GCSFileSystem(project="gcp_project_name")
    gcs_json_path = cred_file_path
    with gcs_file_system.open(gcs_json_path) as f:
      json_dict = json.load(f)
      key = json.dumps(json_dict) 
    source_credentials = service_account.Credentials.from_service_account_info(json_dict,scopes=target_scopes)
    from google.auth import impersonated_credentials
    from google.auth.transport.requests import AuthorizedSession

    target_credentials = impersonated_credentials.Credentials(
      source_credentials=source_credentials,
      target_principal=target_principal,
      target_scopes = target_scopes,
      lifetime=36000)

    creds = impersonated_credentials.IDTokenCredentials(
                                      target_credentials,
                                      target_audience=deployment_url,
                                      include_email=True)

    authed_session = AuthorizedSession(creds)
    resp = authed_session.get(gcp_accounts_url)
    return creds.token
    

# COMMAND ----------

from pyspark.sql import DataFrame
def isEmpty(df: DataFrame):
    return len(df.take(1))==0

# COMMAND ----------

def process_json_schema(df):
    from pyspark.sql.functions import schema_of_json, col, from_json,collect_set,explode
    #df_with_schemas = df.select(explode(collect_set(schema_of_json(col("json_string")))).alias("schema"))
    df_with_schemas = df.select(schema_of_json(col("json_string")).alias("schema")).distinct()

    from pyspark.sql.types import StructType
    from collections import OrderedDict

    all_fields = OrderedDict()

    for row in df_with_schemas.select("schema").collect():
        schema_str = row.schema
        # Remove the outer 'STRUCT<' and '>' 
        inner_schema = schema_str[7:-1]
        schema = StructType.fromDDL(inner_schema)        
        for field in schema.fields:
            all_fields[field.name] = field
    final_struct = StructType(list(all_fields.values()))
    return final_struct

