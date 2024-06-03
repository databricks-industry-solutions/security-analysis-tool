# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** sat_checks_config
# MAGIC **Functionality:** initializes the necessary configruation values for the rest of the process into a json

# COMMAND ----------

# MAGIC %run ./common
# MAGIC

# COMMAND ----------

# Account Level SAT Check Configuration


# SET & GET SAT check configurations for the organization
def get_sat_check_config():
    sat_check = dbutils.widgets.get("sat_check")
    check_id = sat_check.split("_")[0]

    s_sql = """
                SELECT enable, evaluation_value, alert
                FROM {analysis_schema_name}.security_best_practices 
                WHERE check_id= '{check_id}'
            """.format(
        check_id=check_id, analysis_schema_name=json_["analysis_schema_name"]
    )

    get_check = spark.sql(s_sql)
    check = get_check.toPandas().to_dict(orient="list")

    enable = check["enable"][0]
    evaluate = check["evaluation_value"][0]
    alert = check["alert"][0]

    dbutils.widgets.dropdown(
        "check_enabled", str(enable), ["0", "1"], "b. Check Enabled"
    )
    dbutils.widgets.text("evaluation_value", str(evaluate), "c. Evaluation Value")
    dbutils.widgets.text("alert", str(alert), "d. Alert")


def set_sat_check_config():
    # Retrieve widget values
    sat_check = dbutils.widgets.get("sat_check")
    enable = dbutils.widgets.get("check_enabled")
    evaluation_value = dbutils.widgets.get("evaluation_value")
    alert = dbutils.widgets.get("alert")

    check_id = sat_check.split("_")[0]

    s_sql = """
                UPDATE  {analysis_schema_name}.security_best_practices 
                SET enable = {enable}, 
                    evaluation_value={evaluation_value}, 
                    alert = {alert}
                WHERE check_id= '{check_id}'
            """.format(
        enable=enable,
        evaluation_value=evaluation_value,
        alert=alert,
        check_id=check_id,
        analysis_schema_name=json_["analysis_schema_name"],
    )
    print(s_sql)
    spark.sql(s_sql)

    # update user config file (security_best_practices_user.csv)
    prefix = getConfigPath()
    userfile = f"{prefix}/security_best_practices_user.csv"
    security_best_practices_pd = spark.table(
        f'{json_["analysis_schema_name"]}.security_best_practices'
    ).toPandas()
    security_best_practices_pd.to_csv(userfile, encoding="utf-8", index=False)


# Reset SAT check widgets
def get_all_sat_checks():
    dbutils.widgets.removeAll()

    hostname = (
        dbutils.notebook.entry_point.getDbutils()
        .notebook()
        .getContext()
        .apiUrl()
        .getOrElse(None)
    )
    cloud_type = getCloudType(hostname)

    s_sql = """
        SELECT CONCAT_WS('_',check_id, category, check) AS check
        FROM {analysis_schema_name}.security_best_practices 
        WHERE {cloud_type}=1
        """.format(
        cloud_type=cloud_type, analysis_schema_name=json_["analysis_schema_name"]
    )

    all_checks = spark.sql(s_sql)
    checks = all_checks.rdd.map(lambda row: row[0]).collect()

    checks.sort()
    first_check = str(checks[0])

    # Define Driver Widgets
    dbutils.widgets.dropdown(
        "sat_check", first_check, [str(x) for x in checks], "a. SAT Check"
    )


# COMMAND ----------

# Workspace Level SAT Check Configuration
params = {
    "Analysis Enabled": "analysis_enabled",
    "SSO Enabled": "sso_enabled",
    "SCIM Enabled": "scim_enabled",
    "ANY VPC PEERING": "vpc_peering_done",
    "Object Storage Encrypted": "object_storage_encrypted",
    "Table Access Control Enabled": "table_access_control_enabled",
}


