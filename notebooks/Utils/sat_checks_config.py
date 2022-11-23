# Databricks notebook source
#Determine cloud type
def getCloudType(url):
  if '.cloud.' in url:
    return 'aws'
  elif '.azuredatabricks.' in url:
    return 'azure'
  elif '.gcp.' in url:
    return 'gcp'
  return ''

# COMMAND ----------

#Account Level SAT Check Configuration

#SET & GET SAT check configurations for the organization
def get_sat_check_config():
    sat_check = dbutils.widgets.get("sat_check")
    check_id = sat_check.split('_')[0]

    s_sql = '''
                SELECT enable, evaluation_value, alert
                FROM security_analysis.security_best_practices 
                WHERE check_id= '{check_id}'
            '''.format(check_id = check_id)

    get_check = spark.sql(s_sql)
    check = get_check.toPandas().to_dict(orient = 'list')
    
    enable = check['enable'][0]
    evaluate = check['evaluation_value'][0]
    alert = check['alert'][0]

    dbutils.widgets.dropdown("check_enabled", str(enable),  ['0','1'], "b. Check Enabled")
    dbutils.widgets.text("evaluation_value", str(evaluate), "c. Evaluation Value")
    dbutils.widgets.text("alert", str(alert), "d. Alert")
    
def set_sat_check_config():
    #Retrieve widget values 
    sat_check = dbutils.widgets.get("sat_check")
    enable = dbutils.widgets.get("check_enabled")
    evaluation_value = dbutils.widgets.get("evaluation_value")
    alert = dbutils.widgets.get("alert")
    
    check_id = sat_check.split('_')[0]

    s_sql = '''
                UPDATE  security_analysis.security_best_practices 
                SET enable = {enable}, 
                    evaluation_value={evaluation_value}, 
                    alert = {alert}
                WHERE check_id= '{check_id}'
            '''.format(enable=enable, evaluation_value=evaluation_value, alert=alert, check_id = check_id)
    #print(s_sql)
    spark.sql(s_sql)
    
#Reset SAT check widgets 
def get_all_sat_checks():
    dbutils.widgets.removeAll()

    hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
    cloud_type = getCloudType(hostname)

    s_sql = '''
        SELECT CONCAT_WS('_',check_id, category, check) AS check
        FROM security_analysis.security_best_practices 
        WHERE {cloud_type}=1
        '''.format(cloud_type = cloud_type)

    all_checks = spark.sql(s_sql)
    checks = all_checks.rdd.map(lambda row : row[0]).collect()

    checks.sort()
    first_check = str(checks[0])

    #Define Driver Widgets
    dbutils.widgets.dropdown("sat_check", first_check, [str(x) for x in checks], "a. SAT Check")

# COMMAND ----------



# COMMAND ----------

#Workspace Level SAT Check Configuration

#SET & GET SAT check configurations for the workspace
def get_workspace_check_config():
    workspace = dbutils.widgets.get("workspaces")
    ws_id = workspace.split('_')[1]

    s_sql = '''
                SELECT analysis_enabled, sso_enabled, scim_enabled, vpc_peering_done, object_storage_encypted, 
                table_access_control_enabled, alert_subscriber_user_id
                FROM security_analysis.account_workspaces
                WHERE workspace_id= '{ws_id}'
            '''.format(ws_id = ws_id)

    get_workspace = spark.sql(s_sql)
    check = get_workspace.toPandas().to_dict(orient = 'list')
    
    analysis_enabled = check['analysis_enabled'][0]
    sso_enabled = check['sso_enabled'][0]
    scim_enabled = check['scim_enabled'][0]
    vpc_peering_done = check['vpc_peering_done'][0]
    object_storage_encypted = check['object_storage_encypted'][0]
    table_access_control_enabled = check['table_access_control_enabled'][0]
    alert_subscriber_user_id = check['alert_subscriber_user_id'][0]

    dbutils.widgets.dropdown("analysis_enabled", str(analysis_enabled),  ['False','True'], "b. Analysis Enabled")
    dbutils.widgets.dropdown("sso_enabled", str(sso_enabled),  ['False','True'], "c. SSO Enabled")
    dbutils.widgets.dropdown("scim_enabled", str(analysis_enabled),  ['False','True'], "d. SCIM Enabled")    
    dbutils.widgets.dropdown("vpc_peering_done", str(vpc_peering_done),  ['False','True'], "e. ANY VPC PEERING")
    dbutils.widgets.dropdown("object_storage_encypted", str(vpc_peering_done),  ['False','True'], "f. Object Storage Encypted")
    dbutils.widgets.dropdown("table_access_control_enabled", str(table_access_control_enabled),  ['False','True'], "g. Table Access Control Enabled")
    dbutils.widgets.text("alert_subscriber_user_id", str(alert_subscriber_user_id), "h. Alert Subscriber User Id")
    
def set_workspace_check_config():
    #Retrieve widget values 
    workspace = dbutils.widgets.get("workspaces")
    analysis_enabled = dbutils.widgets.get("analysis_enabled").lower()
    sso_enabled = dbutils.widgets.get("sso_enabled").lower()
    scim_enabled = dbutils.widgets.get("scim_enabled").lower()
    vpc_peering_done = dbutils.widgets.get("vpc_peering_done").lower()
    object_storage_encypted = dbutils.widgets.get("object_storage_encypted").lower()
    table_access_control_enabled = dbutils.widgets.get("table_access_control_enabled").lower()
    alert_subscriber_user_id = dbutils.widgets.get("alert_subscriber_user_id")
    
    ws_id = workspace.split('_')[1]

    s_sql = '''
                UPDATE  security_analysis.account_workspaces 
                SET analysis_enabled = {analysis_enabled}, 
                    sso_enabled={sso_enabled}, 
                    scim_enabled = {scim_enabled},
                    vpc_peering_done = {vpc_peering_done},
                    object_storage_encypted = {object_storage_encypted},
                    table_access_control_enabled = {table_access_control_enabled},
                    alert_subscriber_user_id = '{alert_subscriber_user_id}'
                WHERE workspace_id= '{ws_id}'
            '''.format(analysis_enabled=analysis_enabled, sso_enabled=sso_enabled, scim_enabled=scim_enabled, 
                       vpc_peering_done=vpc_peering_done, object_storage_encypted=object_storage_encypted, 
                       table_access_control_enabled=table_access_control_enabled, alert_subscriber_user_id=alert_subscriber_user_id, ws_id = ws_id)
    #print(s_sql)
    spark.sql(s_sql)
    
#Reset widget values to empty

def get_all_workspaces():
    dbutils.widgets.removeAll()

    s_sql = '''
        SELECT CONCAT_WS('_',workspace_name, workspace_id) AS ws
        FROM security_analysis.account_workspaces 
        '''

    all_workspaces = spark.sql(s_sql)
    workspaces = all_workspaces.rdd.map(lambda row : row[0]).collect()
    first_ws = str(workspaces[0])

    #Define Driver Widgets
    dbutils.widgets.dropdown("workspaces", first_ws, [str(x) for x in workspaces], "a. Workspaces")

# COMMAND ----------


