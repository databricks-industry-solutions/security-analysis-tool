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

gcp_accounts_url = 'https://accounts.gcp.databricks.com'
gcp_workspace_url = '8577638828144838.8.gcp.databricks.com'
cred_file_path= '/dbfs/FileStore/tables/SA_1_key.json'
target_principal='arun-sa-2@fe-dev-sandbox.iam.gserviceaccount.com'
long_term = True

secret_scope = 'sat_scope'
secret_scope_initial_manage_principal ='users'

# COMMAND ----------

#replace values for accounts exec
mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
account_id=json_["account_id"]
#replace values for accounts exec
hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

def generatePATToken(deployment_url, tempToken):
    import requests


    response = requests.post(
      '%s/api/2.0/token/create' % (deployment_url),
      headers={'Authorization': 'Bearer %s' % tempToken},
      json={ "comment": "This is an SAT token", "lifetime_seconds": 7776000 }
    )

    if response.status_code == 200:
      loggr.info(f"PAT Token is successfuly created: {response.json()['token_value']}!")
      token_value = response.json()["token_value"] 
    else:
      loggr.info(f"Error creating alert query: {(response.json())}")   


    return token_value


# COMMAND ----------

def generateToken(deployment_url, long_term=False):
    from google.oauth2 import service_account
    target_scopes = [deployment_url]
    source_credentials = service_account.Credentials.from_service_account_file(cred_file_path,scopes=target_scopes)
    from google.auth import impersonated_credentials
    from google.auth.transport.requests import AuthorizedSession

    target_credentials = impersonated_credentials.Credentials(
      source_credentials=source_credentials,
      target_principal=target_principal,
      target_scopes = target_scopes,
      lifetime=3600)

    creds = impersonated_credentials.IDTokenCredentials(
                                      target_credentials,
                                      target_audience=deployment_url,
                                      include_email=True)

    authed_session = AuthorizedSession(creds)
    resp = authed_session.get(gcp_accounts_url)
    print(resp.status_code)
    print(resp.text)
    loggr.info(f"Short term token for {deployment_url} : {creds.token}!")
    if long_term:
        return creds.token, generatePATToken(deployment_url,creds.token)
        
    else:    
        return creds.token, creds.token
    

# COMMAND ----------

def storePATTokenAsSecret(deployment_url, workspace_id, tempToken, token):
    import requests


    response = requests.post(
      '%s/api/2.0/secrets/put' % (deployment_url),
      headers={'Authorization': 'Bearer %s' % tempToken},
      json={ "scope": secret_scope,
              "key": 'sat_token'+'_'+workspace_id,
              "string_value": token 
           }
    )

    if response.status_code == 200:
      loggr.info(f"PAT Token is successfuly stored in secrets: {response.json()}!")
    else:
      loggr.info(f"Error storing secrets: {(response.json())}")   




# COMMAND ----------

import json
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

print(current_workspace)

# COMMAND ----------

import requests

response = requests.get(
  '%s/api/2.0/accounts/%s/workspaces' % (gcp_accounts_url,account_id),
  headers={'Authorization': 'Bearer %s' % mastername, 'X-Databricks-GCP-SA-Access-Token': '%s' % masterpwd},
  json=None
)

if response.status_code == 200:
    loggr.info("Workspaces query successful!")
    workspaces = response.json()
    for ws in workspaces:
        print(ws['workspace_id'])
        if (str(ws['workspace_id']) == current_workspace):   
            deployment_url = "https://"+ ws['deployment_name']+'.'+cloud_type+'.databricks.com'
            loggr.info(f" Getting token for Workspace : {deployment_url}")
            tempToken, longTermToken = generateToken(deployment_url, long_term)
            storePATTokenAsSecret(deployment_url, str(ws['workspace_id']), tempToken, longTermToken)
else:
    loggr.info(f"Error querying workspace API. Check account tokens: {response}")   
