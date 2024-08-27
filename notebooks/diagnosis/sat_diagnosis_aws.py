# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** sat_diagnosis_aws  
# MAGIC **Functionality:** Diagnose account and workspace connections for aws workspaces

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

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
      print('Your SAT configuration has the required scope name')
      found=True
      break
if not found:
   dbutils.notebook.exit('Your SAT configuration is missing required scope, please review setup instructions"')

      

# COMMAND ----------

import json
#Get current workspace id
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope

# COMMAND ----------


try:
   dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='use-sp-auth')
   dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
   print("Your SAT configuration is has required secret names")
except Exception as e:
   dbutils.notebook.exit(f'Your SAT configuration is missing required secret, please review setup instructions {e}')  

# COMMAND ----------

# MAGIC %md
# MAGIC ### Validate the following values and make sure they are correct

# COMMAND ----------

sat_scope = json_['master_name_scope']

for key in dbutils.secrets.list(sat_scope):
    print(key.key)
    secretvalue = dbutils.secrets.get(scope=sat_scope, key=key.key)
    print(" ".join(secretvalue))


# COMMAND ----------

# Define the URL and headers
workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')

import requests

def getAWSTokenwithOAuth(source, baccount, client_id, client_secret):
        '''generates OAuth token for Service Principal authentication flow'''
        '''baccount if generating for account. False for workspace'''
        response = None
        user_pass = (client_id,client_secret)
        oidc_token = {
            "User-Agent": "databricks-sat/0.1.0"
        }
        json_params = {
            "grant_type": "client_credentials",
            "scope": "all-apis"
        }
              
        if baccount is True:
            full_endpoint = f"https://accounts.cloud.databricks.com/oidc/accounts/{source}/v1/token" #url for accounts api  
        else: #workspace
            full_endpoint = f'https://{source}/oidc/v1/token'

        response = requests.post(full_endpoint, headers=oidc_token,
                                    auth=user_pass, data=json_params, timeout=60)  

        if response is not None and response.status_code == 200:
            return response.json()['access_token']
        display(json.dumps(response.json()))
        return None


# COMMAND ----------

# MAGIC %md
# MAGIC ### Check to see if the SP client_id and cleint_secret are valid

# COMMAND ----------

token = getAWSTokenwithOAuth(workspaceUrl,False, dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id'), dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret'))
                             
print(token)

# COMMAND ----------

import requests


# Define the URL and headers
workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')


url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {token}'
}

# Make the GET request
response = requests.get(url, headers=headers)

# Print the response
print(response.json())


# COMMAND ----------

import requests



# Define the URL and headers
workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')


url = f'https://{workspaceUrl}/api/2.1/unity-catalog/models'
headers = {
    'Authorization': f'Bearer {token}'
}

# Make the GET request
response = requests.get(url, headers=headers)

# Print the response
print(response.json())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Additional validation   - Execute the curl command to check the token is able to access the workspace.

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl --header 'Authorization: Bearer <token>' -X GET 'https://<workspace>.cloud.databricks.com/api/2.0/clusters/spark-versions'

# COMMAND ----------

access_token = getAWSTokenwithOAuth(dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id'),True, dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id'), dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret'))
                             
print(access_token)

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl -v -H 'Authorization: Bearer <toke>'  'https://accounts.cloud.databricks.com/api/2.0/accounts/<account_console_id>/workspaces'
# MAGIC
# MAGIC

# COMMAND ----------

import requests

# Define the URL and headers
DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
url = f'https://accounts.cloud.databricks.com/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}/workspaces'

## Note: The access token should be generated for a SP which is an account admin to run this command.  

headers = {
     'Authorization': f'Bearer {access_token}' 
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
workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')

openssl_connect(workspaceUrl, 443)



# COMMAND ----------

openssl_connect('accounts.cloud.databricks.com', 443)
