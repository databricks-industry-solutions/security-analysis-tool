# Databricks notebook source
# MAGIC %run ../Includes/install_sat_sdk

# COMMAND ----------

import time
start_time = time.time()

# COMMAND ----------

# MAGIC %run ./common

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

loggr.info('-----------------')
loggr.info(json.dumps(json_))
loggr.info('-----------------')

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)

# COMMAND ----------

from core.dbclient import SatDBClient


mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])

if (json_['use_mastercreds']) is False:
    tokenscope = json_['workspace_pat_scope']
    tokenkey = f"{json_['workspace_pat_token_prefix']}-{json_['workspace_id']}"
    token = dbutils.secrets.get(tokenscope, tokenkey)
else:
    token = ''

json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
if cloud_type =='azure':
    json_.update({'client_secret': dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])})

db_client = SatDBClient(json_)


# COMMAND ----------

is_successful_ws=False
try:
  is_successful_ws = db_client.test_connection()

  if is_successful_ws == True:
    loggr.info("Workspace Connection successful!")
  else:
    loggr.info("Unsuccessful workspace connection. Verify credentials.")
except requests.exceptions.RequestException as e:
    is_successful_ws = False
    loggr.exception('Unsuccessful connection. Verify credentials.')
except Exception:
    is_successful_ws = False
    loggr.exception("Exception encountered")

# COMMAND ----------

if not is_successful_ws:
  dbutils.notebook.exit('Unsuccessful Workspace connection. Verify credentials.')

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Clusters

# COMMAND ----------

from clientpkgs.clusters_client import ClustersClient
try:
    cluster_client = ClustersClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('clusters', cluster_client.get_cluster_list, alive=False)

# COMMAND ----------

bootstrap('spark_versions', cluster_client.get_spark_versions)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### DBSql

# COMMAND ----------

from clientpkgs.db_sql_client import DBSqlClient
try:
    db_sql_client = DBSqlClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('endpoints', db_sql_client.get_sqlendpoint_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### IPAccessList

# COMMAND ----------

from clientpkgs.ip_access_list import IPAccessClient
try:
    ip_access_client = IPAccessClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('ipaccesslist', ip_access_client.get_ipaccess_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Jobs and Job Runs

# COMMAND ----------

from clientpkgs.jobs_client import JobsClient
from clientpkgs.job_runs_client import JobRunsClient
try:
    jobs_client = JobsClient(json_)
    job_runs_client = JobRunsClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('jobs', jobs_client.get_jobs_list)

# COMMAND ----------

bootstrap('job_runs', job_runs_client.get_jobruns_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Policies

# COMMAND ----------

from clientpkgs.policies_client import PoliciesClient
try:
    policies_client = PoliciesClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('policies', policies_client.get_policies_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Pools

# COMMAND ----------

from clientpkgs.pools_client import PoolsClient
try:
    pools_client = PoolsClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('pools', pools_client.get_pools_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Repos

# COMMAND ----------

from clientpkgs.repos_client import ReposClient
try:
    repos_client = ReposClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('repos', repos_client.get_repos_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Tokens

# COMMAND ----------

from clientpkgs.tokens_client import TokensClient
try:
    tokens_client = TokensClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('tokens', tokens_client.get_tokens_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Secrets

# COMMAND ----------

from clientpkgs.secrets_client import SecretsClient
try:
    secrets_client = SecretsClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Secret Scope

# COMMAND ----------

bootstrap('secretscope', secrets_client.get_secret_scopes_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Secret List

# COMMAND ----------

df = spark.sql('select * from `global_temp`.`secretscope`')
#vList = df.rdd.map(lambda x: x['name']).collect()
vList=df.collect()
bootstrap('secretslist', secrets_client.get_secrets, scope_list=vList)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### User Groups

# COMMAND ----------

from clientpkgs.scim_client import ScimClient
try:
    scim_client = ScimClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('groups', scim_client.get_groups)

# COMMAND ----------

bootstrap('users', scim_client.get_users)

# COMMAND ----------

bootstrap('serviceprincipals', scim_client.get_users)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### MLFlow

# COMMAND ----------

from clientpkgs.ml_flow_client import MLFlowClient
try:
    mlflow_client = MLFlowClient(json_)
except:
    loggr.exception("Exception encountered")


# COMMAND ----------

bootstrap('mlflowexperiments', mlflow_client.get_experiments_list)

# COMMAND ----------

bootstrap('mlflowmodels', mlflow_client.get_registered_models)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Workspace Settings

# COMMAND ----------

from clientpkgs.ws_settings_client import WSSettingsClient
try:
    ws_client = WSSettingsClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('workspacesettings', ws_client.get_wssettings_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### DBFS

# COMMAND ----------

from clientpkgs.dbfs_client import DbfsClient
try:
    db_client = DbfsClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('dbfssettingsdirs', db_client.get_dbfs_directories, path='/user/hive/warehouse/')

# COMMAND ----------

bootstrap('dbfssettingsmounts', db_client.get_dbfs_mounts)

# COMMAND ----------

# MAGIC %md
# MAGIC 
# MAGIC ##### Global Init Scripts

# COMMAND ----------

from clientpkgs.init_scripts_client import InitScriptsClient
try:
    init_scripts_client = InitScriptsClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('globalscripts', init_scripts_client.get_allglobalinitscripts_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Libraries

# COMMAND ----------

from clientpkgs.libraries_client import LibrariesClient
try:
    lib_client = LibrariesClient(json_)
except:
    loggr.exception("Exception encountered")


# COMMAND ----------

bootstrap('libraries', lib_client.get_libraries_status_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Workspace

# COMMAND ----------

# from clientpkgs.workspace_client import WorkspaceClient
# try:
#   workspace_client = workspace_client(json_)
# except:
#   loggr.exception("Exception encountered")


# COMMAND ----------

# This is expensive. 
#bootstrap('wsnotebooks', workspace_client.get_all_notebooks)

# COMMAND ----------

print(f"Workspace Bootstrap - {time.time() - start_time} seconds to run")
