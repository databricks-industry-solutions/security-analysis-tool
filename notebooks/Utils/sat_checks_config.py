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

def getConfigPath():
  import os
  cwd = os.getcwd().lower()
  if (cwd.rfind('/includes') != -1) or (cwd.rfind('/setup') != -1) or (cwd.rfind('/utils') != -1):
    return '../../configs'
  elif (cwd.rfind('/notebooks') != -1):
    return '../configs'
  else:
    return 'configs'

# COMMAND ----------

#Account Level SAT Check Configuration

#SET & GET SAT check configurations for the organization
def get_sat_check_config():
    sat_check = dbutils.widgets.get("sat_check")
    check_id = sat_check.split('_')[0]

    s_sql = '''
                SELECT enable, evaluation_value, alert
                FROM {analysis_schema_name}.security_best_practices 
                WHERE check_id= '{check_id}'
            '''.format(check_id = check_id, analysis_schema_name= json_["analysis_schema_name"])

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
                UPDATE  {analysis_schema_name}.security_best_practices 
                SET enable = {enable}, 
                    evaluation_value={evaluation_value}, 
                    alert = {alert}
                WHERE check_id= '{check_id}'
            '''.format(enable=enable, evaluation_value=evaluation_value, alert=alert, check_id = check_id, analysis_schema_name= json_["analysis_schema_name"])
    print(s_sql)
    spark.sql(s_sql)
    
    #update user config file (security_best_practices_user.csv)
    prefix = getConfigPath()
    userfile = f'{prefix}/security_best_practices_user.csv'
    security_best_practices_pd = spark.table(f'{json_["analysis_schema_name"]}.security_best_practices').toPandas()
    security_best_practices_pd.to_csv(userfile, encoding='utf-8', index=False)
    
#Reset SAT check widgets 
def get_all_sat_checks():
    dbutils.widgets.removeAll()

    hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
    cloud_type = getCloudType(hostname)

    s_sql = '''
        SELECT CONCAT_WS('_',check_id, category, check) AS check
        FROM {analysis_schema_name}.security_best_practices 
        WHERE {cloud_type}=1
        '''.format(cloud_type = cloud_type, analysis_schema_name= json_["analysis_schema_name"])

    all_checks = spark.sql(s_sql)
    checks = all_checks.rdd.map(lambda row : row[0]).collect()

    checks.sort()
    first_check = str(checks[0])

    #Define Driver Widgets
    dbutils.widgets.dropdown("sat_check", first_check, [str(x) for x in checks], "a. SAT Check")

# COMMAND ----------

#Workspace Level SAT Check Configuration
params = {'Analysis Enabled': 'analysis_enabled', 
                  'SSO Enabled':'sso_enabled', 
                  'SCIM Enabled': 'scim_enabled', 
                  'ANY VPC PEERING': 'vpc_peering_done', 
                  'Object Storage Encrypted': 'object_storage_encrypted', 
                  'Table Access Control Enabled':'table_access_control_enabled'}
#SET & GET SAT check configurations for the workspace
import yaml
def get_workspace_check_config():
    prefix = getConfigPath()
    userfile = f'{prefix}/manual_sat_check.yaml'
    # Load the YAML configuration
    with open(userfile, 'r') as file:
        all_checks = yaml.safe_load(file)
    
    # Prepare a list to hold the extracted data
    checks_data = {}

    # Iterate over each entry to extract required fields
    for check in all_checks:
        checks_data[check['check_id']] = {
            'check': check['check'],
            'enabled': check['enabled']
        }
    return checks_data
    
def set_workspace_check_config(checks_data):
    #Retrieve widget values 
    sso_enabled = checks_data['IA-1']['enabled'].lower()
    scim_enabled = checks_data['IA-2']['enabled'].lower()
    vpc_peering_done = checks_data['INFO-7']['enabled'].lower()
    object_storage_encrypted = checks_data['DP-4']['enabled'].lower()
    table_access_control_enabled = checks_data['IA-3']['enabled'].lower()
    apply_setting_to_all_ws_enabled = dbutils.widgets.get("apply_setting_to_all_ws_enabled")
    
    ws_id = workspace.split('_')[-1]
    
    if apply_setting_to_all_ws_enabled == '':
        s_sql = '''
                    UPDATE  {analysis_schema_name}.account_workspaces 
                    SET sso_enabled={sso_enabled}, 
                        scim_enabled = {scim_enabled},
                        vpc_peering_done = {vpc_peering_done},
                        object_storage_encrypted = {object_storage_encrypted},
                        table_access_control_enabled = {table_access_control_enabled}
                '''.format(analysis_enabled=analysis_enabled, sso_enabled=sso_enabled, scim_enabled=scim_enabled, 
                           vpc_peering_done=vpc_peering_done, object_storage_encrypted=object_storage_encrypted, 
                           table_access_control_enabled=table_access_control_enabled, ws_id = ws_id, analysis_schema_name= json_["analysis_schema_name"])
        print(s_sql)
        spark.sql(s_sql)
    else:
        s_sql = 'UPDATE  "{analysis_schema_name}".account_workspaces SET '
        first_param=False
        for param in params:
            if param in apply_setting_to_all_ws_enabled:
                val = params[param]
                if first_param == True:
                    s_sql = s_sql + ","
                s_sql = s_sql + val + "=" + eval(params[param])
                first_param=True
        print(s_sql)
        spark.sql(s_sql.format(analysis_schema_name= json_["analysis_schema_name"]))
        
#Reset widget values to empty
def get_all_workspaces():
    dbutils.widgets.removeAll()

    s_sql = '''
            SELECT CONCAT_WS('_',workspace_name, workspace_id) AS ws
            FROM {analysis_schema_name}.account_workspaces 
          '''.format(analysis_schema_name= json_["analysis_schema_name"])
    all_workspaces = spark.sql(s_sql)
    workspaces = all_workspaces.rdd.map(lambda row : row[0]).collect()
    first_ws = str(workspaces[0])

    #Define Driver Widgets
    #dbutils.widgets.dropdown("workspaces", first_ws, [str(x) for x in workspaces], "a. Workspaces")

# COMMAND ----------


