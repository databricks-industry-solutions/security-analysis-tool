# Databricks notebook source
# MAGIC %run ../../Includes/install_sat_sdk

# COMMAND ----------

pip install msal

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
loggr.info(f"Current_workspace {current_workspace}")

# COMMAND ----------

subscription_id = json_["subscription_id"] 
client_id = json_["client_id"] 
client_credential = json_["client_secret"]
tenant_id = json_["tenant_id"]
loggr.info(f"Subscription id {subscription_id},  Client id {client_id} Tenant id {tenant_id}")
if subscription_id is None or client_id is None or client_credential is None or tenant_id is None:
    dbutils.notebook.exit("Please set values for :Azure subscription ID,  The Application (client) ID for the application registered in Azure AD. The Value of the client secret for the application registered in Azure AD. The Directory (tenant) ID for the application registered in Azure AD.")

workspace_pat_scope = json_['workspace_pat_scope']
tokenscope = json_['workspace_pat_token_prefix']
ws_pat_token = dbutils.secrets.get(workspace_pat_scope, tokenscope+"-"+current_workspace)


master_name_scope = json_["master_name_scope"] 
master_name_key = json_["master_name_key"] 

master_pwd_scope = json_["master_pwd_scope"] 
master_pwd_key = json_["master_pwd_key"] 

account_id = json_["account_id"] 

# COMMAND ----------

#Account level calls:
import requests
import msal


# Optional logging
# logging.basicConfig(level=logging.DEBUG)  # Enable DEBUG log for entire script
# logging.getLogger("msal").setLevel(logging.INFO)  # Optionally disable MSAL DEBUG logs


# Create a preferably long-lived app instance which maintains a token cache.
app = msal.ConfidentialClientApplication(
    client_id, 
    authority='https://login.microsoftonline.com/'+tenant_id,
    client_credential= client_credential,
    # token_cache=...  # Default cache is in memory only.
                       # You can learn how to use SerializableTokenCache from
                       # https://msal-python.readthedocs.io/en/latest/#msal.SerializableTokenCache
    )

# The pattern to acquire a token looks like this.
result = None

# Firstly, looks up a token from cache
# Since we are looking for token for the current app, NOT for an end user,
# notice we give account parameter as None.
result = app.acquire_token_silent(['https://management.core.windows.net/.default'], account=None)

if not result:
    loggr.info("No suitable token exists in cache. Let's get a new one from AAD.")
    result = app.acquire_token_for_client(['https://management.core.windows.net/.default'])

if "access_token" in result:
    access_token = result['access_token']
else:
   loggr.info(result.get("error"))
   loggr.info(result.get("error_description"))
   loggr.info(result.get("correlation_id"))  # You may need this when reporting a bug

# COMMAND ----------

import requests

response =  requests.get(  # Use token to call downstream service
                        'https://management.azure.com/subscriptions/%s/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01'% (subscription_id),
                        headers={'Authorization': 'Bearer ' + result['access_token']},
                        timeout=60
                        )

if response.status_code == 200:
    loggr.info("Workspaces query successful!")
    workspaces = response.json()['value']
    #loggr.info(workspaces)
    for ws in workspaces:
        #loggr.info('workspaceId' in ws['properties']) 
        if 'workspaceId' in ws['properties'] and str(ws['properties']['workspaceId']) == str(current_workspace):
            if 'workspaceUrl' in ws['properties']:
                workspace_url = 'https://'+ws['properties']['workspaceUrl']
        
else:
    loggr.info(f"Error querying workspace API. Check account tokens: {response}")   
    
loggr.info(f"Current workspace URL : {workspace_url}")   

# COMMAND ----------

def storeTokenAsSecret(deployment_url, scope, key, PAT_token, token):
    import requests
    

    response = requests.post(
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

if workspace_url is None or access_token is None:
    dbutils.notebook.exit("Failed to create the necessary tokens, please check your Service key file and the Impersonation service account ")

    loggr.info(f"Storing identity token :- scope:{master_pwd_scope}, key:{master_pwd_key}, on workpace:{gcp_workspace_url}")          

storeTokenAsSecret(workspace_url,master_name_scope, master_name_key,ws_pat_token,access_token)    
storeTokenAsSecret(workspace_url,master_pwd_scope, master_pwd_key,ws_pat_token,access_token)

# COMMAND ----------

dbutils.notebook.exit('OK')
