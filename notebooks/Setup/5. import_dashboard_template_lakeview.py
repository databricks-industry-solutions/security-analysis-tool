# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** 5. import_dashboard_template.      
# MAGIC **Functionality:** Imports dashboard template from code repo into Dashboards section for SAT report.  

# COMMAND ----------

# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

workspacedf = spark.sql("select * from `global_temp`.`all_workspaces` where workspace_id='" + current_workspace + "'" )
if (workspacedf.rdd.isEmpty()):
    dbutils.notebook.exit("The current workspace is not found in configured list of workspaces for analysis.")
display(workspacedf)
ws = (workspacedf.collect())[0]

# COMMAND ----------

import requests
import json

DOMAIN = ws.deployment_url
TOKEN =  dbutils.secrets.get(json_['workspace_pat_scope'], ws.ws_token) 
loggr.info(f"Looking for data_source_id for : {json_['sql_warehouse_id']}!")
response = requests.get(
          'https://%s/api/2.0/preview/sql/data_sources' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=None,
          timeout=60 
        )
if '\"error_code\":\"403\"' not in response.text:
    resources = json.loads(response.text)
    found = False
    for resource in resources:
        if resource['endpoint_id'] == json_['sql_warehouse_id']:
            data_source_id = resource['id']
            loggr.info(f"Found data_source_id for : {json_['sql_warehouse_id']}!") 
            found = True
            break
    if (found == False):
        dbutils.notebook.exit("The configured SQL Warehouse Endpoint is not found.")    
else:
    dbutils.notebook.exit("Invalid access token, check PAT configuration value for this workspace.")      

# COMMAND ----------

# MAGIC %md
# MAGIC #Import the Dashboard into the workspace

# COMMAND ----------

with open('/Workspace/Applications/SAT/files/dashboards/SAT_Dashboard.json') as json_file: CONTENT = json.load(json_file)

BODY = {'path': '/Workspace/Applications/SAT/files/dashboards/SAT - Security Analysis Tool (Lakeview).lvdash.json', 'content': CONTENT['content'], 'format': 'AUTO', 'overwrite': 'true'}

loggr.info(f"Importing Dashboard")
response = requests.post(
          'https://%s/api/2.0/workspace/import' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=BODY,
          timeout=60
        )

# COMMAND ----------

# MAGIC %md
# MAGIC # Get the metadata of the imported Dashboard

# COMMAND ----------

import requests
import json

with open('SAT_Dashboard.json') as json_file: CONTENT = json.load(json_file)

BODY = {'path': '/Workspace/Applications/SAT/files/dashboards/SAT - Security Analysis Tool (Lakeview).lvdash.json'}

loggr.info(f"Getting metadata of dashboard")
response = requests.post(
          'https://%s/api/2.0/workspace/get-status' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=BODY,
          timeout=60
        )

dashboard_id = json.loads(response.content.decode('utf-8'))['resource_id']

# COMMAND ----------

# MAGIC %md
# MAGIC # Publish the Dashboard using the SAT warehouse

# COMMAND ----------

import requests
import json

URL = "https://"+DOMAIN+"/api/2.0/lakeview/dashboards/"+dashboard_id+"/published"
BODY = {'embed_credentials': 'true', 'warehouse_id': json_['sql_warehouse_id']}

loggr.info(f"Publishing the Dashboard using the SAT SQL Warehouse")
response = requests.post(
          URL,
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=BODY,
          timeout=60
        )

# COMMAND ----------

dbutils.notebook.exit('OK')
