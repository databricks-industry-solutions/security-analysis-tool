# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** Validate SAT Configs  
# MAGIC **Functionality:** Diagnose account and workspace connections and writes workspaces that can be connected with status into the config file

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

dbutils.secrets.listScopes()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Validate the following Values and make sure they are correct

# COMMAND ----------

sat_scope = 'sat_scope'
for key in dbutils.secrets.list(sat_scope):
    print(key.key)
    secretvalue = dbutils.secrets.get(scope=sat_scope, key=key.key)
    print(" ".join(secretvalue))


# COMMAND ----------

# MAGIC %md
# MAGIC ### Check to see if the tokens are valid

# COMMAND ----------

import requests

access_token = sat-token-<<your workspace id>>

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
# MAGIC #curl --header 'Authorization: Bearer <<Sat-token-workspace-id>>' -X GET 'https://adb-6583047541360945.5.azuredatabricks.net/api/2.0/clusters/spark-versions'

# COMMAND ----------

# MAGIC %sh 
# MAGIC
# MAGIC curl -v -H 'Authorization: Bearer <<Generate a token for the SP which is an Account admin>>'   -H 'x-databricks-account-console-api-version: 2.0' 'https://accounts.azuredatabricks.net/api/2.0/accounts/827e3e09-89ba-4dd2-9161-a3301d0f21c0/scim/v2/Users?startIndex=1&count=10'
# MAGIC
# MAGIC

# COMMAND ----------

import requests

# Define the URL and headers
DATABRICKS_ACCOUNT_ID = dbutils.secrets.get(scope=sat_scope, key="account-console-id")
url = f'https://accounts.azuredatabricks.net/api/2.0/accounts/{DATABRICKS_ACCOUNT_ID}'

## Note: The access token should be generated for a SP which is an account admin to run this command.  
access_token = <<Sat-token-workspace-id>>
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

openssl_connect('accounts.azuredatabricks.net', 443)
