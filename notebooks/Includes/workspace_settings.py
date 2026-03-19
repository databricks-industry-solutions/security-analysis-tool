# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** workspace_settings  
# MAGIC **Functionality:** runs analysis logic on the workspace settings api responses and writes the results into a checks tables 

# COMMAND ----------

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
import logging
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

cloud_type = json_['cloud_type']
workspace_id = json_['workspace_id']

# COMMAND ----------

spark.sql(f"USE {json_['intermediate_schema']}")

# COMMAND ----------

id = '29'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableJobViewAcls(df): #Job View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 0, defn)
    else:
        return (id, 1, defn)
if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableJobViewAcls"
    '''
    sqlctrl(workspace_id, sql, enableJobViewAcls)

# COMMAND ----------

id = '30'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enforceClusterViewAcls(df): #Cluster View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 0,  defn)
    else:
        return (id, 1,  defn)
if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enforceClusterViewAcls"
    '''
    sqlctrl(workspace_id, sql, enforceClusterViewAcls)

# COMMAND ----------

id = '31'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enforceWorkspaceViewAcls(df): #Workspace View Acls
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enforceWorkspaceViewAcls"
    '''
    sqlctrl(workspace_id, sql, enforceWorkspaceViewAcls)

# COMMAND ----------

id = '32'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

import json
def enableProjectTypeInWorkspace(df): #Project Type In Workspace
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn.replace("'", '')}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableProjectTypeInWorkspace"
    '''
    sqlctrl(workspace_id, sql, enableProjectTypeInWorkspace)

# COMMAND ----------

id = '5'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableResultsDownloading(df): #Results Downloading
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 1, defn)
    else:
        return (id, 0, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableResultsDownloading"
    '''
    sqlctrl(workspace_id, sql, enableResultsDownloading)

# COMMAND ----------

id = '38'
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def maximumLifetimeNewTokens(df): #Max life time for tokens
    value = 0
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value is not None and value != "null" and int(value) > 0):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="maxTokenLifetimeDays"
    '''
    sqlctrl(workspace_id, sql, maximumLifetimeNewTokens)

# COMMAND ----------

id = '43' # Enable Enforce ImdsV2
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableEnforceImdsV2(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableEnforceImdsV2"
    '''
    sqlctrl(workspace_id, sql, enableEnforceImdsV2)

# COMMAND ----------

id = '44' #Notebook export 
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableExportNotebook(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 1, defn)
    else:
        return (id, 0, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableExportNotebook"
    '''
    sqlctrl(workspace_id, sql, enableExportNotebook)

# COMMAND ----------

id = '45' #Notebook Table Clipboard Features
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableNotebookTableClipboard(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row. defn}
    if(value == None or value == 'true'): # if is set or left as default (None)
        return (id, 1, defn)
    else:
        return (id, 0, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableNotebookTableClipboard"
    '''
    sqlctrl(workspace_id, sql, enableNotebookTableClipboard)

# COMMAND ----------

id = '49' # Store Interactive Notebook Results in Customer Account
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def storeInteractiveNotebookResultsInCustomerAccount(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings'+ '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="storeInteractiveNotebookResultsInCustomerAccount"
    '''
    sqlctrl(workspace_id, sql, storeInteractiveNotebookResultsInCustomerAccount)

# COMMAND ----------

id = '50' # Enable verbose audit logs
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableVerboseAuditLogs(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableVerboseAuditLogs"
    '''
    sqlctrl(workspace_id, sql, enableVerboseAuditLogs)

# COMMAND ----------

id = '51' # Review and disable FileStore endpoint in Admin Console Workspace settings
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableFileStoreEndpoint(df): 
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if(value == 'false'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name} 
        WHERE name="enableFileStoreEndpoint"
    '''
    sqlctrl(workspace_id, sql, enableFileStoreEndpoint)

# COMMAND ----------

id = '113' # Git repository allowlist configured
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableProjectsAllowList(df):
    value = 'false'
    defn = {'defn' : ''}
    allowlist = ''
    for row in df.collect():
        if row.name == 'enableProjectsAllowList':
            value = row.value if row.value else 'false'
            defn = {'defn' : row.defn.replace("'", '')}
        elif row.name == 'projectsAllowList':
            allowlist = row.value if row.value else ''
    if value == 'true':
        return (id, 0, {**defn, 'allowlist': allowlist})
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name}
        WHERE name IN ("enableProjectsAllowList", "projectsAllowList")
    '''
    sqlctrl(workspace_id, sql, enableProjectsAllowList)

# COMMAND ----------

id = '116' # DBFS file browser disabled
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableDbfsFileBrowser(df):
    value = 'true'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if value == 'false':
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name}
        WHERE name="enableDbfsFileBrowser"
    '''
    sqlctrl(workspace_id, sql, enableDbfsFileBrowser)

# COMMAND ----------

id = '118' # PAT token creation restricted to admins
enabled, sbp_rec = getSecurityBestPracticeRecord(id, cloud_type)

def enableTokensConfig(df):
    value = 'false'
    defn = {'defn' : ''}
    for row in df.collect():
        value = row.value
        defn = {'defn' : row.defn.replace("'", '')}
    if(value == 'true'):
        return (id, 0, defn)
    else:
        return (id, 1, defn)

if enabled:
    tbl_name = 'workspacesettings' + '_' + workspace_id
    sql = f'''
        SELECT * FROM {tbl_name}
        WHERE name="enableTokensConfig"
    '''
    sqlctrl(workspace_id, sql, enableTokensConfig)

# COMMAND ----------

tcomp = time.time() - start_time
print(f"Workspace Settings - {tcomp} seconds to run")

# COMMAND ----------

dbutils.notebook.exit(f'Completed SAT workspace settings in {tcomp} seconds')
