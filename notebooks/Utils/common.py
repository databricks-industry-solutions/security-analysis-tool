# Databricks notebook source
# MAGIC %md
# MAGIC ##### Common Routines

# COMMAND ----------

def bootstrap(viewname, func, **kwargs ):
  """bootstrap with function and store resulting dataframe as a global temp view
  if the function doesnt return a value, creates an empty dataframe and corresponding view
  :param str viewname - name of the view
  :param func - Name of the function to call
  :**kwargs - named args to pass to the function
    
  """
  from pyspark.sql.types import StructType
  import json
  apiDF=None
  try:
    lst = func(**kwargs)
    if lst:
      lstjson =  [json.dumps(ifld) for ifld in lst]
      apiDF = spark.read.json(sc.parallelize(lstjson))
    else:
      apiDF = spark.createDataFrame([], StructType([]))
      loggr.info('No Results!')
    spark.catalog.dropGlobalTempView(viewname)
    apiDF.createGlobalTempView(viewname)
    loggr.info(f'View created. `global_temp`.`{viewname}`')
  except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

def handleAnalysisErrors(e):
  """
  Handle AnalysisException when sql is run. This is raised when fields in sql are not found.
  """
  v= e.desc
  vlst = v.lower().split(" ")
  strField=''
  if len(vlst)>2 and vlst[0]=='cannot' and vlst[1]=='resolve':
    strField='cannot find field ' + vlst[2] + ' in SQL'
  elif len(vlst)>3 and vlst[1]=='such' and vlst[2]=='struct':
    strField='cannot find struct field `' + vlst[4] + '` in SQL'
  elif len(vlst)>2 and 'Did you mean' in v:
    strField='field ' + vlst[1] + ' not found'
  else:
    strField=v
  return strField

# COMMAND ----------

def sqlctrl(workspace_id, sqlstr, funcrule, info=False): #lambda 
    """Executes sql, tests the result with the function and write results to control table
    :param sqlstr sql to execute
    :param funcrule rule to execute to check if violation passed or failed
    :param infoStats boolean to insert into stats as opposed to control table
    """
    import pyspark.sql.utils
    from pyspark.sql.types import StructType
    try:
        df = spark.sql(sqlstr)
    except  pyspark.sql.utils.AnalysisException as e:
        s = handleAnalysisErrors(e)
        df = spark.createDataFrame([], StructType([]))
        loggr.info(s)    
    try:
        if funcrule:
            display(df)
            if info:
                name,value,category = funcrule(df)
                insertIntoInfoTable(workspace_id, name, value,category) 
            else:    
                ctrlname,ctrlscore,additional_details = funcrule(df)
                if len(additional_details) ==0 and ctrlscore ==0:
                    additional_details = {'message':'No deviations from the security best practices found for this check'}
                
                insertIntoControlTable(workspace_id, ctrlname, ctrlscore, additional_details) 
    except Exception as e:
        loggr.exception(e)


# COMMAND ----------

def sqldisplay(sqlstr):
  """
  execute a sql and display the dataframe. 
  :param str sqlstr SQL to execute
  """
  import pyspark.sql.utils
  try:
    df = spark.sql(sqlstr)
    display(df)
  except  pyspark.sql.utils.AnalysisException as e:
    s = handleAnalysisErrors(e)
    loggr.info(s)
  except Exception as e:
    loggr.exception(e)

# COMMAND ----------

def insertIntoControlTable(workspace_id, id, score, additional_details):
    """
    Insert results into a control table
    :workspace_id workspace id for this check 
    :param str id id mapping to best practices config of the check
    :param int score integer score based on violation
    :param dictionary additional_details additional details of the check
    """
    import time,json
    ts = time.time()
    #change this. Has to come via function.
    #orgId = dbutils.notebook.entry_point.getDbutils().notebook().getContext().tags().get('orgId').getOrElse(None)
    run_id = spark.sql('select max(runID) from security_analysis.run_number_table').collect()[0][0]
    jsonstr = json.dumps(additional_details)
    sql = '''INSERT INTO `security_analysis`.`security_checks` (`workspaceid`, `id`, `score`, `additional_details`, `run_id`, `check_time`) 
            VALUES ('{}', '{}', cast({} as int),  from_json('{}', 'MAP<STRING,STRING>'), {}, cast({} as timestamp))'''.format(workspace_id, id, score,  jsonstr, run_id, ts)
    ###print(sql)
    spark.sql(sql)

