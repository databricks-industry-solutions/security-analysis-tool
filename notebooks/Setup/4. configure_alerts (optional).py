# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

# MAGIC %run ../Utils/initialize

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

from core import  parser as pars
from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

dfexist = readWorkspaceConfigFile()
dfexist.filter(dfexist.analysis_enabled==True).createOrReplaceTempView('configured_workspaces') 

# COMMAND ----------

workspacesdf = spark.sql('select * from `configured_workspaces`')
display(workspacesdf)
workspaces = workspacesdf.collect()

# COMMAND ----------

import requests

for ws in workspaces:
      
    DOMAIN = ws.deployment_url
    TOKEN =  dbutils.secrets.get(json_['master_pwd_scope'], ws.ws_token) 
    loggr.info(f"Creating alerts for: {DOMAIN}!") 
    response = requests.post(
      'https://%s/api/2.0/preview/sql/queries' % (DOMAIN),
      headers={'Authorization': 'Bearer %s' % TOKEN},
      json={
                "name": "sat_alert_"+ws.workspace_id,
                "description": "",
                "query": "SELECT\n  concat(\"<br> <b>Check name:</b> \",sbp.check_id, \", <b>Check:</b>\" , sbp.check, \" in workspace:\", sc.workspaceid, \n  \", <b>Recommendation:</b>\",sbp.recommendation, \"</br>\" ) as message,  count(*) as total\nFROM\n  security_analysis.security_checks sc,\n  security_analysis.security_best_practices sbp\nWHERE \nsbp.id = sc.id and\nsc.workspaceid = "+ws.workspace_id+" and\nsbp.alert = 1 and sc.score = 1 and run_id = (\n    select\n      max(runID)\n    from\n      security_analysis.run_number_table\n  )\nGROUP BY \n1\nORDER BY total DESC\n\n\n\n\n"

              }
    )

    if response.status_code == 200:
      loggr.info(f"Alert query is successfuly created: {response.json()['id']}!")
      query_id = response.json()["id"] 
    else:
      loggr.info(f"Error creating alert query: {(response.json())}")   
    
    if query_id is not None:
        response = requests.post(
          'https://%s/api/2.0/preview/sql/alerts' % (DOMAIN),
          headers={'Authorization': 'Bearer %s' % TOKEN},
          json={
           "name":"sat_alerts_"+ws.workspace_id+"",
           "options":{
              "op":">=",
              "value":1,
              "muted":"false",
              "column":"total",
              "custom_subject":"SAT-Alert for workspace:"+ws.workspace_id,
              "custom_body":"Hello,\nAlert \"{{ALERT_NAME}}\" changed status to {{ALERT_STATUS}}.\nThere have been the following unexpected events on the last day:\n{{QUERY_RESULT_ROWS}}\n\n",
              "schedule_failures":0,
               "muted":"false",

           },

           "query_id":query_id
        }
        )

        if response.status_code == 200:
          loggr.info(f"Alert is successfuly created {response.json()['id']}!")
          alert_id = response.json()["id"]
        else:
          loggr.info(f"Error creating alert: {(response.json())}")  
        
        if alert_id is not None:
            response = requests.get(
              'https://%s/api/2.0/preview/scim/v2/Users?filter=userName+eq+%s' % (DOMAIN,ws.alert_subscriber_user_id),
              headers={'Authorization': 'Bearer %s' % TOKEN},
              json=None
            )
            
            resources = json.loads(response.text)['Resources']
            for resource in resources:
              user_id = resource["id"]

            if user_id is not None:
                response = requests.post(
                  'https://%s/api/2.0/preview/sql/alerts/%s/subscriptions' % (DOMAIN, alert_id),
                  headers={'Authorization': 'Bearer %s' % TOKEN},
                  json={
                      "alert_id":alert_id,
                      "user_id":user_id
                    }
                )

                if response.status_code == 200:
                  loggr.info(f"Alert subscription is successfuly associated to user {response.json()['user']}!")
                else:
                  loggr.info(f"Error creating alert subscription: {(response.json())}")
    