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
   # Validate that all required values are accessible (param or scope).
   # account_id, client_id already in json_ from initialize.py resolution.
   assert json_.get('account_id'), "account_id missing"
   assert json_.get('use_sp_auth') or json_.get('client_id'), "client_id/use_sp_auth missing"
   # client_secret must be in the scope.
   _sat_scope = json_.get("secret_scope", json_['master_name_scope'])
   _sat_keys  = json_.get("secret_keys", DEFAULT_SECRET_KEYS)
   dbutils.secrets.get(scope=_sat_scope, key=_sat_keys.get("client_secret", "client-secret"))
   assert json_.get('sql_warehouse_id'), "sql_warehouse_id missing"
   assert json_.get('analysis_schema_name'), "analysis_schema_name missing"
   print("Your SAT configuration has all required values")
except Exception as e:
   dbutils.notebook.exit(f'Your SAT configuration is missing a required value, please review setup instructions: {e}')

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify that the required secrets have the correct values

# COMMAND ----------

sat_scope = json_.get("secret_scope", json_['master_name_scope'])
_sat_keys = json_.get("secret_keys", DEFAULT_SECRET_KEYS)

# List scope keys and report presence/length — never print the values.
print(f"Secret scope: {sat_scope}")
print("Keys present in scope:")
for key in dbutils.secrets.list(sat_scope):
    try:
        val = dbutils.secrets.get(scope=sat_scope, key=key.key)
        print(f"  {key.key}: {'[set, {0} chars]'.format(len(val)) if val else '[empty]'}")
    except Exception as e:
        print(f"  {key.key}: [error reading: {e}]")

# Show non-secret config values from json_ directly (safe to print).
print(f"\nConfig values (from job parameters / scope fallback):")
for field in ("account_id", "client_id", "tenant_id", "subscription_id",
              "sql_warehouse_id", "analysis_schema_name", "use_sp_auth"):
    v = json_.get(field, "<not set>")
    # Partially mask UUIDs and IDs for log safety.
    if v and len(str(v)) > 8:
        display_v = f"{str(v)[:4]}...{str(v)[-4:]}"
    else:
        display_v = v
    print(f"  {field}: {display_v}")

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

token = getAWSTokenwithOAuth(workspaceUrl, False,
    json_.get("client_id") or dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("client_id", "client-id")),
    dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("client_secret", "client-secret")))

print("Workspace token obtained" if token else "Workspace token FAILED")

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

access_token = getAWSTokenwithOAuth(
    json_.get("account_id") or dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("account_id", "account-console-id")),
    True,
    json_.get("client_id") or dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("client_id", "client-id")),
    dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("client_secret", "client-secret")))

print("Account token obtained" if access_token else "Account token FAILED")

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl -v -H 'Authorization: Bearer <token>'  'https://accounts.cloud.databricks.com/api/2.0/accounts/<account_id>/workspaces'
# MAGIC
# MAGIC

# COMMAND ----------

import requests

DATABRICKS_ACCOUNT_ID = json_.get("account_id") or dbutils.secrets.get(scope=sat_scope, key=_sat_keys.get("account_id", "account-console-id"))
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
