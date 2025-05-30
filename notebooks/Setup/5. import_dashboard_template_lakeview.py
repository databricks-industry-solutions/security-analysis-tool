# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 5. import_dashboard_template_lakeview.      
# MAGIC **Functionality:** Imports dashboard template from code repo into Lakeview Dashboards section for SAT report.  

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceTempView('all_workspaces') 

# COMMAND ----------

from dbruntime.databricks_repl_context import get_context
current_workspace = get_context().workspaceId

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")

# COMMAND ----------

workspacedf = spark.sql("select * from `all_workspaces` where workspace_id='" + current_workspace + "'" )
if len(workspacedf.take(1))==0:
    dbutils.notebook.exit("The current workspace is not found in configured list of workspaces for analysis.")
display(workspacedf)
ws = (workspacedf.collect())[0]

# COMMAND ----------

from core.dbclient import SatDBClient
json_.update({'url':'https://' + ws.deployment_url, 'workspace_id': ws.workspace_id,  'clusterid':clusterid, 'cloud_type':cloud_type})  


token = ''
if cloud_type =='azure': #client secret always needed
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
    mastername = ' '
    masterpwd = ' ' # we still need to send empty user/pwd.
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
else: #lets populate master key for accounts api
    mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
    
if (json_['use_mastercreds']) is False:
    tokenscope = json_['workspace_pat_scope']
    tokenkey = f"{json_['workspace_pat_token_prefix']}-{json_['workspace_id']}"
    token = dbutils.secrets.get(tokenscope, tokenkey)
    json_.update({'token':token})

db_client = SatDBClient(json_)
token = db_client.get_temporary_oauth_token()


# COMMAND ----------

import requests

DOMAIN = ws.deployment_url
response = requests.get(
          'https://%s/api/2.0/sql/warehouses' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % token},
          json=None,
          timeout=60 
        )
        
if response.status_code == 200:
    resources = json.loads(response.text)
    found = False
    for warehouse in resources["warehouses"]:
        if warehouse["id"] == json_['sql_warehouse_id']:
            data_source_id = warehouse['id']
            found = True
            break
    else:
        dbutils.notebook.exit("The configured SQL Warehouse is not found.")            
          


# COMMAND ----------

# MAGIC %md
# MAGIC # Modify json file with the selected catalog

# COMMAND ----------


# Path to the JSON file
file_path = f'{basePath()}/dashboards/SAT_Dashboard_definition.json'

# String to search and replace
old_string = 'hive_metastore.security_analysis'
new_string = json_['analysis_schema_name']

# Read the JSON file
with open(file_path, 'r') as file:
    data = json.load(file)

# Modify the JSON by replacing the string
# Traverse the JSON object and replace the string when found
def replace_string(obj, old_str, new_str):
    if isinstance(obj, dict):
        for key in obj:
            if isinstance(obj[key], dict) or isinstance(obj[key], list):
                replace_string(obj[key], old_str, new_str)
            elif isinstance(obj[key], str):
                obj[key] = obj[key].replace(old_str, new_str)
    elif isinstance(obj, list):
        for item in obj:
            replace_string(item, old_str, new_str)

if json_['analysis_schema_name'] != 'hive_metastore.security_analysis':
    replace_string(data, old_string, new_string)

    # Write the updated JSON back to the file
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# COMMAND ----------

# MAGIC %md
# MAGIC # Delete previously created Dashboard

# COMMAND ----------

# DBTITLE 1,Check if Dashboard exists first
import requests

response = requests.get(
          'https://%s/api/2.0/lakeview/dashboards' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % token},
          timeout=60
        )

exists = True

if '[SAT] Security Analysis Tool - Assessment Results' in response.text:
    json_response = response.json()
    filtered_dashboard = [d for d in json_response['dashboards'] if d['display_name'] == '[SAT] Security Analysis Tool - Assessment Results']

    dashboard_id = filtered_dashboard[0]['dashboard_id']
    print("Dashboard already exists")
else:
    exists = False
    print("Dashboard doesn't exist yet")           


# COMMAND ----------

# DBTITLE 1,If dashboard exists delete
#Delete using the API DELETE /api/2.0/lakeview/dashboards/

if exists != False:

  response = requests.delete(
            'https://%s/api/2.0/lakeview/dashboards/%s' % (DOMAIN, dashboard_id),
            headers={'Authorization': 'Bearer %s' % token},
            timeout=60
          )


# COMMAND ----------

# MAGIC %md
# MAGIC # Create Dashboard from json definition

# COMMAND ----------

# DBTITLE 1,Create new version of dashboard
import requests
json_file_path = f"{basePath()}/dashboards/SAT_Dashboard_definition.json"

# Read the JSON file as a string
with open(json_file_path) as json_file:
    json_data = json.load(json_file)

json_string = json_string = json.dumps(json_data)

BODY = {'display_name': '[SAT] Security Analysis Tool - Assessment Results','warehouse_id': json_['sql_warehouse_id'], 'serialized_dashboard': json_string, 'parent_path': f"{basePath()}/dashboards"}

response = requests.post(
          'https://%s/api/2.0/lakeview/dashboards' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % token},
          json=BODY,
          timeout=60
        )

exists = False

if 'RESOURCE_ALREADY_EXISTS' not in response.text:
    json_response = response.json()
    dashboard_id = json_response['dashboard_id']
    serialized_dashboard = json_response['serialized_dashboard']
else:
    exists = True
    print("Lakeview Dashboard already exists")  

# COMMAND ----------

# MAGIC %md
# MAGIC # Publish the Dashboard using the SAT warehouse

# COMMAND ----------

import requests
import json

if exists != True:

    URL = "https://"+DOMAIN+"/api/2.0/lakeview/dashboards/"+dashboard_id+"/published"
    BODY = {'embed_credentials': 'true', 'warehouse_id': json_['sql_warehouse_id']}

    response = requests.post(
            URL,
            headers={'Authorization': 'Bearer %s' % token},
            json=BODY,
            timeout=60
            )

else:
    print("Dashboard already exists")

# COMMAND ----------

dbutils.notebook.exit('OK')