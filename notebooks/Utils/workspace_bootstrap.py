# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** workspace_bootstrap       
# MAGIC **Functionality:** Notebook that queries the workspace level APIs and creates temp tables with the results. 

# COMMAND ----------

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
workspace_id = json_['workspace_id']

# COMMAND ----------

from core.dbclient import SatDBClient

token = ''
if cloud_type =='azure': #client secret always needed
  client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
  json_.update({'token':token, 'client_secret': client_secret})
elif (cloud_type =='aws' and json_['use_sp_auth'].lower() == 'true'):  
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
    mastername = ' '
    masterpwd = ' ' # we still need to send empty user/pwd.
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
else: #lets populate master key for accounts api
    mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
    json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})
    
if (json_['use_mastercreds']) is False:
    tokenscope = json_['workspace_pat_scope']
    tokenkey = f"{json_['workspace_pat_token_prefix']}-{json_['workspace_id']}"
    token = dbutils.secrets.get(tokenscope, tokenkey)
    json_.update({'token':token})

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

#if is_successful_ws: 
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

bootstrap('clusters'+ '_' + workspace_id, cluster_client.get_cluster_list, alive=False)
#this returns job, api and ui clusters

# COMMAND ----------

bootstrap('spark_versions'+ '_' + workspace_id, cluster_client.get_spark_versions)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### DBSql

# COMMAND ----------

from clientpkgs.dbsql_client import DBSQLClient
try:
    db_sql_client =  DBSQLClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('endpoints' + '_' + workspace_id, db_sql_client.get_sqlendpoint_list)

# COMMAND ----------

bootstrap('dbsql_alerts' + '_' + workspace_id, db_sql_client.get_alerts_list)

# COMMAND ----------

bootstrap('dbsql_warehouselist' + '_' + workspace_id, db_sql_client.get_sql_warehouse_list)

# COMMAND ----------

bootstrap('dbsql_warehouselistv2' + '_' + workspace_id, db_sql_client.get_sql_warehouse_listv2)

# COMMAND ----------

bootstrap('dbsql_workspaceconfig' + '_' + workspace_id, db_sql_client.get_sql_workspace_config)

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

bootstrap('ipaccesslist'+ '_' + workspace_id, ip_access_client.get_ipaccess_list)

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

bootstrap('jobs'+ '_' + workspace_id, jobs_client.get_jobs_list)

# COMMAND ----------

bootstrap('job_runs'+ '_' + workspace_id, job_runs_client.get_jobruns_list)

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

bootstrap('policies'+ '_' + workspace_id, policies_client.get_policies_list)

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

bootstrap('pools'+ '_' + workspace_id, pools_client.get_pools_list)

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

bootstrap('repos'+ '_' + workspace_id, repos_client.get_repos_list)

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

bootstrap('tokens'+ '_' + workspace_id, tokens_client.get_tokens_list)

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

bootstrap('secretscope'+ '_' + workspace_id, secrets_client.get_secret_scopes_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Secret List

# COMMAND ----------

tbl_name = 'global_temp.secretscope' + '_' + workspace_id
sql = f'''select * from {tbl_name} '''
try:
    df = spark.sql(sql)
    #vList = df.rdd.map(lambda x: x['name']).collect()
    vList=df.collect()
    bootstrap('secretslist'+ '_' + workspace_id, secrets_client.get_secrets, scope_list=vList)
except Exception:
    loggr.exception("Exception encountered")    

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

bootstrap('groups'+ '_' + workspace_id, scim_client.get_groups)

# COMMAND ----------

bootstrap('users'+ '_' + workspace_id, scim_client.get_users)

# COMMAND ----------

bootstrap('serviceprincipals'+ '_' + workspace_id, scim_client.get_serviceprincipals)

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

bootstrap('mlflowexperiments'+ '_' + workspace_id, mlflow_client.get_experiments_list)

# COMMAND ----------

bootstrap('mlflowmodels'+ '_' + workspace_id, mlflow_client.get_registered_models)

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

bootstrap('workspacesettings'+ '_' + workspace_id, ws_client.get_wssettings_list)

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

bootstrap('dbfssettingsdirs'+ '_' + workspace_id, db_client.get_dbfs_directories, path='/user/hive/warehouse/')

# COMMAND ----------

bootstrap('dbfssettingsmounts'+ '_' + workspace_id, db_client.get_dbfs_mounts)

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

bootstrap('globalscripts'+ '_' + workspace_id, init_scripts_client.get_allglobalinitscripts_list)

# COMMAND ----------

bootstrap('legacyinitscripts'+ '_' + workspace_id, db_client.get_dbfs_directories, path='/databricks/init/')

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

bootstrap('libraries'+ '_' + workspace_id, lib_client.get_libraries_status_list)

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Unity Catalog

# COMMAND ----------

from clientpkgs.unity_catalog_client import UnityCatalogClient
try:
    uc_client = UnityCatalogClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

bootstrap('unitycatalogmsv1' + '_' + workspace_id, uc_client.get_metastore_list)

# COMMAND ----------

bootstrap('unitycatalogmsv2' + '_' + workspace_id, uc_client.get_workspace_metastore_assignments)

# COMMAND ----------

bootstrap('unitycatalogexternallocations' + '_' + workspace_id, uc_client.get_external_locations)

# COMMAND ----------

bootstrap('unitycatalogcredentials' + '_' + workspace_id, uc_client.get_credentials)

# COMMAND ----------

bootstrap('unitycatalogshares' + '_' + workspace_id, uc_client.get_list_shares)

# COMMAND ----------

bootstrap('unitycatalogshareproviders' + '_' + workspace_id, uc_client.get_sharing_providers_list)

# COMMAND ----------

bootstrap('unitycatalogsharerecipients' + '_' + workspace_id, uc_client.get_sharing_recepients_list)

# COMMAND ----------

 bootstrap('unitycatalogcatlist' + '_' + workspace_id, uc_client.get_catalogs_list)

# COMMAND ----------

 bootstrap('metastorepermissions' + '_' + workspace_id, uc_client.get_grants_effective_permissions_ext)

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

tcomp = time.time() - start_time
print(f"Workspace Bootstrap - {tcomp} seconds to run")

# COMMAND ----------

dbutils.notebook.exit(f'Completed SAT workspace bootstrap in {tcomp} seconds')