# COMMAND ----------

def insertIntoInfoTable(workspace_id, name, value, category):
    """
    Insert values into an information table
    :param str name name of the information
    :param value additional_details additional details of the value
    :param str category of info for filtering
    """
    import time,json
    ts = time.time()
    #change this. Has to come via function.
    #orgId = dbutils.notebook.entry_point.getDbutils().notebook().getContext().tags().get('orgId').getOrElse(None)
    run_id = spark.sql('select max(runID) from security_analysis.run_number_table').collect()[0][0]
    jsonstr = json.dumps(value)
    sql = '''INSERT INTO `security_analysis`.`account_info` (`workspaceid`,`name`, `value`, `category`, `run_id`, `check_time`) 
            VALUES ('{}','{}', from_json('{}', 'MAP<STRING,STRING>'), '{}', '{}', cast({} as timestamp))'''.format(workspace_id, name, jsonstr, category, run_id, ts)
    ### print(sql)
    spark.sql(sql)

# COMMAND ----------

def getCloudType(url):
  if '.cloud.' in url:
    return 'aws'
  elif '.azuredatabricks.' in url:
    return 'azure'
  elif '.gcp.' in url:
    return 'gcp'
  return ''

# COMMAND ----------

def readWorkspaceConfigFile():
  import pandas as pd
  prefix = getConfigPath()
  
  dfa=pd.DataFrame()
  schema = 'workspace_id string, deployment_url string, workspace_name string,workspace_status string, ws_token string, alert_subscriber_user_id string, sso_enabled boolean, scim_enabled boolean, vpc_peering_done boolean, object_storage_encypted boolean, table_access_control_enabled boolean, connection_test boolean, analysis_enabled boolean'
  dfexist = spark.createDataFrame([], schema)
  try:
    dict = {'workspace_id': 'str', 'connection_test': 'bool', 'analysis_enabled': 'bool'} 
    dfa = pd.read_csv(f'{prefix}/workspace_configs.csv', header=0, dtype=dict)
    if len(dfa) > 0:
      dfexist = spark.createDataFrame(dfa, schema)
  except FileNotFoundError:
    print('Missing workspace Config file')
    return
  except pd.errors.EmptyDataError as e:
    pass
  return dfexist

# COMMAND ----------

#read the best practices file. User configs present in this file, so use the security_best_practices_user
#to refresh delete this and it will regen however enabled and alerts will be lost.
def readBestPracticesConfigsFile():
  import pandas as pd
  from os.path import exists
  import shutil

  prefix = getConfigPath()
  origfile = f'{prefix}/security_best_practices.csv'
  userfile = f'{prefix}/security_best_practices_user.csv' #delete this file to get latest 
  file_exists = exists(userfile)
  if(file_exists is False): #regen file only if not present
    shutil.copy2(f'{origfile}', f'{userfile}')
  schema = 'id int, check_id string,category string,check string, evaluation_value string,severity string,recommendation string,doc_url string,aws int,azure int,gcp int,enable int,alert int, logic string, api string'

  security_best_practices_pd = pd.read_csv(userfile, header=0)
  
  security_best_practices = spark.createDataFrame(security_best_practices_pd, schema)
  security_best_practices.write.format('delta').mode('overwrite').saveAsTable('security_analysis.security_best_practices')
  display(security_best_practices)

# COMMAND ----------

def getSecurityBestPracticeRecord(id, cloud_type):
  df = spark.sql(f'''select * from security_analysis.security_best_practices where id = '{id}' ''')
  dict_elems = {} 
  enable=0
  if 'none' not in cloud_type and df is not None and df.count()>0:
    dict_elems = df.collect()[0]
    if dict_elems[cloud_type]==1 and dict_elems['enable']==1:
      enable=1
    
  return (enable, dict_elems)

# COMMAND ----------

def getConfigPath():
  import os
  cwd = os.getcwd().lower()
  if (cwd.rfind('/includes') != -1) or (cwd.rfind('/setup') != -1) or (cwd.rfind('/utils') != -1):
    return '../../configs'
  elif (cwd.rfind('/notebooks') != -1):
    return '../configs'
  else:
    return 'configs'

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE DATABASE IF NOT EXISTS security_analysis;
# MAGIC CREATE TABLE IF NOT EXISTS security_analysis.run_number_table (
# MAGIC   runID BIGINT GENERATED ALWAYS AS IDENTITY,
# MAGIC   check_time TIMESTAMP
# MAGIC )
# MAGIC USING DELTA
# MAGIC LOCATION '/user/hive/warehouse/security_analysis.db/run_number_table'

