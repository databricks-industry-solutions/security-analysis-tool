# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

import time
start_time = time.time()

# COMMAND ----------

# MAGIC %run ../Utils/common

# COMMAND ----------

test=False #local testing
if test:
    jsonstr = JSONLOCALTEST
else:
    jsonstr = dbutils.widgets.get('json_')

# COMMAND ----------

import requests, json
if not jsonstr:
    print('cannot run notebook by itself')
    dbutils.notebook.exit('cannot run notebook by itself')
else:
    json_ = json.loads(jsonstr)


# COMMAND ----------

from core.logging_utils import LoggingUtils
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

cloud_type = json_['cloud_type']
workspace_id = json_['workspace_id']

# COMMAND ----------

id = '29'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableJobViewAcls(df): #Job View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)
if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="enableJobViewAcls"''', enableJobViewAcls)

# COMMAND ----------

id = '30'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enforceClusterViewAcls(df): #Cluster View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == 'true'):
        return (id, 0,  defn)
    else:
        return (id, 1,  defn)
if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="enforceClusterViewAcls"''', enforceClusterViewAcls)

# COMMAND ----------

id = '31'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enforceWorkspaceViewAcls(df): #Workspace View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="enforceWorkspaceViewAcls"''', enforceWorkspaceViewAcls)

# COMMAND ----------

id = '32'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

import json
def enableProjectTypeInWorkspace(df): #Project Type In Workspace
    value = 'false'
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn.replace("'", '')}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="enableProjectTypeInWorkspace"''', enableProjectTypeInWorkspace)

# COMMAND ----------

id = '5'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableResultsDownloading(df): #Results Downloading
    value = 'false'
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="enableResultsDownloading"''', enableResultsDownloading)

# COMMAND ----------

id = '38'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def maximumLifetimeNewTokens(df): #Max life time for tokens
    value = 0
    defn = {'defn' : ''}
    for row in df.rdd.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value is not None and value !=null and value != "null" and  value.isnumeric() and  int(value) > 0):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    sqlctrl(workspace_id, '''select * from `global_temp`.`workspacesettings` where name="maximumLifetimeNewTokens"''', maximumLifetimeNewTokens)

# COMMAND ----------

print(f"Workspace Settings - {time.time() - start_time} seconds to run")
