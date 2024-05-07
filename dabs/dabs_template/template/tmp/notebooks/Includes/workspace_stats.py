# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** workspace_stats  
# MAGIC **Functionality:** runs analysis logic on the workspace stats and writes the results into a checks tables 

# COMMAND ----------

# MAGIC %md
# MAGIC ##### This Notebook gets all Account Stats and Workspace level Stats like number of jobs, numer of users, pricing tier, region, etc

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
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

cloud_type = json_['cloud_type']
workspace_id = json_['workspace_id']

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get all workspace level stats that correspond to this workspace orgID

# COMMAND ----------

def getAccountId(df):
  if(df is not None):
    return ('AS-1', {'value':df.collect()[0].account_id}, 'Account Stats')
  else:
    return ('AS-1', {'value': 0}, 'Account Stats')

sqlctrl(workspace_id, f'''select * from `global_temp`.`acctworkspaces` where workspace_id={workspace_id}''', getAccountId, True)

# COMMAND ----------

def getAccountRegion(df):
  if(df is not None):
    if 'aws_region' in df.collect()[0] and df.collect()[0].aws_region is not None and df.collect()[0].aws_region:
        return ('AS-2', {'value':df.collect()[0].aws_region}, 'Account Stats')
    elif 'region' in df.collect()[0] and  df.collect()[0].region is not None and df.collect()[0].region:
        return ('AS-2', {'value':df.collect()[0].region}, 'Account Stats')
    elif 'location' in df.collect()[0] and  df.collect()[0].location is not None and df.collect()[0].location:
        return ('AS-2', {'value':df.collect()[0].location}, 'Account Stats')
    else: 
        return ('AS-2', {'value': 0}, 'Account Stats')
  else:
    return ('AS-2', {'value': 0}, 'Account Stats')

sqlctrl(workspace_id, f'''select * from `global_temp`.`acctworkspaces` where workspace_id={workspace_id}''', getAccountRegion, True)

# COMMAND ----------

def getDeploymentName(df):
  if(df is not None):
    return ('AS-3', {'value':df.collect()[0].deployment_name}, 'Account Stats')
  else:
    return ('AS-3', {'value': 0}, 'Account Stats')

sqlctrl(workspace_id, f'''select * from `global_temp`.`acctworkspaces` where workspace_id={workspace_id}''', getDeploymentName, True)

# COMMAND ----------

def getPricingTier(df):
  if(df is not None and df.collect()[0].pricing_tier is not None):
    return ('AS-4', {'value':df.collect()[0].pricing_tier.capitalize()}, 'Account Stats')
  else:
    return ('AS-4', {'value': 0}, 'Account Stats')

sqlctrl(workspace_id, f'''select * from `global_temp`.`acctworkspaces` where workspace_id={workspace_id}''', getPricingTier, True)

# COMMAND ----------

def getWorkspaceId(df):
  return ('AS-5', {'value': workspace_id}, 'Account Stats')

sqlctrl(workspace_id, f'''select 1''', getWorkspaceId, True)

# COMMAND ----------

def getWorkspaceStatus(df):
  if(df is not None):
    return ('AS-6', {'value':df.collect()[0].workspace_status}, 'Account Stats')
  else:
    return ('AS-6', {'value': 0}, 'Account Stats')

sqlctrl(workspace_id, f'''select * from `global_temp`.`acctworkspaces` where workspace_id={workspace_id}''', getWorkspaceStatus, True)

# COMMAND ----------

def num_defined_jobs_rule(df):
    if(df is not None):
        return ('WST-1', {'value':df.count()}, 'Workspace Stats')
    else:
        return ('WST-1', 0, 'OK', {'value': 0}, 'Workspace Stats')

tbl_name = 'global_temp.jobs' + '_' + workspace_id
sql = f'''
    SELECT * FROM {tbl_name} 
'''
sqlctrl(workspace_id,sql, num_defined_jobs_rule, True)

# COMMAND ----------

def num_external_jobs_rule(df):
    if(df is not None):
        return ('WST-2', {'value':df.count()}, 'Workspace Stats')
    else:
        return ('WST-2', {'value': 0}, 'Workspace Stats')

tbl_name = 'global_temp.jobs' + '_' + workspace_id
tbl_name_runs = 'global_temp.job_runs' + '_' + workspace_id
sql = f'''
    SELECT distinct job_id from FROM {tbl_name_runs} a 
    LEFT ANTI JOIN {tbl_name} b
    ON a.job_id==b.job_id
'''
sqlctrl(workspace_id, sql, num_external_jobs_rule, True)

# COMMAND ----------

tcomp = time.time() - start_time
print(f"Workspace stats - {tcomp} seconds to run")

# COMMAND ----------

dbutils.notebook.exit(f'Completed SAT workspace stats in {tcomp} seconds')
