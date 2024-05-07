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

import json
#Get current workspace id
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']
print(current_workspace)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope

# COMMAND ----------

try:
   dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='gs-path-to-json')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='impersonate-service-account')
   tokenkey = f"{json_['workspace_pat_token_prefix']}-{current_workspace}"
   dbutils.secrets.get(scope=json_['master_name_scope'], key=tokenkey)
   print("Your SAT configuration has required secret names")
except Exception as e:
   dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  

# COMMAND ----------

# MAGIC %md
# MAGIC ### Validate the following Values and make sure they are correct

# COMMAND ----------

sat_scope = json_['master_name_scope']

for key in dbutils.secrets.list(sat_scope):
    if key.key == tokenkey or not key.key.startswith("sat-token-"): 
        print(key.key)
        secretvalue = dbutils.secrets.get(scope=sat_scope, key=key.key)
        print(" ".join(secretvalue))


# COMMAND ----------

# MAGIC %md
# MAGIC ### Check to see if the PAT token is valid

# COMMAND ----------

import requests,json

access_token = dbutils.secrets.get(scope=json_['master_name_scope'], key=tokenkey)

# Define the URL and headers
workspaceUrl = json.loads(dbutils.notebook.entry_point.getDbutils().notebook() \
  .getContext().toJson())['tags']['browserHostName']


url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {access_token}'
}

# Make the GET request
response = requests.get(url, headers=headers)

# Print the response
print(response.json())


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
DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
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
# MAGIC curl -X GET --header 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImEzYjc2MmY4NzFjZGIzYmFlMDA0NGM2NDk2MjJmYzEzOTZlZGEzZTMiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOiJodHRwczovL2FjY291bnRzLmdjcC5kYXRhYnJpY2tzLmNvbSIsImF6cCI6IjEwMzA2NDAxNzI0ODg1NDIyMjkwNiIsImVtYWlsIjoiYXJ1bi1zYS0yQGZlLWRldi1zYW5kYm94LmlhbS5nc2VydmljZWFjY291bnQuY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsImV4cCI6MTcxNTExOTMxNSwiaWF0IjoxNzE1MTE1NzE1LCJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJzdWIiOiIxMDMwNjQwMTcyNDg4NTQyMjI5MDYifQ.T8PlFibpIFAHVYjInmnRL3_InknK_Z4ZAit0TPgTLwl_EsBW3O9dRqco07diDcbQUVK2uqZSZMte0y6vY-7e3BE_ouTt17zcMIohCJFUhSyFVpc5pgMy3VYW5MoK-yio04bQ_vl00myO7EDiXyYsdqdK0iNXDjCa6KN2e8wqEPL8K5KmbYnP6nL7wM0_SHcvW7ahS6aEGow49BoJNG784dQhVeOTLwweQmCddElmmJMnbBfDCRjzuZqtLnWVK4cWKCIQ7Pm7ngPHaTCZfNJZXea8R4Q2s5zQGwTxhQqc1CUQQ4qDTyJhTAIMLYdRIl99x4NrZQ7uvuqISA5ZgoAG6g' --header 'X-Databricks-GCP-SA-Access-Token: ya29.c.c0AY_VpZifjXLsML6GXMLhSEO9YX8sh6g34Vmd88lEG1wwuqQVy1YJETExjfIjC1Khg_pFCHKtDx_Ps36gqEDwyVWsJmN_AZcOJQ-iXtg8_6etiywyMGuTdjp3KoxfwiEDZLjfQVfqu9I0fvkT6zfdB4b_2orX0Y2LEZzrT4rspTem9u6n2txMTR3u7IFLGe6EB0xAJbwEPPoLV9vwokBRyMBjYKU00BfRWIRS5pLXCR01M1SVgEq8Dt0b4pgYtfbJI7_DPTKl4AeePZPUd9QQLBes747GHkr2vhkUvxDBbVs0dSiNHSx9wnVPv0Ob4CDgLAWZtYEcxJud3WAlj_rHk54ysiXYfuTorwkfLB1a1cxOR6l-gAY8Wg0EXee_qJ_1y_O_o9Yp1Z0JXbk3un_XxRut_5A8fRp3iGHttsenICn19xtcbHwjCOcBL_pk2BbtGYcFFB_vnb-LJzkjBk8Vx4OQweb5LTdEOajYdFH8fBnDP4o_eSSZ9ntIuXOQM0eklSo17kxlCb9hRvbJiWzSQpZQtNHBhbpZW8_fFvpe_HOwVADuqTxeJoPgXUc6HRGC-CXa77R7jaw3-ws-AjN6hqsYRlN7-x2cDGYXK3ocw7YD-dHFgmD9_AN639KwW67_Fm25sO0Q6oU8BsbQhvO_cyYlSu_vvwzgd6zh1OaY3uMkcQwxwW1pQpqddnW44iwmgRrgRU6Iy6d1OQXMZ_3kmqXwpqhz9nfj-uI8giqzIR-vsOxpIzziYnb6Sh-jeIOsx2bW1z_1Zxjz0JuWlBqzWw_ukbxuUXxO-f9fudu8e3c04F9z4RuiIO8u3-axopM92wYmbllWbmipe96XkgdIbIacut4vz7Sug_3quhn155q7r41xlBulejfRM-gr348yiXflVunxqeUplI5ROWb8vix1tnxYiyge4RSz_7gbBsdzwQMtiwd5uV7Ifamal-Q0rFxjtdjjBbjui0vFa_mFyUjvctjOmZapaRbW_0MoUZdOd3nrxdsjlrd' https://accounts.gcp.databricks.com/api/2.0/accounts/e11e38c5-a449-47b9-b37f-0fa36c821612/workspaces

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