# SET & GET SAT check configurations for the workspace
def get_workspace_check_config():
    workspace = dbutils.widgets.get("workspaces")
    ws_id = workspace.split("_")[-1]

    s_sql = """
                SELECT analysis_enabled, sso_enabled, scim_enabled, vpc_peering_done, object_storage_encrypted, 
                table_access_control_enabled
                FROM {analysis_schema_name}.account_workspaces
                WHERE workspace_id= '{ws_id}'
            """.format(
        ws_id=ws_id, analysis_schema_name=json_["analysis_schema_name"]
    )

    get_workspace = spark.sql(s_sql)
    check = get_workspace.toPandas().to_dict(orient="list")

    analysis_enabled = check["analysis_enabled"][0]
    sso_enabled = check["sso_enabled"][0]
    scim_enabled = check["scim_enabled"][0]
    vpc_peering_done = check["vpc_peering_done"][0]
    object_storage_encrypted = check["object_storage_encrypted"][0]
    table_access_control_enabled = check["table_access_control_enabled"][0]

    dbutils.widgets.dropdown(
        "analysis_enabled",
        str(analysis_enabled),
        ["False", "True"],
        "b. Analysis Enabled",
    )
    dbutils.widgets.dropdown(
        "sso_enabled", str(sso_enabled), ["False", "True"], "c. SSO Enabled"
    )
    dbutils.widgets.dropdown(
        "scim_enabled", str(scim_enabled), ["False", "True"], "d. SCIM Enabled"
    )
    dbutils.widgets.dropdown(
        "vpc_peering_done",
        str(vpc_peering_done),
        ["False", "True"],
        "e. ANY VPC PEERING",
    )
    dbutils.widgets.dropdown(
        "object_storage_encrypted",
        str(object_storage_encrypted),
        ["False", "True"],
        "f. Object Storage Encrypted",
    )
    dbutils.widgets.dropdown(
        "table_access_control_enabled",
        str(table_access_control_enabled),
        ["False", "True"],
        "g. Table Access Control Enabled",
    )
    dbutils.widgets.multiselect(
        "apply_setting_to_all_ws_enabled",
        "",
        [
            "",
            "Analysis Enabled",
            "SSO Enabled",
            "SCIM Enabled",
            "ANY VPC PEERING",
            "Object Storage Encrypted",
            "Table Access Control Enabled",
        ],
        "i. Apply Setting to all workspaces",
    )


def set_workspace_check_config():
    # Retrieve widget values
    workspace = dbutils.widgets.get("workspaces")
    analysis_enabled = dbutils.widgets.get("analysis_enabled").lower()
    sso_enabled = dbutils.widgets.get("sso_enabled").lower()
    scim_enabled = dbutils.widgets.get("scim_enabled").lower()
    vpc_peering_done = dbutils.widgets.get("vpc_peering_done").lower()
    object_storage_encrypted = dbutils.widgets.get("object_storage_encrypted").lower()
    table_access_control_enabled = dbutils.widgets.get(
        "table_access_control_enabled"
    ).lower()
    apply_setting_to_all_ws_enabled = dbutils.widgets.get(
        "apply_setting_to_all_ws_enabled"
    )

    ws_id = workspace.split("_")[-1]

    if apply_setting_to_all_ws_enabled == "":
        s_sql = """
                    UPDATE  {analysis_schema_name}.account_workspaces 
                    SET analysis_enabled = {analysis_enabled}, 
                        sso_enabled={sso_enabled}, 
                        scim_enabled = {scim_enabled},
                        vpc_peering_done = {vpc_peering_done},
                        object_storage_encrypted = {object_storage_encrypted},
                        table_access_control_enabled = {table_access_control_enabled}
                    WHERE workspace_id= '{ws_id}'
                """.format(
            analysis_enabled=analysis_enabled,
            sso_enabled=sso_enabled,
            scim_enabled=scim_enabled,
            vpc_peering_done=vpc_peering_done,
            object_storage_encrypted=object_storage_encrypted,
            table_access_control_enabled=table_access_control_enabled,
            ws_id=ws_id,
            analysis_schema_name=json_["analysis_schema_name"],
        )
        print(s_sql)
        spark.sql(s_sql)
    else:
        s_sql = 'UPDATE  "{analysis_schema_name}".account_workspaces SET '
        first_param = False
        for param in params:
            if param in apply_setting_to_all_ws_enabled:
                val = params[param]
                if first_param == True:
                    s_sql = s_sql + ","
                s_sql = s_sql + val + "=" + eval(params[param])
                first_param = True
        print(s_sql)
        spark.sql(s_sql.format(analysis_schema_name=json_["analysis_schema_name"]))


