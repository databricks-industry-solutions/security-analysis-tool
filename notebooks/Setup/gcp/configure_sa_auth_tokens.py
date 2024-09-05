# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** configure_sa_auth_tokens  
# MAGIC **Functionality:** generates and saves the temp authorization tokens for gcp service account 

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

master_name_scope = json_["master_name_scope"] 
master_name_key = json_["master_name_key"] 

master_pwd_scope = json_["master_pwd_scope"] 
master_pwd_key = json_["master_pwd_key"] 

secret_scope_initial_manage_principal ='users'
account_id = json_["account_id"] 


hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
gcp_accounts_url = 'https://accounts.'+cloud_type+'.databricks.com'
loggr.info(f" GCP account URL: {gcp_accounts_url}")

# COMMAND ----------

from google.oauth2 import service_account
import gcsfs
import json
target_scopes = [gcp_accounts_url]

# Reading gcs files with gcsfs
gcs_file_system = gcsfs.GCSFileSystem(project="gcp_project_name")
gcs_json_path = cred_file_path
with gcs_file_system.open(gcs_json_path) as f:
  json_dict = json.load(f)
  key = json.dumps(json_dict) 
    
source_credentials = (service_account.Credentials.from_service_account_info(json_dict,scopes=target_scopes))
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

target_credentials = impersonated_credentials.Credentials(
  source_credentials=source_credentials,
  target_principal=target_principal,
  target_scopes = target_scopes,
  lifetime=36000)

creds = impersonated_credentials.IDTokenCredentials(
                                  target_credentials,
                                  target_audience=gcp_accounts_url,
                                  include_email=True)

url = gcp_accounts_url+'/api/2.0/accounts/'+account_id+'/workspaces'

authed_session = AuthorizedSession(creds)

# make authenticated request and print the response, status_code
resp = authed_session.get(url)
identity_token = creds.token


# COMMAND ----------

from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

import gcsfs
import json
target_scopes = [gcp_accounts_url]

# Reading gcs files with gcsfs
gcs_file_system = gcsfs.GCSFileSystem(project="gcp_project_name")
gcs_json_path = cred_file_path
with gcs_file_system.open(gcs_json_path) as f:
  json_dict = json.load(f)
  key = json.dumps(json_dict) 

source_credentials = service_account.Credentials.from_service_account_info(json_dict, scopes = ['https://www.googleapis.com/auth/cloud-platform'],)

target_credentials = impersonated_credentials.Credentials(
  source_credentials=source_credentials,
  target_principal=target_principal,
  target_scopes = ['https://www.googleapis.com/auth/cloud-platform'],
  lifetime=3600)

import google.auth.transport.requests
request = google.auth.transport.requests.Request()
target_credentials.refresh(request)
access_token = target_credentials.token


# COMMAND ----------

import requests

response = requests.get(
  '%s/api/2.0/accounts/%s/workspaces' % (gcp_accounts_url,account_id),
  headers={'Authorization': 'Bearer %s' % identity_token, 'X-Databricks-GCP-SA-Access-Token': '%s' % access_token},
  json=None,
  timeout=60
)
loggr.info(response)

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

def storeTokenAsSecret(deployment_url, scope, key, PAT_token, token):
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
      '%s/api/2.0/secrets/put' % (deployment_url),
      headers={'Authorization': 'Bearer %s' % PAT_token},
      json={ "scope": scope,
              "key": key,
              "string_value": token 
           },
      timeout=60
    )

    if response.status_code == 200:
      loggr.info(f"Token is successfuly stored in secrets: {response}!")
    else:
      loggr.info(f"Error storing secrets: {response}")   




# COMMAND ----------

if gcp_workspace_url is None or identity_token is None or access_token is None:
    dbutils.notebook.exit("Failed to create the necessary tokens, please check your Service key file and the Impersonation service account ")

ws_temp_token = generateGCPWSToken(gcp_workspace_url ,dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json'),dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account'))


if gcp_workspace_url:
    if identity_token:
        loggr.info(f"Storing identity token :- scope:{master_name_scope}, key:{master_name_key}, on workpace:{gcp_workspace_url}")
        storeTokenAsSecret(gcp_workspace_url,master_name_scope, master_name_key,ws_temp_token,identity_token)

    if access_token:
         loggr.info(f"Storing identity token :- scope:{master_pwd_scope}, key:{master_pwd_key}, on workpace:{gcp_workspace_url}")          
         storeTokenAsSecret(gcp_workspace_url,master_pwd_scope, master_pwd_key,ws_temp_token,access_token)

# COMMAND ----------

dbutils.notebook.exit('OK')
