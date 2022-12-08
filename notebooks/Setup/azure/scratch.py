# Databricks notebook source
pip install msal

# COMMAND ----------

#Workspace calls:

import sys  # For simplicity, we'll read config file from 1st CLI param sys.argv[1]
import json
import logging

import requests
import msal


# Optional logging
# logging.basicConfig(level=logging.DEBUG)  # Enable DEBUG log for entire script
# logging.getLogger("msal").setLevel(logging.INFO)  # Optionally disable MSAL DEBUG logs


# Create a preferably long-lived app instance which maintains a token cache.
app = msal.ConfidentialClientApplication(
    'e06da8c0-f548-4a1a-bb68-6eaa3b26babc', 
    authority='https://login.microsoftonline.com/9f37a392-f0ae-4280-9796-f1864a10effc',
    client_credential= 'C4M8Q~UAk8ZyXdKtdmtA5PUl~jPr1KfgLx5~_bog',
    # token_cache=...  # Default cache is in memory only.
                       # You can learn how to use SerializableTokenCache from
                       # https://msal-python.readthedocs.io/en/latest/#msal.SerializableTokenCache
    )

# The pattern to acquire a token looks like this.
result = None

# Firstly, looks up a token from cache
# Since we are looking for token for the current app, NOT for an end user,
# notice we give account parameter as None.
result = app.acquire_token_silent(['2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'], account=None)

if not result:
    logging.info("No suitable token exists in cache. Let's get a new one from AAD.")
    result = app.acquire_token_for_client(['2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'])

if "access_token" in result:
    # Calling graph using the access token
    graph_data = requests.get(  # Use token to call downstream service
        'https://adb-6589999224263519.19.azuredatabricks.net/api/2.0/clusters/list',
        headers={'Authorization': 'Bearer ' + result['access_token']},).json()
    print("Graph API call result: %s" % json.dumps(graph_data))

else:
    print(result.get("error"))
    print(result.get("error_description"))
    print(result.get("correlation_id"))  # You may need this when reporting a bug

# COMMAND ----------

#Account level calls:

import sys  # For simplicity, we'll read config file from 1st CLI param sys.argv[1]
import json
import logging

import requests
import msal


# Optional logging
# logging.basicConfig(level=logging.DEBUG)  # Enable DEBUG log for entire script
# logging.getLogger("msal").setLevel(logging.INFO)  # Optionally disable MSAL DEBUG logs


# Create a preferably long-lived app instance which maintains a token cache.
app = msal.ConfidentialClientApplication(
    'e06da8c0-f548-4a1a-bb68-6eaa3b26babc', 
    authority='https://login.microsoftonline.com/9f37a392-f0ae-4280-9796-f1864a10effc',
    client_credential= 'C4M8Q~UAk8ZyXdKtdmtA5PUl~jPr1KfgLx5~_bog',
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
    logging.info("No suitable token exists in cache. Let's get a new one from AAD.")
    result = app.acquire_token_for_client(['https://management.core.windows.net/.default'])

if "access_token" in result:
    # Calling graph using the access token
    graph_data = requests.get(  # Use token to call downstream service
        'https://management.azure.com/subscriptions/3f2e4d32-8e8d-46d6-82bc-5bb8d962328b/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01',
        headers={'Authorization': 'Bearer ' + result['access_token']},).json()
    print("Graph API call result: %s" % json.dumps(graph_data))

else:
    print(result.get("error"))
    print(result.get("error_description"))
    print(result.get("correlation_id"))  # You may need this when reporting a bug
