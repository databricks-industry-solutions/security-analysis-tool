# Databricks notebook source
# MAGIC %run ../../Includes/install_sat_sdk

# COMMAND ----------

pip install --upgrade google-auth

# COMMAND ----------

# MAGIC %run ../../Utils/initialize

# COMMAND ----------

# MAGIC %run ../../Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

dbutils.widgets.text("cred_file_path", "", "a. Service account key file path")
dbutils.widgets.text("target_principal", "", "b. Impersonation service account")


# COMMAND ----------

import json
#Get current workspace id
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

cred_file_path = dbutils.widgets.get("cred_file_path")
target_principal = dbutils.widgets.get("target_principal")
loggr.info(f" Service account key file path {cred_file_path}")
loggr.info(f" Impersonation service account {target_principal}")
if cred_file_path is None or target_principal is None:
    dbutils.notebook.exit("Please set values for : Service account key file path, Impersonation service account, Generate Long term PAT tokens")

workspace_pat_scope = json_['workspace_pat_scope']
tokenscope = json_['workspace_pat_token_prefix']
ws_pat_token = dbutils.secrets.get(workspace_pat_scope, tokenscope+"_"+current_workspace)
#cred_file_path= '/dbfs/FileStore/tables/SA_1_key.json'
#target_principal='arun-sa-2@fe-dev-sandbox.iam.gserviceaccount.com'
#ws_pat_token="dapic5a1740b147488a3ceb3c3625310a47f"

master_name_scope = json_["master_name_scope"] 
master_name_key = json_["master_name_key"] 

master_pwd_scope = json_["master_pwd_scope"] 
master_pwd_key = json_["master_pwd_key"] 

secret_scope_initial_manage_principal ='users'
account_id = json_["account_id"] 


hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
gcp_accounts_url = 'https://accounts.'+cloud_type+'.databricks.com'

# COMMAND ----------

from google.oauth2 import service_account
target_scopes = [gcp_accounts_url]
source_credentials = (service_account.Credentials.from_service_account_file(cred_file_path,scopes=target_scopes))
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

source_credentials = service_account.Credentials.from_service_account_file(cred_file_path, scopes = ['https://www.googleapis.com/auth/cloud-platform'],)

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
  json=None
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

def storeTokenAsSecret(deployment_url, scope, key, PAT_token, token):
    import requests
    

    response = requests.post(
      '%s/api/2.0/secrets/put' % (deployment_url),
      headers={'Authorization': 'Bearer %s' % PAT_token},
      json={ "scope": scope,
              "key": key,
              "string_value": token 
           }
    )

    if response.status_code == 200:
      loggr.info(f"Token is successfuly stored in secrets: {response.json()}!")
    else:
      loggr.info(f"Error storing secrets: {response}")   




# COMMAND ----------

if gcp_workspace_url is None or identity_token is None or access_token is None:
    dbutils.notebook.exit("Failed to create the necessary tokens, please check your Service key file and the Impersonation service account ")


if gcp_workspace_url:
    if identity_token:
        loggr.info(f"Storing identity token :- scope:{master_name_scope}, key:{master_name_key}, on workpace:{gcp_workspace_url}")
        storeTokenAsSecret(gcp_workspace_url,master_name_scope, master_name_key,ws_pat_token,identity_token)

    if access_token:
         loggr.info(f"Storing identity token :- scope:{master_pwd_scope}, key:{master_pwd_key}, on workpace:{gcp_workspace_url}")          
         storeTokenAsSecret(gcp_workspace_url,master_pwd_scope, master_pwd_key,ws_pat_token,access_token)

# COMMAND ----------

dbutils.notebook.exit('OK')
