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

dfexist = readWorkspaceConfigFile()
dfexist.filter((dfexist.analysis_enabled==True) & (dfexist.connection_test==True)).createOrReplaceGlobalTempView('all_workspaces') 

# COMMAND ----------

import json
context = json.loads(dbutils.notebook.entry_point.getDbutils().notebook().getContext().toJson())
current_workspace = context['tags']['orgId']

# COMMAND ----------

workspacedf = spark.sql("select * from `global_temp`.`all_workspaces` where workspace_id='" + current_workspace + "'" )
if (workspacedf.rdd.isEmpty()):
    dbutils.notebook.exit("The current workspace is not found in configured list of workspaces for analysis.")
display(workspacedf)
ws = (workspacedf.collect())[0]

# COMMAND ----------

# MAGIC %md
# MAGIC # Delete previously created Dashboard

# COMMAND ----------

import requests

BODY = {'path': '/Workspace/Applications/SAT/files/dashboards/SAT - Security Analysis Tool (Lakeview).lvdash.json'}

loggr.info(f"Getting Dashboard")
response = requests.get(
          'https://%s/api/2.0/workspace/get-status' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=BODY,
          timeout=60
        )

if 'RESOURCE_DOES_NOT_EXIST' not in response.text:
    json_response = response.json()
    dashboard_id = json_response['resource_id']   
else:
    exists = False
    print("Dashboard doesn't exist yet")           


# COMMAND ----------

#Delete using the API DELETE /api/2.0/lakeview/dashboards/

if exists != False:

  loggr.info(f"Deleting Dashboard")
  response = requests.delete(
            'https://%s/api/2.0/lakeview/dashboards/%s' % (DOMAIN, dashboard_id),
            headers={'Authorization': 'Bearer %s' % TOKEN},
            json=BODY,
            timeout=60
          )


# COMMAND ----------

# MAGIC %md
# MAGIC # Create Dashboard from json definition

# COMMAND ----------

import requests
json_file_path = "/Workspace/Applications/SAT/files/dashboards/SAT_Dashboard_definition.json"

# Read the JSON file as a string
with open(json_file_path) as json_file:
    json_data = json.load(json_file)

json_string = json_string = json.dumps(json_data)

BODY = {'display_name': 'SAT - Security Analysis Tool (Lakeview)','warehouse_id': json_['sql_warehouse_id'], 'serialized_dashboard': json_string, 'parent_path': "/Workspace/Applications/SAT/files/dashboards"}

loggr.info(f"Creating Dashboard")
response = requests.post(
          'https://%s/api/2.0/lakeview/dashboards' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json=BODY,
          timeout=60
        )

json_response = response.json()

dashboard_id = json_response['dashboard_id']

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

response.text

# COMMAND ----------

dbutils.notebook.exit('OK')