access_token = dbutils.secrets.get(scope=json_['master_name_scope'], key=tokenkey)

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
# MAGIC curl -X GET --header 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImEzYjc2MmY4NzFjZGIzYmFlMDA0NGM2NDk2MjJmYzEzOTZlZGEzZTMiLCJ0eXAiOiJKV1QifQ.eyJhdWQiOiJodHRwczovLzg1Nzc2Mzg4MjgxNDQ4MzguOC5nY3AuZGF0YWJyaWNrcy5jb20iLCJhenAiOiIxMDMwNjQwMTcyNDg4NTQyMjI5MDYiLCJlbWFpbCI6ImFydW4tc2EtMkBmZS1kZXYtc2FuZGJveC5pYW0uZ3NlcnZpY2VhY2NvdW50LmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJleHAiOjE3MTUxMjAzNDEsImlhdCI6MTcxNTExNjc0MSwiaXNzIjoiaHR0cHM6Ly9hY2NvdW50cy5nb29nbGUuY29tIiwic3ViIjoiMTAzMDY0MDE3MjQ4ODU0MjIyOTA2In0.ZFa-L5efUAj-Z4OLb-AI5VU3Esh3GHJI9jTZHrep6q98PrWmrM7v7-sAiPN9d8ssk9rwHFVdxNsoxKbPU3Z43KbSHMsqKKh3nMqsfURcAq20xGSsahX4-XuerbzS8gmuhxfhKEh6UzSHpk7gjrXtvD3ICxPFVA27SYeE4J3dtstdF7PBTiNolCyQH0kVFHz2krge8tGsw3HzOVNIGIIBPcuijTs2gt-5vU1pijrHuup1bTM2fqxHwqwpqfb8mbAR0BQjGshgKzNVK7eTh4x-6Fm3clvdm8YQC_k9wiLbZZxI8Xh91cRLsZo4zfZetM3lYveETF0glefhpDL6oqrkSA' 'https://8577638828144838.8.gcp.databricks.com/api/2.0/clusters/list'

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