# COMMAND ----------

def insertNewBatchRun():
  import time
  ts = time.time()
  df = spark.sql(f'insert into security_analysis.run_number_table (check_time) values ({ts})')


# COMMAND ----------

# MAGIC %sql
# MAGIC --DROP DATABASE security_analysis CASCADE

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE DATABASE IF NOT EXISTS security_analysis;
# MAGIC CREATE TABLE IF NOT EXISTS security_analysis.security_checks (
# MAGIC   workspaceid string,
# MAGIC   id int,
# MAGIC   score integer, 
# MAGIC   additional_details map<string, string>,
# MAGIC   run_id bigint,
# MAGIC   check_time timestamp,
# MAGIC   chk_date date GENERATED ALWAYS AS (CAST(check_time AS DATE)),
# MAGIC   chk_hhmm integer GENERATED ALWAYS AS (CAST(CAST(hour(check_time) as STRING) || CAST(minute(check_time) as STRING) as INTEGER))
# MAGIC )
# MAGIC USING DELTA
# MAGIC LOCATION '/user/hive/warehouse/security_analysis.db/security_checks'
# MAGIC PARTITIONED BY (chk_date);

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE DATABASE IF NOT EXISTS security_analysis;
# MAGIC CREATE TABLE IF NOT EXISTS security_analysis.account_info (
# MAGIC   workspaceid string,
# MAGIC   name string, 
# MAGIC   value map<string, string>, 
# MAGIC   category string,
# MAGIC   run_id bigint,
# MAGIC   check_time timestamp,
# MAGIC   chk_date date GENERATED ALWAYS AS (CAST(check_time AS DATE)),
# MAGIC   chk_hhmm integer GENERATED ALWAYS AS (CAST(CAST(hour(check_time) as STRING) || CAST(minute(check_time) as STRING) as INTEGER))
# MAGIC )
# MAGIC USING DELTA
# MAGIC LOCATION '/user/hive/warehouse/security_analysis.db/account_info'
# MAGIC PARTITIONED BY (chk_date);

# COMMAND ----------

# MAGIC %sql -- drop table security_analysis.account_workspaces

# COMMAND ----------

##dbutils.fs.rm('/user/hive/warehouse/security_analysis.db/account_workspaces', True)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE DATABASE IF NOT EXISTS security_analysis;
# MAGIC CREATE TABLE IF NOT EXISTS security_analysis.account_workspaces (
# MAGIC    workspace_id string,
# MAGIC    deployment_url string,
# MAGIC    workspace_name string,
# MAGIC    workspace_status string,
# MAGIC    workspace_token string,
# MAGIC    alert_subscriber_user_id string, 
# MAGIC    analysis_enabled boolean,
# MAGIC    sso_enabled boolean, 
# MAGIC    scim_enabled boolean, 
# MAGIC    vpc_peering_done boolean, 
# MAGIC    object_storage_encypted boolean,
# MAGIC    table_access_control_enabled boolean
# MAGIC )
# MAGIC USING DELTA
# MAGIC LOCATION '/user/hive/warehouse/security_analysis.db/account_workspaces'

# COMMAND ----------

#For testing
JSONLOCALTEST='{"account_id": "", "sql_warehouse_id": "", "username_for_alerts": "sat@youremail.com", "verbosity": "info", "master_name_scope": "sat_master_scope", "master_name_key": "user", "master_pwd_scope": "sat_master_scope", "master_pwd_key": "pass", "workspace_pat_scope": "sat_master_scope", "workspace_pat_token_prefix": "sat_token", "dashboard_id": "317f4809-8d9d-4956-a79a-6eee51412217", "dashboard_folder": "../../dashboards/", "dashboard_tag": "SAT", "use_mastercreds": "true", "url": "https://satanalysis.cloud.databricks.com", "workspace_id": "2657683783405196", "cloud_type": "aws", "clusterid": "1115-184042-ntswg7ll", "sso": false, "scim": false, "object_storage_encryption": false, "vpc_peering": false, "table_access_control_enabled": false}'
