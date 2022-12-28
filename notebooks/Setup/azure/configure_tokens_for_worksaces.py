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
ws_pat_token = dbutils.secrets.get(workspace_pat_scope, tokenscope+"_"+current_workspace)


master_name_scope = json_["master_name_scope"] 
master_name_key = json_["master_name_key"] 

master_pwd_scope = json_["master_pwd_scope"] 
master_pwd_key = json_["master_pwd_key"] 

account_id = json_["account_id"] 

long_term = (bool(eval(json_["generate_pat_tokens"])))

workspace_id = None
try:
    workspace_id = dbutils.widgets.get('workspace_id')
except Exception:
    loggr.exception("Exception encountered")
loggr.info(f"Renewing token for workspace: {workspace_id}")

# COMMAND ----------

def generatePATtoken(deployment_url, tempToken):
    import requests
    token_value = None  

    response = requests.post(
      '%s/api/2.0/token/create' % (deployment_url),
      headers={'Authorization': 'Bearer %s' % tempToken},
      json={ "comment": "This is an SAT token", "lifetime_seconds": 7776000 },
      timeout=60    
    )

    if response.status_code == 200:
      loggr.info(f"PAT Token is successfuly created!")
      token_value = response.json()["token_value"] 
    else:
      loggr.info(f"Error creating PAT token: {response}")   


    return token_value


# COMMAND ----------

def generateToken(deployment_url, long_term=False):
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
    access_token = None

    # Firstly, looks up a token from cache
    # Since we are looking for token for the current app, NOT for an end user,
    # notice we give account parameter as None.
    result = app.acquire_token_silent(['2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'], account=None)

    if not result:
        loggr.info("No suitable token exists in cache. Let's get a new one from AAD.")
        result = app.acquire_token_for_client(['2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'])

    if "access_token" in result:
        access_token = result['access_token']
    
    else:
       loggr.info(result.get("error"))
       loggr.info(result.get("error_description"))
       loggr.info(result.get("correlation_id"))  # You may need this when reporting a bug
    
    
    return access_token

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
      loggr.info(f"Token is successfuly stored in secrets: {response.json()}!")
    else:
      loggr.info(f"Error storing secrets: {response}")   



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
        if ( ('workspaceId' in ws['properties']) and (((workspace_id is None) and (str(ws['properties']['workspaceId']) != current_workspace)) or (workspace_id is not None and ((str(ws['properties']['workspaceId'])) == workspace_id))  and (str(ws['properties']['workspaceId']) != current_workspace))) :
            if 'workspaceUrl' in ws['properties']:
                deployment_url = 'https://'+ws['properties']['workspaceUrl']
                loggr.info(f" Getting token for Workspace : {deployment_url}")
                token = generateToken(deployment_url)
                if token and long_term:
                    loggr.info(f" Getting PAT token for Workspace : {deployment_url}")  
                    token = generatePATtoken(deployment_url,token)

                if token:
                    storeTokenAsSecret(workspace_url, workspace_pat_scope, tokenscope+"_"+str(ws['properties']['workspaceId']), ws_pat_token, token)
else:
    loggr.info(f"Error querying workspace API. Check account tokens: {response}")   

# COMMAND ----------

dbutils.notebook.exit('OK')
