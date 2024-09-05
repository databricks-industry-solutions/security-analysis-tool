# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** sat_diagnosis_gcp  
# MAGIC **Functionality:** Diagnose account and workspace connections for gcp workspaces

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

pip install --upgrade google-auth  gcsfs

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

secret_scopes = dbutils.secrets.listScopes()
display(secret_scopes)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there is an SAT scope configured

# COMMAND ----------

found = False
for secret_scope in secret_scopes:
   
   if secret_scope.name == json_['master_name_scope']:
      print('Your SAT configuration is has the required scope name')
      found=True
      break
if not found:
   dbutils.notebook.exit('Your SAT configuration is missing required scope, please review setup instructions"')

      

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope

# COMMAND ----------

try:
   dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account')
   dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
   print("Your SAT configuration has required secret names")
except Exception as e:
   dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  

# COMMAND ----------

import requests,json


# Define the URL and headers
workspaceUrl = json.loads(dbutils.notebook.entry_point.getDbutils().notebook() \
  .getContext().toJson())['tags']['browserHostName']

# COMMAND ----------

# MAGIC %md
# MAGIC ### Check to see if the PAT token is valid

# COMMAND ----------

import requests,json


# Define the URL and headers
workspaceUrl = json.loads(dbutils.notebook.entry_point.getDbutils().notebook() \
  .getContext().toJson())['tags']['browserHostName']

# COMMAND ----------

gcp_accounts_url = 'https://accounts.gcp.databricks.com' 

# COMMAND ----------

from google.oauth2 import service_account
import gcsfs
import json
def getGCSIdentityToken(account_id, cred_file_path,target_principal):
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
        return identity_token

# COMMAND ----------

identity_token = getGCSIdentityToken(dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id'), dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json'),dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account'))
print(identity_token)

# COMMAND ----------

from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

import gcsfs
import json
target_scopes = [gcp_accounts_url]
def getGCSAccessToken(cred_file_path,target_principal):
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
    return access_token

# COMMAND ----------

access_token = getGCSAccessToken( dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json'),dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account'))
print(access_token)

# COMMAND ----------

import requests

# Define the URL and headers
DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=json_['master_name_scope'], key="account-console-id")
url = f'https://accounts.gcp.databricks.com/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}/workspaces'

## Note: The access token should be generated for a SP which is an account admin to run this command.  

headers = {
     'Authorization': f'Bearer {identity_token}', 
     'X-Databricks-GCP-SA-Access-Token':f'{access_token}'
}

try:
    # Make the GET request
    response = requests.get(url, headers=headers)

    # Check if the response was successful
    response.raise_for_status()

    # Print the response
    print(response.json())
    
except requests.exceptions.RequestException as err:
    print(f"An error occurred: {err}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Additional validation   - Execute the curl command to check the token is able to access the accounts console.

# COMMAND ----------

# MAGIC %sh
# MAGIC curl -X GET --header 'Authorization: Bearer <identity_token>' --header 'X-Databricks-GCP-SA-Access-Token: <access_token>' https://accounts.gcp.databricks.com/api/2.0/accounts/<accounts_console_id>/workspaces

# COMMAND ----------

def generateWSToken(deployment_url, cred_file_path,target_principal):
    from google.oauth2 import service_account
    import gcsfs
    import json 
    
    target_scopes = [deployment_url]
    print(target_scopes)
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
    return creds.token
    

# COMMAND ----------

identity_token = generateWSToken(f'https://{workspaceUrl}' ,dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json'),dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account'))
print(identity_token)

# COMMAND ----------

import requests,json


# Define the URL and headers
workspaceUrl = json.loads(dbutils.notebook.entry_point.getDbutils().notebook() \
  .getContext().toJson())['tags']['browserHostName']


url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {identity_token}'
}

# Make the GET request
response = requests.get(url, headers=headers)

# Print the response
print(response.json())


# COMMAND ----------

# MAGIC %md
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ### Additional validation   - Execute the curl command to check the token is able to access the workspace.

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl -X GET --header 'Authorization: Bearer access_token' 'https://<workspace_id>.gcp.databricks.com/api/2.0/clusters/list'

# COMMAND ----------

# MAGIC %md
# MAGIC ### Test Connectivity to Workspace URL and Account Console 

# COMMAND ----------

import subprocess

def openssl_connect(host, port):
    # Command to connect to a server using OpenSSL s_client
    openssl_command = [
        'openssl', 's_client', '-connect', f'{host}:{port}'
    ]

    # Run the OpenSSL command
    process = subprocess.Popen(openssl_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Communicate with the subprocess
    output, error = process.communicate(input=b'GET / HTTP/1.0\r\n\r\n')

    # Print the output
    print(output.decode())

    # Check if there was any error
    if error:
        print("Error:", error.decode())



# COMMAND ----------

# Example usage: connect to a server running on localhost at port 443 (HTTPS)
openssl_connect(workspaceUrl, 443)



# COMMAND ----------

openssl_connect('accounts.azuredatabricks.net', 443)
