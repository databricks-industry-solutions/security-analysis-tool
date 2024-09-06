# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** sat_diagnosis_azure 
# MAGIC
# MAGIC **Functionality:** Diagnose account and workspace connections for azure and writes workspaces that can be connected with status into the config file

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

# COMMAND ----------

# MAGIC %md
# MAGIC ### Let us check if there are required configs in the SAT scope

# COMMAND ----------


try:
   dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='sql-warehouse-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='subscription-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='tenant-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret')
   dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
   print("Your SAT configuration has required secret names")
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

# MAGIC %md
# MAGIC ### Check to see if the access tokens are successfully created

# COMMAND ----------

import msal

# Define Azure AD constants
TENANT_ID = dbutils.secrets.get(scope=sat_scope, key="tenant-id")
CLIENT_ID = dbutils.secrets.get(scope=sat_scope, key="client-id")  # This might be your application/client ID if you registered one for your app
AUTHORITY = "https://login.microsoftonline.com/" + TENANT_ID

# Initialize MSAL client
app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=AUTHORITY,
    client_credential=(dbutils.secrets.get(scope=sat_scope, key="client-secret"))
)

# Acquire token for managed identity
scopes = [ '2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default' ]  # Scope required for accessing Azure resources
result = app.acquire_token_for_client(scopes=scopes)

if "access_token" in result:
    access_token = result["access_token"]  # This is your access token
    print("Access token:", access_token)
else:
    print(result.get("error"))
    print(result.get("error_description"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Check to see if the tokens can be used to access workspace API

# COMMAND ----------

import requests


# Define the URL and headers
workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')


url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {access_token}'
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
# MAGIC #curl --header 'Authorization: Bearer <access token>' -X GET 'https://<yourworkspace url>.azuredatabricks.net/api/2.0/clusters/spark-versions'

# COMMAND ----------

# MAGIC %sh 
# MAGIC #optional
# MAGIC #curl -v -H 'Authorization: Bearer <token>'   -H 'x-databricks-account-console-api-version: 2.0' 'https://accounts.azuredatabricks.net/api/2.0/accounts/<account_console_id>/scim/v2/Users?startIndex=1&count=10'
# MAGIC
# MAGIC

# COMMAND ----------

import requests

# Define the URL and headers
DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
url = f'https://accounts.azuredatabricks.net/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}/workspaces'

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


#Make sure to populate 
# pip install msal
import msal
import sys
def get_msal_token():
    """
    validate client id and secret from microsoft and google
    """
    # Define Azure AD constants
    TENANT_ID = dbutils.secrets.get(scope=sat_scope, key="tenant-id")
    CLIENT_ID = dbutils.secrets.get(scope=sat_scope, key="client-id")  # This might be your application/client ID if you registered one for your app
    try:
        app = msal.ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=(dbutils.secrets.get(scope=sat_scope, key="client-secret")),
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        )
        # call for default scope in order to verify client id and secret.
        scopes = [ 'https://management.azure.com/.default' ]
        # The pattern to acquire a token looks like this.
        token = None
        # Firstly, looks up a token from cache
        # Since we are looking for token for the current app, NOT for an end user,
        # notice we give account parameter as None.
        token = app.acquire_token_silent(scopes=scopes, account=None)
        if not token:
            token = app.acquire_token_for_client(scopes=scopes)
        
        print(token)
        if token.get("access_token") is None:
            print(['no token'])
        else:
            print(token.get("access_token"))
    except Exception as error:
        print(f"Exception {error}")
        print(str(error))


# COMMAND ----------

get_msal_token()

# COMMAND ----------

# MAGIC %md
# MAGIC ##Put MSAL access_token from above output and replace "blahblahblah" below and replace the <sbuscription_id> with your sbuscription_id

# COMMAND ----------

# MAGIC %sh 
# MAGIC #curl -X GET 'https://management.azure.com/subscriptions/<sbuscription_id>/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01' -H "Accept: application/json" -H "Authorization: Bearer blah"
# MAGIC

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

openssl_connect('accounts.azuredatabricks.net', 443)
