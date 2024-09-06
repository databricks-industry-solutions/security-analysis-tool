# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 5. import_dashboard_template.      
# MAGIC **Functionality:** Imports dashboard template from code repo into Dashboards section for SAT report.  

# COMMAND ----------

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

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
clusterid = spark.conf.get("spark.databricks.clusterUsageTags.clusterId")

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
loggr.info(f"Looking for data_source_id for : {json_['sql_warehouse_id']}!")
response = requests.get(
          'https://%s/api/2.0/preview/sql/data_sources' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % token},
          json=None,
          timeout=60 
        )
if response.status_code == 200:
    resources = json.loads(response.text)
    found = False
    for resource in resources:
        if resource['endpoint_id'] == json_['sql_warehouse_id']:
            data_source_id = resource['id']
            loggr.info(f"Found data_source_id for : {json_['sql_warehouse_id']}!") 
            found = True
            break
    if (found == False):
        dbutils.notebook.exit("The configured SQL Warehouse Endpoint is not found.")    
else:
    loggr.info(f"Error with token, {response.text}")    
    dbutils.notebook.exit("Invalid access token, check configuration value for this workspace.")            


# COMMAND ----------

#todo: Add parent folder to all SQL assets, expose name in _json (default SAT)
#create a folder to house all SAT sql artifacts
import requests
from core.dbclient import SatDBClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
session = requests.Session()
retry = Retry(connect=10, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

def create_ws_folder(ws, dir_name):
    #delete tthe WS folder if it exists
    delete_ws_folder(ws, dir_name)
    url = "https://"+ ws.deployment_url
    headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
    path = "/Users/"+context['tags']['user']+"/"+ dir_name
    body = {"path":  path}
    target_url = url + "/api/2.0/workspace/mkdirs"
    
    loggr.info(f"Creating {path} using {target_url}")
    session.post(target_url, headers=headers, json=body,timeout=60).json()
    
    target_url = url + "/api/2.0/workspace/get-status"
    loggr.info(f"Get Status {path} using {target_url}")
    response=requests.get(target_url, headers=headers, json=body, timeout=60).json()    
    loggr.info(response)
    return response['object_id']


#delete folder that houses all SAT sql artifacts
def get_ws_folder_object_id(ws, dir_name):
    
    #Use the workspace list API to get the object_id for the folder you want to use. 
    #Here’s an example for how to get it for a folder called “/Users/me@example.com”:
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
    url = "https://"+ ws.deployment_url
    headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
    path = "/Users/"+context['tags']['user']+"/"+ dir_name
    body = {"path":  path, "recursive": True}
    target_url = url + "/api/2.0/workspace/delete"
    loggr.info(f"Creating {path} using {target_url}")
    
    session.post(target_url, headers=headers, json=body, timeout=60).json()
    loggr.info(f"Dir {dir_name} deleted")
    


# COMMAND ----------

folder_id = create_ws_folder(ws, 'SAT_dashboard')

# COMMAND ----------

class Client():
    def __init__(self, url, token,  endpoint_id, data_source_id, dashboard_tags = None):
        self.url = "https://"+url
        self.headers = {"Authorization": "Bearer " + token, 'Content-type': 'application/json'}
        permissions = "[{\"group_name\": \"users\",\"permission_level\": \"CAN_RUN\"},{\"group_name\": \"admins\",\"permission_level\": \"CAN_MANAGE\"}]"
        self.permissions = {"access_control_list": permissions}
        self.data_source_id = data_source_id
        self.endpoint_id = endpoint_id
        self.dashboard_tags = dashboard_tags
        
    def permisions_defined(self):
        return self.permissions is not None and len(self.permissions["access_control_list"]) > 0

# COMMAND ----------

def get_client(workspace,pat_token):
    client = Client(workspace.deployment_url, pat_token, json_['sql_warehouse_id'], data_source_id, json_['dashboard_tag'])
    return  client, json_['dashboard_id'],  json_['dashboard_folder']


# COMMAND ----------

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
session = requests.Session()
retry = Retry(connect=10, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)


def clone_dashboard(dashboard, target_client: Client, dashboard_state):
    if "queries" not in dashboard_state:
        dashboard_state["queries"] = {}

    for q in dashboard["queries"]:
        #We need to replace the param queries with the newly created one
        if "parameters" in q["options"]:
            for p in q["options"]["parameters"]:
                if "queryId" in p:
                    p["queryId"] = dashboard_state["queries"][p["queryId"]]["new_id"]
                    if "parentQueryId" in p:
                        del p["parentQueryId"]
                    del p["value"]
        new_query = clone_or_update_query(dashboard_state, q, target_client)
        loggr.info("new_query=", new_query)
        if target_client.permisions_defined():
            permissions = session.post(target_client.url+"/api/2.0/preview/sql/permissions/queries/"+new_query["id"], headers = target_client.headers, json=target_client.permissions,timeout=60).json()
            loggr.info(f"     Permissions set to {permissions}")

        visualizations = clone_query_visualization(target_client, q, new_query)
        dashboard_state["queries"][q["id"]] = {"new_id": new_query["id"], "visualizations": visualizations}
    duplicate_dashboard(target_client, dashboard["dashboard"], dashboard_state)
    return dashboard_state

def clone_or_update_query(dashboard_state, q, target_client):
    q_creation = {
        "data_source_id": target_client.data_source_id,
        "query": q["query"].replace('security_analysis',json_["analysis_schema_name"]),
        "name": q["name"],
        "description": q["description"],
        "schedule": q["schedule"],
        "tags": q["tags"],
        "options": q["options"],
        "parent":"folders/"+str(folder_id)
    }
    new_query = None
    if q['id'] in dashboard_state["queries"]:
        existing_query_id = dashboard_state["queries"][q['id']]["new_id"]
        # check if the query still exists (it might have been manually deleted by mistake)
        existing_query = requests.get(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                      headers=target_client.headers, timeout=60).json()
        if 'id' in existing_query and 'moved_to_trash_at' not in existing_query:
            loggr.info(f"     updating the existing query {existing_query_id}")
            new_query = session.post(target_client.url + "/api/2.0/preview/sql/queries/" + existing_query_id,
                                      headers=target_client.headers, json=q_creation, timeout=60).json()
            # Delete all query visualization to reset its settings
            for v in new_query["visualizations"]:
                loggr.info(f"     deleting query visualization {v['id']}")
                requests.delete(target_client.url + "/api/2.0/preview/sql/visualizations/" + v["id"],
                                headers=target_client.headers,timeout=60).json()
    if not new_query:
        loggr.info(f"     cloning query {q_creation}...")
        new_query = session.post(target_client.url + "/api/2.0/preview/sql/queries", headers=target_client.headers,
                                  json=q_creation,timeout=60).json()
    return new_query

def clone_query_visualization(client: Client, query, target_query):
    # Sort both lists to retain visualization order on the query screen
    def get_first_vis(q):
        orig_table_visualizations = sorted(
            [i for i in q["visualizations"] if i["type"] == "TABLE"],
            key=lambda x: x["id"],
        )
        if len(orig_table_visualizations) > 0:
            return orig_table_visualizations[0]
        return None
    #Update the default(first) visualization to match the existing one:
    # Sort this table like orig_table_visualizations.
    # The first elements in these lists should mirror one another.
    orig_default_table = get_first_vis(query)
    mapping = {}
    if orig_default_table:
        target_default_table = get_first_vis(target_query)
        default_table_viz_data = {
            "name": orig_default_table["name"],
            "description": orig_default_table["description"],
            "options": orig_default_table["options"]
        }
        if target_default_table is not None:
            mapping[orig_default_table["id"]] = target_default_table["id"]
        loggr.info(f"         updating default Viz {target_default_table['id']}...")
        session.post(client.url+"/api/2.0/preview/sql/visualizations/"+target_default_table["id"], headers = client.headers, json=default_table_viz_data,timeout=60)
    #Then create the other visualizations
    for v in sorted(query["visualizations"], key=lambda x: x["id"]):
        loggr.info(v)
        data = {
            "name": v["name"],
            "description": v["description"],
            "options": v["options"],
            "type": v["type"],
            "query_plan": v["query_plan"],
            "query_id": target_query["id"]
        }
        new_v = session.post(client.url+"/api/2.0/preview/sql/visualizations", headers = client.headers, json=data,timeout=60).json()
        mapping[v["id"]] = new_v["id"]
    return mapping

def duplicate_dashboard(client: Client, dashboard, dashboard_state):
    data = {"name": dashboard["name"], "tags": dashboard["tags"],"parent":"folders/"+str(folder_id) }
    new_dashboard = None
    if "new_id" in dashboard_state:
        existing_dashboard = requests.get(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers,timeout=60).json()
        if "options" in existing_dashboard and "moved_to_trash_at" not in existing_dashboard["options"]:
            loggr.info("  dashboard exists, updating it")
            new_dashboard = requests.post(client.url+"/api/2.0/preview/sql/dashboards/"+dashboard_state["new_id"], headers = client.headers, json=data,timeout=60).json()
            #Drop all the widgets and re-create them
            for widget in new_dashboard["widgets"]:
                loggr.info(f"    deleting widget {widget['id']} from existing dashboard {new_dashboard['id']}")
                requests.delete(client.url+"/api/2.0/preview/sql/widgets/"+widget['id'], headers = client.headers, timeout=60).json()
        else:
            loggr.info("    couldn't find the dashboard defined in the state, it probably has been deleted.")
    if new_dashboard is None:
        loggr.info(f"  creating new dashboard...")
        new_dashboard = session.post(client.url+"/api/2.0/preview/sql/dashboards", headers = client.headers, json=data,timeout=60).json()
        dashboard_state["new_id"] = new_dashboard["id"]
    if client.permisions_defined():
        permissions = session.post(client.url+"/api/2.0/preview/sql/permissions/dashboards/"+new_dashboard["id"], headers = client.headers, json=client.permissions,timeout=60).json()
        loggr.info(f"     Dashboard permissions set to {permissions}")
    for widget in dashboard["widgets"]:
        loggr.info(f"          cloning widget {widget}...")
        visualization_id_clone = None
        if "visualization" in widget:
            query_id = widget["visualization"]["query"]["id"]
            visualization_id = widget["visualization"]["id"]
            visualization_id_clone = dashboard_state["queries"][query_id]["visualizations"][visualization_id]
        data = {
            "dashboard_id": new_dashboard["id"],
            "visualization_id": visualization_id_clone,
            "text": widget["text"],
            "options": widget["options"],
            "width": widget["width"]
        }
        session.post(client.url+"/api/2.0/preview/sql/widgets", headers = client.headers, json=data, timeout=60).json()

    return new_dashboard

# COMMAND ----------

def load_dashboard(target_client: Client, dashboard_id, dashboard_state, folder_prefix="./dashboards/"):
    if not folder_prefix.endswith("/"):
        folder_prefix += "/"
    with open(f'{folder_prefix}dashboard-{dashboard_id}.json', 'r') as r:
        dashboard = json.loads(r.read())
        dashboard_state = clone_dashboard(dashboard, target_client, dashboard_state)
        return dashboard_id, dashboard_state

# COMMAND ----------

from core.dbclient import SatDBClient
target_client, dashboard_id_to_load,dashboard_folder  = get_client(ws, token)
workspace_state = {}
loggr.info(f"Loading dashboard to master workspace {ws.workspace_id} from dashboard folder {dashboard_folder}")
load_dashboard(target_client, dashboard_id_to_load,  workspace_state, dashboard_folder)

# COMMAND ----------

dbutils.notebook.exit('OK')
