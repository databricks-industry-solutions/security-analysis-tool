# Databricks notebook source
# MAGIC %md 
# MAGIC **Functionality:** Diagnoses account-level and workspace-level connections for Databricks workspaces on AWS to ensure proper configuration and connectivity.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Widget to provide specific workspace URL for connectivity tests
# MAGIC If you need to test connectivity to specific workspaces, the following code will create a new widget to accept the workspace URL as a parameter. If this widget is left empty it connects to the current workspace (default). A sample workspace URL format is provided below.
# MAGIC
# MAGIC * dbc-xxxxxxxx-xxxx.cloud.databricks.com

# COMMAND ----------

dbutils.widgets.text("workspaceUrl", "")
userWorkspaceUrl = dbutils.widgets.get("workspaceUrl")
print("User provided workspace URL ->", userWorkspaceUrl)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Proxy Configuration (Optional)
# MAGIC If network is behind a proxy, provide the proxy URLs below. Leave blank if not using a proxy.
# MAGIC
# MAGIC **Example formats:**
# MAGIC * `http://proxy.company.com:8080`

# COMMAND ----------

# Create proxy configuration widgets
dbutils.widgets.text("http_proxy", "", "HTTP Proxy (Optional)")
dbutils.widgets.text("https_proxy", "", "HTTPS Proxy (Optional)")

http_proxy = dbutils.widgets.get("http_proxy").strip()
https_proxy = dbutils.widgets.get("https_proxy").strip()

# Build the proxies dictionary
proxies = {}
if http_proxy:
    proxies['http'] = http_proxy
    print(f"✓ HTTP Proxy configured: {http_proxy}")
if https_proxy:
    proxies['https'] = https_proxy
    print(f"✓ HTTPS Proxy configured: {https_proxy}")

if not proxies:
    print("ℹ️  No proxy configured - using direct connection")
    
print(f"\nProxy configuration: {proxies if proxies else 'None'}")

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
      print('Your SAT configuration has the required scope name')
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
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret')
   dbutils.secrets.get(scope=json_['master_name_scope'], key='use-sp-auth')
   dbutils.secrets.get(scope=json_['master_name_scope'], key="analysis_schema_name")
   print("Your SAT configuration is has required secret names")
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
# MAGIC ## TruffleHog Secret Scanner Validation

# COMMAND ----------

import os
import subprocess

print("\n" + "="*80)
print("TRUFFLEHOG VALIDATION")
print("="*80)

# 1. Binary check
trufflehog_path = "/tmp/trufflehog"
trufflehog_installed = os.path.exists(trufflehog_path)

if trufflehog_installed:
    print(f"✅ TruffleHog installed at {trufflehog_path}")

    # Get version
    try:
        result = subprocess.run([trufflehog_path, "--version"],
                               capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"   Version: {result.stdout.strip()}")
    except:
        pass
else:
    print(f"⚠️  TruffleHog not installed (will be installed when secret scanner runs)")

# 2. Config file check
try:
    notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    path_parts = notebook_path.split('/')
    sat_index = path_parts.index('security-analysis-tool')
    repo_root = '/'.join(path_parts[:sat_index+1])
    config_path = f"{repo_root}/configs/trufflehog_detectors.yaml"

    # Note: Can't easily check Workspace file from notebook, so just log the path
    print(f"   Config path: {config_path}")
    print(f"   (Config will be validated when secret scanner runs)")
except:
    print(f"⚠️  Could not determine config path")

# 3. Network access check for GitHub
try:
    response = requests.head("https://raw.githubusercontent.com", timeout=5, proxies=proxies)
    print(f"✅ Network access to GitHub: OK")
except:
    print(f"❌ Network access to GitHub: FAILED")
    print(f"   ACTION: Allowlist raw.githubusercontent.com in firewall")

print()

# COMMAND ----------

# Retrieve the workspace URL from the user-provided input or fallback to the default workspace URL
workspaceUrl = userWorkspaceUrl or spark.conf.get("spark.databricks.workspaceUrl")

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
            full_endpoint = f"https://accounts.cloud.databricks.com/oidc/accounts/{source}/v1/token"   
        else: 
            full_endpoint = f'https://{source}/oidc/v1/token'

        response = requests.post(full_endpoint, headers=oidc_token,
                                    auth=user_pass, data=json_params, timeout=60, proxies=proxies)  

        if response is not None and response.status_code == 200:
            return response.json()['access_token']
        display(json.dumps(response.json()))
        return None


# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the Service Principal client_id and client_secret are valid

# COMMAND ----------

token = getAWSTokenwithOAuth(workspaceUrl,False, dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id'), dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret'))
                             
print(token)

# COMMAND ----------

import requests

workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')

url = f'https://{workspaceUrl}/api/2.0/clusters/spark-versions'
headers = {
    'Authorization': f'Bearer {token}'
}

response = requests.get(url, headers=headers, proxies=proxies)
print(response.json())

# COMMAND ----------

import requests

workspaceUrl = spark.conf.get('spark.databricks.workspaceUrl')

url = f'https://{workspaceUrl}/api/2.1/unity-catalog/catalogs'
headers = {
    'Authorization': f'Bearer {token}'
}

response = requests.get(url, headers=headers, proxies=proxies)

print(response.json())

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the token can access the workspace

# COMMAND ----------

access_token = getAWSTokenwithOAuth(dbutils.secrets.get(scope=json_['master_name_scope'], key='account-console-id'),True, dbutils.secrets.get(scope=json_['master_name_scope'], key='client-id'), dbutils.secrets.get(scope=json_['master_name_scope'], key='client-secret'))
                             
print(access_token)

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl -v -H 'Authorization: Bearer <token>'  'https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/workspaces'
# MAGIC
# MAGIC

# COMMAND ----------

import requests

DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
url = f'https://accounts.cloud.databricks.com/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}/workspaces'

## Note: The access token must be generated for a Service Principal that has account admin privileges to run this command.  

headers = {
     'Authorization': f'Bearer {access_token}' 
}

try:
    response = requests.get(url, headers=headers, proxies=proxies)
    response.raise_for_status()
    print(response.json())
except requests.exceptions.RequestException as err:
    print(f"An error occurred: {err}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify connectivity to the workspace URL and account console

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

openssl_connect('accounts.cloud.databricks.com', 443)

# COMMAND ----------

# MAGIC %sh
# MAGIC curl -X POST "https://accounts.cloud.databricks.com/oidc/accounts/<account_id>/v1/token" -H "Authorization: Basic $(echo -n '<client_id>:<secet>' | base64)"

# COMMAND ----------

# MAGIC %sh
# MAGIC export CLIENT_ID=<CLIENT_ID>
# MAGIC export CLIENT_SECRET=<CLIENT_SECRET>
# MAGIC
# MAGIC curl -v --request POST \
# MAGIC --url https://accounts.cloud.databricks.com/oidc/accounts/<account_id>/v1/token \
# MAGIC --user "$CLIENT_ID:$CLIENT_SECRET" \
# MAGIC --data 'grant_type=client_credentials&scope=all-apis'
