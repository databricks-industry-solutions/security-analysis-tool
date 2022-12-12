# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceGlobalTempView('all_workspaces') 

# COMMAND ----------

import json
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

workspacedf = spark.sql("select * from `global_temp`.`all_workspaces` where workspace_id='" + current_workspace + "'" )
if (workspacedf.rdd.isEmpty()):
    dbutils.notebook.exit("The current workspace is not found in configured list of workspaces for analysis.")
display(workspacedf)
ws = (workspacedf.collect())[0]

# COMMAND ----------

workspacesdf = spark.sql('select * from `global_temp`.`all_workspaces`')
display(workspacesdf)
workspaces = workspacesdf.collect()

# COMMAND ----------

#todo: Add parent folder to all SQL assets, expose name in _json (default SAT)
#create a folder to house all SAT sql artifacts
import requests
def create_ws_folder(ws, dir_name):
    #delete tthe WS folder if it exists
    delete_ws_folder(ws, dir_name)
    
    token = dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token)
    url = "https://"+ ws.deployment_url
    headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
    path = "/Users/"+context['tags']['user']+"/"+ dir_name
    body = {"path":  path}
    target_url = url + "/api/2.0/workspace/mkdirs"
    
    loggr.info(f"Creating {path} using {target_url}")
    requests.post(target_url, headers=headers, json=body,timeout=60).json()
    
    target_url = url + "/api/2.0/workspace/get-status"
    loggr.info(f"Get Status {path} using {target_url}")
    response=requests.get(target_url, headers=headers, json=body).json()    
    print(response)
    return response['object_id']


#delete folder that houses all SAT sql artifacts
def get_ws_folder_object_id(ws, dir_name):
    
    #Use the workspace list API to get the object_id for the folder you want to use. 
    #Here’s an example for how to get it for a folder called “/Users/me@example.com”:
    token = dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token)
    url = "https://"+ ws.deployment_url
    headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
    path = "/Users/"+context['tags']['user']+"/"
    body = {"path":  path}
    
    target_url = url + "/api/2.0/workspace/list"
    loggr.info(f"Get metadata for all of the subfolders and objects in this path {path} using {target_url}")
    response=requests.get(target_url, headers=headers, json=body, timeout=60).json()    
    loggr.info(response['objects'])
    path = path+dir_name
    for ws_objects in response['objects']:
        loggr.info(ws_objects)
        if str(ws_objects['object_type']) == 'DIRECTORY' and str(ws_objects['path']) == path:
            return str(ws_objects['object_id'])
    
    
    return None
    

#delete folder that houses all SAT sql artifacts
def delete_ws_folder(ws, dir_name):
    
    token = dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token)
    url = "https://"+ ws.deployment_url
    headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
    path = "/Users/"+context['tags']['user']+"/"+ dir_name
    body = {"path":  path, "recursive": True}
    target_url = url + "/api/2.0/workspace/delete"
    loggr.info(f"Creating {path} using {target_url}")
    
    requests.post(target_url, headers=headers, json=body, timeout=60  ).json()
    loggr.info(f"Dir {dir_name} deleted")
    


# COMMAND ----------

folder_id = create_ws_folder(ws, 'SAT_alerts')

# COMMAND ----------

#object_id = get_ws_folder_object_id(ws, 'SAT')

#loggr.info(f"Using object_id for the SAT folder : {object_id}!") 

# COMMAND ----------

import requests
data_source_id =''
user_id = None
DOMAIN = ws.deployment_url
TOKEN =  dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token) 
        
loggr.info(f"Looking for data_source_id for : {json_['sql_warehouse_id']}!") 
       
response = requests.get(
          'https://%s/api/2.0/preview/sql/data_sources' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=None,
          timeout=60  
        )
resources = json.loads(response.text)
#print (resources)
for resource in resources:
    if resource['endpoint_id'] == json_['sql_warehouse_id']:
        data_source_id = resource['id']
        loggr.info(f"Found data_source_id for : {json_['sql_warehouse_id']}!") 

# COMMAND ----------

import requests
DOMAIN = ws.deployment_url
TOKEN =  dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token) 
loggr.info(f"Creating alerts on: {DOMAIN}!") 