# Reset widget values to empty
def get_all_workspaces():
    dbutils.widgets.removeAll()

    s_sql = """
            SELECT CONCAT_WS('_',workspace_name, workspace_id) AS ws
            FROM {analysis_schema_name}.account_workspaces 
          """.format(
        analysis_schema_name=json_["analysis_schema_name"]
    )
    all_workspaces = spark.sql(s_sql)
    workspaces = all_workspaces.rdd.map(lambda row: row[0]).collect()
    first_ws = str(workspaces[0])

    # Define Driver Widgets
    dbutils.widgets.dropdown(
        "workspaces", first_ws, [str(x) for x in workspaces], "a. Workspaces"
    )


# COMMAND ----------

# Workspace Level SAT Check Configuration
params = {
    "Analysis Enabled": "analysis_enabled",
    "SSO Enabled": "sso_enabled",
    "SCIM Enabled": "scim_enabled",
    "ANY VPC PEERING": "vpc_peering_done",
    "Object Storage Encrypted": "object_storage_encrypted",
    "Table Access Control Enabled": "table_access_control_enabled",
}
# SET & GET SAT check configurations for the workspace
import yaml


def get_workspace_self_assessment_check_config():
    prefix = getConfigPath()
    userfile = f"{prefix}/self_assessment_checks.yaml"
    # Load the YAML configuration
    with open(userfile, "r") as file:
        all_checks = yaml.safe_load(file)

    # Prepare a list to hold the extracted data
    checks_data = {}

    # Iterate over each entry to extract required fields
    for check in all_checks:
        checks_data[check["id"]] = {
            "check": check["check"],
            "enabled": check["enabled"],
        }
    return checks_data


def set_workspace_self_assessment_check_config(checks_data):
    # Retrieve widget values

    cloud_type = getCloudType(hostname)
    if cloud_type == "azure" or cloud_type == "gcp" :
            sso_enabled = 'true'
    else:
        sso_enabled = checks_data.get(18)["enabled"]

    scim_enabled = checks_data.get(19)["enabled"]
    vpc_peering_done = checks_data.get(28)["enabled"]
    object_storage_encrypted = checks_data.get(4)["enabled"]
    table_access_control_enabled = checks_data.get(20)["enabled"]
    # apply_setting_to_all_ws_enabled = dbutils.widgets.get("apply_setting_to_all_ws_enabled")

    # ws_id = workspace.split('_')[-1]

    s_sql = """
                UPDATE  {analysis_schema_name}.account_workspaces 
                SET sso_enabled={sso_enabled}, 
                    scim_enabled = {scim_enabled},
                    vpc_peering_done = {vpc_peering_done},
                    object_storage_encrypted = {object_storage_encrypted},
                    table_access_control_enabled = {table_access_control_enabled}
            """.format(
        sso_enabled=sso_enabled,
        scim_enabled=scim_enabled,
        vpc_peering_done=vpc_peering_done,
        object_storage_encrypted=object_storage_encrypted,
        table_access_control_enabled=table_access_control_enabled,
        analysis_schema_name=json_["analysis_schema_name"],
    )
    print(s_sql)
    spark.sql(s_sql)
