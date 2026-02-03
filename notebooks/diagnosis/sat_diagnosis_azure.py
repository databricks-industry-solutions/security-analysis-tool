# Databricks notebook source
# MAGIC %md
# MAGIC **Functionality:** Diagnoses account-level and workspace-level connections for Databricks workspaces on Azure to ensure proper configuration and connectivity.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Widget to provide specific workspace URL for connectivity tests
# MAGIC If you need to test connectivity to specific workspaces, the following code will create a new widget to accept the workspace URL as a parameter. If this widget is left empty it connects to the current workspace (default). A sample workspace URL format is provided below.
# MAGIC
# MAGIC * adb-xxxxxxxxxxxxxxxx.x.azuredatabricks.net

# COMMAND ----------

dbutils.widgets.text("workspaceUrl", "")
userWorkspaceUrl = dbutils.widgets.get("workspaceUrl")
print("User provided workspace URL ->", userWorkspaceUrl)

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

sat_version = json_['sat_version']
print("Current SAT version ->", sat_version)

# COMMAND ----------

secret_scopes = dbutils.secrets.listScopes()
display(secret_scopes)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the required SAT scope is configured

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
# MAGIC ### Verify that the required secrets are configured in the SAT scope

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
# MAGIC ### Verify that the required secrets have the correct values

# COMMAND ----------

sat_scope = json_['master_name_scope']

for key in dbutils.secrets.list(sat_scope):
    print(key.key)
    secretvalue = dbutils.secrets.get(scope=sat_scope, key=key.key)
    print(" ".join(secretvalue))


# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the access tokens are successfully created

# COMMAND ----------

import msal

# Define Azure AD constants
TENANT_ID = dbutils.secrets.get(scope=sat_scope, key="tenant-id")
CLIENT_ID = dbutils.secrets.get(scope=sat_scope, key="client-id") 
AUTHORITY = "https://login.microsoftonline.com/" + TENANT_ID

app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=AUTHORITY,
    client_credential=(dbutils.secrets.get(scope=sat_scope, key="client-secret"))
)

# Acquire token for managed identity
scopes = [ '2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default' ]  # Scope required for accessing Azure resources
result = app.acquire_token_for_client(scopes=scopes)

if "access_token" in result:
    access_token = result["access_token"] 
    print("Access token:", access_token)
else:
    print(result.get("error"))
    print(result.get("error_description"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the tokens can be used to access the workspace

# COMMAND ----------

import requests

# Retrieve the workspace URL from the user-provided input or fallback to the default workspace URL
workspaceUrl = userWorkspaceUrl or spark.conf.get("spark.databricks.workspaceUrl")

url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {access_token}'
}

response = requests.get(url, headers=headers)

print(response.json())

# COMMAND ----------

# MAGIC %md
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the token can access the workspace

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

DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
url = f'https://accounts.azuredatabricks.net/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}/workspaces'

## Note: The access token must be generated for a Service Principal that has account admin privileges to run this command.  

headers = {
     'Authorization': f'Bearer {access_token}' 
}

try:
    response = requests.get(url, headers=headers)

    response.raise_for_status()

    print(response.json())
    
except requests.exceptions.RequestException as err:
    print(f"An error occurred: {err}")

# COMMAND ----------

# pip install msal
import msal
import sys
def get_msal_token():
    """
    validate client id and secret from microsoft and google
    """
    # Define Azure AD constants
    TENANT_ID = dbutils.secrets.get(scope=sat_scope, key="tenant-id")
    CLIENT_ID = dbutils.secrets.get(scope=sat_scope, key="client-id") 
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
# MAGIC ## Verify that the MSAL access_token can be used to access the workspace

# COMMAND ----------

# MAGIC %sh 
# MAGIC #curl -X GET 'https://management.azure.com/subscriptions/<subscription_id>/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01' -H "Accept: application/json" -H "Authorization: Bearer token"
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ### Test Connectivity to Workspace URL and Account Console 

# COMMAND ----------

import subprocess

def openssl_connect(host, port):
    openssl_command = [
        'openssl', 's_client', '-connect', f'{host}:{port}'
    ]

    process = subprocess.Popen(openssl_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    output, error = process.communicate(input=b'GET / HTTP/1.0\r\n\r\n')

    print(output.decode())

    if error:
        print("Error:", error.decode())


# COMMAND ----------

workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')

openssl_connect(workspaceUrl, 443)


# COMMAND ----------

openssl_connect('accounts.azuredatabricks.net', 443)