#load alerts templates for each workspace
for ws_to_load in workspaces:

    alert_name = "sat_alerts_"+ws_to_load.workspace_id
    body = {"name" : alert_name}
    response = requests.get(
              'https://%s/api/2.0/preview/sql/alerts' % (DOMAIN),
              json = body,
              headers={'Authorization': 'Bearer %s' % TOKEN},
              timeout=60)
    alerts = response.json()
    found = False
    #for alert in alerts:
    #    if (alert['name'] == alert_name):
    #        found = True
    #if alert is already configured, or folder is not found move on to next ws
    if (response.status_code == 200 and found):
        loggr.info(f"Alert already configured for workspace {ws_to_load.workspace_id}") 
        continue

    if (folder_id is None):
        loggr.info(f"Folder can't be created or found {ws_to_load.workspace_id}") 
        continue    
    response = requests.post(
              'https://%s/api/2.0/preview/sql/queries' % (DOMAIN),
              headers={'Authorization': 'Bearer %s' % TOKEN},
              json={
                        "data_source_id":data_source_id,
                        "name": "sat_alert_"+ws_to_load.workspace_id,
                        "description": "",
                        "parent":"folders/"+str(folder_id),
                        "query": "SELECT\n  concat(\"<br> <b>Check name:</b> \",sbp.check_id, \", <b>Check:</b>\" , sbp.check, \" in workspace:\", sc.workspaceid, \n  \", <b>Recommendation:</b>\",sbp.recommendation, \"</br>\" ) as message,  count(*) as total\nFROM\n  security_analysis.security_checks sc,\n  security_analysis.security_best_practices sbp\nWHERE \nsbp.id = sc.id and\nsc.workspaceid = "+ws_to_load.workspace_id+" and\nsbp.alert = 1 and sc.score = 1 and run_id = (\n    select\n      max(runID)\n    from\n      security_analysis.run_number_table\n  )\nGROUP BY \n1\nORDER BY total DESC\n\n\n\n\n"

                      },
              timeout=60  
            )

    if response.status_code == 200:
        loggr.info(f"Alert query is successfuly created: {response.json()['id']}!")
        query_id = response.json()["id"] 
    else:
        loggr.info(f"Error creating alert query: {(response.json())}")   

    if query_id is not None:
        response = requests.post(
                  'https://%s/api/2.0/preview/sql/alerts' % (DOMAIN),
                  headers={'Authorization': 'Bearer %s' % TOKEN},
                  json={
                   "name":"sat_alerts_"+ws_to_load.workspace_id+"",
                   "options":{
                      "op":">=",
                      "value":1,
                      "muted":False,
                      "column":"total",
                      "custom_subject":"SAT-Alert for workspace:"+ws_to_load.workspace_id,
                      "custom_body":"Hello,\nAlert \"{{ALERT_NAME}}\" changed status to {{ALERT_STATUS}}.\nThere have been the following unexpected events on the last day:\n{{QUERY_RESULT_ROWS}}\n\n",
                      "schedule_failures":0
                
                   },
                   "query_id":query_id,
                   "parent":"folders/"+str(folder_id)   
                },
                timeout=60  
                )

    if response.status_code == 200:
        loggr.info(f"Alert is successfuly created {response.json()['id']}!")
        alert_id = response.json()["id"]
    else:
        loggr.info(f"Error creating alert: {(response.json())}")  

    if alert_id is not None:
        response = requests.get(
                      'https://%s/api/2.0/preview/scim/v2/Users?filter=userName+eq+%s' % (DOMAIN,ws_to_load.alert_subscriber_user_id),
                      headers={'Authorization': 'Bearer %s' % TOKEN},
                      json=None,
                      timeout=60
                    )

    result = json.loads(response.text)
    if result['totalResults'] != 0 :
        resources = result['Resources']
        for resource in resources:
            user_id = resource["id"]

            if user_id is not None:
                response = requests.post(
                          'https://%s/api/2.0/preview/sql/alerts/%s/subscriptions' % (DOMAIN, alert_id),
                          headers={'Authorization': 'Bearer %s' % TOKEN},
                          json={
                              "alert_id":alert_id,
                              "user_id":user_id
                            },
                          timeout=60  
                        )

                if response.status_code == 200:
                    loggr.info(f"Alert subscription is successfuly associated to user {response.json()['user']}!")
                else:
                    loggr.info(f"Error creating alert subscription: {(response.json())}")
                    dbutils.notebook.exit("Error creating alert subscription")
            else: 
                loggr.info(f"User not found with login : {ws_to_load.alert_subscriber_user_id}")
                dbutils.notebook.exit("Error creating alert subscription, Configured user not found " + user_id )

# COMMAND ----------

dbutils.notebook.exit('OK')
