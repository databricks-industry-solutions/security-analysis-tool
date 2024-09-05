# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** configure_tokens_for_worksaces   
# MAGIC **Functionality:** generates and saves the temp authorization tokens for gcp service account for the workspaces

# COMMAND ----------

# MAGIC %run ../../Includes/install_sat_sdk

# COMMAND ----------

pip install --upgrade google-auth  gcsfs

# COMMAND ----------

# MAGIC %run ../../Utils/initialize

# COMMAND ----------

# MAGIC %run ../../Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

import json
#Get current workspace id
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

cred_file_path = json_["service_account_key_file_path"] 
target_principal = json_["impersonate_service_account"]
loggr.info(f" Service account key file path {cred_file_path}")
loggr.info(f" Impersonation service account {target_principal}")


if cred_file_path is None or target_principal is None:
    dbutils.notebook.exit("Please set values for : Service account key file path, Impersonation service account")


workspace_pat_scope = json_['workspace_pat_scope']
tokenscope = json_['workspace_pat_token_prefix']


workspace_id = None
try:
    workspace_id = dbutils.widgets.get('workspace_id')
except Exception:
    loggr.exception("Exception encountered")
loggr.info(f"Renewing token for workspace")

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

#replace values for accounts exec
mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
account_id=json_["account_id"]
#replace values for accounts exec
hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
gcp_accounts_url = 'https://accounts.'+cloud_type+'.databricks.com'

# COMMAND ----------

def generateToken(deployment_url):
    from google.oauth2 import service_account
    import gcsfs
    import json 
    target_scopes = [deployment_url]
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
    loggr.info(f"Short term token for {deployment_url} !")
    
    return creds.token
    

# COMMAND ----------

def storeTokenAsSecret(gcp_workspace_url, scope, key, PAT_token, token):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(connect=10, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    loggr.info(f"Storing secrets on {gcp_workspace_url}")
    response = session.post(
      '%s/api/2.0/secrets/put' % (gcp_workspace_url),
      headers={'Authorization': 'Bearer %s' % PAT_token},
      json={ "scope": scope,
              "key": key,
              "string_value": token 
           },
      timeout=600
    )

    if response.status_code == 200:
      loggr.info(f"Token is successfuly stored in secrets: {response.json()}!")
    else:
      loggr.info(f"Error storing secrets: {response}")   



# COMMAND ----------

import requests

response = requests.get(
  '%s/api/2.0/accounts/%s/workspaces' % (gcp_accounts_url,account_id),
  headers={'Authorization': 'Bearer %s' % mastername, 'X-Databricks-GCP-SA-Access-Token': '%s' % masterpwd},
  json=None,
  timeout=600
)

if response.status_code == 200:
    loggr.info("Workspaces query successful!")
    workspaces = response.json()
    for ws in workspaces:
        if str(ws['workspace_id']) == current_workspace:
            gcp_workspace_url = 'https://'+ws['deployment_name']+'.'+cloud_type+'.databricks.com'
        
else:
    loggr.info(f"Error querying workspace API. Check account tokens: {response}")   
    
loggr.info(f"Current workspace URL : {gcp_workspace_url}")   

# COMMAND ----------

import requests

response = requests.get(
  '%s/api/2.0/accounts/%s/workspaces' % (gcp_accounts_url,account_id),
  headers={'Authorization': 'Bearer %s' % mastername, 'X-Databricks-GCP-SA-Access-Token': '%s' % masterpwd},
  json=None,
  timeout=600
)
ws_temp_token = generateGCPWSToken(gcp_workspace_url ,dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json'),dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account'))
if response.status_code == 200:
    loggr.info("Workspaces query successful!")
    workspaces = response.json()
    #generate rest of the workspace tokens and store them in the secret store of the main workspace
    #Renew the token for specified workspace or all workspaces based on the workspace_id value
    for ws in workspaces:
        if((workspace_id is None and (ws['workspace_status'] == 'RUNNING')) or (workspace_id is not None and (str(ws['workspace_id']) == workspace_id))):
            deployment_url = "https://"+ ws['deployment_name']+'.'+cloud_type+'.databricks.com'
            loggr.info(f" Getting token for Workspace : {deployment_url}")
            token = generateToken(deployment_url)
            if token:
                storeTokenAsSecret(gcp_workspace_url, workspace_pat_scope, tokenscope+"-"+str(ws['workspace_id']), ws_temp_token, token)
else:
    loggr.info(f"Error querying workspace API. Check account tokens: {response}")   

# COMMAND ----------

dbutils.notebook.exit('OK')
