# Databricks notebook source
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
    if df.collect()[0].aws_region is not None and df.collect()[0].aws_region:
        return ('AS-2', {'value':df.collect()[0].aws_region}, 'Account Stats')
    elif df.collect()[0].region is not None and df.collect()[0].region:
        return ('AS-2', {'value':df.collect()[0].region}, 'Account Stats')  
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
  if(df is not None):
    return ('AS-4', {'value':df.collect()[0].pricing_tier}, 'Account Stats')
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

sqlctrl(workspace_id,'''select * from `global_temp`.`jobs`''', num_defined_jobs_rule, True)

# COMMAND ----------

def num_external_jobs_rule(df):
    if(df is not None):
        return ('WST-2', {'value':df.count()}, 'Workspace Stats')
    else:
        return ('WST-2', {'value': 0}, 'Workspace Stats')

sqlctrl(workspace_id,'''select distinct job_id from `global_temp`.`job_runs` a LEFT ANTI JOIN `global_temp`.`jobs` b ON a.job_id==b.job_id''', num_external_jobs_rule, True)

# COMMAND ----------

def num_users_rule(df):
    if(df is not None):
        return ('WST-3', {'value':df.count()}, 'Workspace Stats')
    else:
        return ('WST-3', {'value': 0}, 'Workspace Stats')

sqlctrl(workspace_id,'''select * from `global_temp`.`users`''', num_users_rule, True)

# COMMAND ----------

def num_groups_rule(df):
    if(df is not None):
        return ('WST-4', {'value':df.count()}, 'Workspace Stats')
    else:
        return ('WST-4', {'value': 0}, 'Workspace Stats')

sqlctrl(workspace_id,'''select * from `global_temp`.`groups`''', num_groups_rule, True)

# COMMAND ----------

def get_num_databases():
  dbs = spark.catalog.listDatabases()
  return len(dbs)

#optimized. hopefully faster.
def get_num_tables():
  dbs = spark.catalog.listDatabases()
  table_count = 0
  for db in dbs:
    tables = spark.sql(f'SHOW TABLES IN {db.name}') 
    #tables = spark.catalog.listTables(db.name)
    table_count += tables.count()
  return table_count 

# COMMAND ----------

def num_databases_rule(df):
    if(get_num_databases() is not None):
        return ('WST-5', {'value': get_num_databases()}, 'Workspace Stats')
    else:
        return ('WST-5',  {'value': 0}, 'Workspace Stats')

sqlctrl(workspace_id,'''select * where 1=1''', num_databases_rule, True)

# COMMAND ----------

def num_tables_rule(df):
    if(get_num_tables() is not None):
        return ('WST-6', {'value': get_num_tables()}, 'Workspace Stats')
    else:
        return ('WST-6', {'value':'Coming soon'}, 'Workspace Stats')

sqlctrl(workspace_id,'''select * where 1=1''', num_tables_rule, True)

# COMMAND ----------

def num_notebooks_rule(df):
    if(df is not None):
        return ('WST-7', {'value':'Coming soon'}, 'Workspace Stats')
    else:
        return ('WST-7', {'value':'Coming soon'}, 'Workspace Stats')

sqlctrl(workspace_id,'''select * where 1=1''', num_notebooks_rule, True)

# COMMAND ----------

print(f"Workspace stats - {time.time() - start_time} seconds to run")
