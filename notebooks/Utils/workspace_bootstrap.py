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
    originstr = 'driver'
else:
    jsonstr = dbutils.widgets.get('json_')
    originstr = dbutils.widgets.get('origin')

# COMMAND ----------

import requests, json
if not jsonstr:
    print('cannot run notebook by itself')
    dbutils.notebook.exit('cannot run notebook by itself')
else:
    json_ = json.loads(jsonstr)

# COMMAND ----------


from core.logging_utils import LoggingUtils

LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_["verbosity"]))
loggr = LoggingUtils.get_logger()

# COMMAND ----------

loggr.info('-----------------')
loggr.info(json.dumps(json_))
loggr.info('-----------------')

# COMMAND ----------

hostname = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiUrl().getOrElse(None)
cloud_type = getCloudType(hostname)
workspace_id = json_['workspace_id']
json_.update({"cloud_type": cloud_type})

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
else: # Populate the master key for the Accounts API
    client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
    json_.update({'token':token, 'client_secret': client_secret})
    mastername = ' '
    masterpwd = ' '
    #mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
    #masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
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

spark.sql(f"USE {json_['intermediate_schema']}")

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

if any_check_enabled("2", "9", "10", "17", cloud_type=cloud_type):
    bootstrap('clusters'+ '_' + workspace_id, cluster_client.get_cluster_list, alive=False)
    #this returns job, api and ui clusters
else:
    loggr.info("Skipping clusters; DP-2/GOV-4/GOV-5/GOV-12 are disabled")

# COMMAND ----------

if any_check_enabled("10", cloud_type=cloud_type):
    bootstrap('spark_versions'+ '_' + workspace_id, cluster_client.get_spark_versions)
else:
    loggr.info("Skipping spark_versions; GOV-5 is disabled")

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

# No SAT check reads this table. Left commented for reference.
# bootstrap('dbsql_warehouselistv2' + '_' + workspace_id, db_sql_client.get_sql_warehouse_listv2)
loggr.info("Skipping dbsql_warehouselistv2; no SAT check uses this collector")

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

if any_check_enabled("37", cloud_type=cloud_type):
    bootstrap('ipaccesslist'+ '_' + workspace_id, ip_access_client.get_ip_access_list)
else:
    loggr.info("Skipping ipaccesslist; NS-5 is disabled")

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

if any_check_enabled("117", "123", cloud_type=cloud_type):
    bootstrap('jobs'+ '_' + workspace_id, jobs_client.get_jobs_list)
else:
    loggr.info("Skipping jobs; GOV-42/GOV-45 are disabled")

# COMMAND ----------

if any_check_enabled("123", cloud_type=cloud_type):
    tbl_name = 'jobs' + '_' + workspace_id
    sql = f'''SELECT job_id, settings.name AS job_name FROM {tbl_name}'''
    try:
        df = spark.sql(sql)
        job_list = df.collect()
        bootstrap('job_permissions_' + workspace_id, jobs_client.get_job_permissions_for_jobs, job_list=job_list)
    except Exception:
        loggr.exception("Exception encountered")
else:
    loggr.info("Skipping job_permissions; GOV-45 is disabled")

# COMMAND ----------

# WST-2 (workspace stats) compares job_runs to jobs; not a SAT check.
if any_check_enabled("117", "123", cloud_type=cloud_type):
    bootstrap('job_runs'+ '_' + workspace_id, job_runs_client.get_jobruns_list)
else:
    loggr.info("Skipping job_runs; GOV-42/GOV-45 are disabled (WST-2 needs jobs)")

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

#bootstrap('policies'+ '_' + workspace_id, policies_client.get_policies_list)
# No SAT check reads this table. Left commented for reference.
# bootstrap('policies'+ '_' + workspace_id, policies_client.get_cluster_policies_list)
loggr.info("Skipping policies; no SAT check uses this collector")

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

# No SAT check reads this table. Left commented for reference.
# bootstrap('pools'+ '_' + workspace_id, pools_client.get_pools_list)
loggr.info("Skipping pools; no SAT check uses this collector")

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

# No SAT check reads this table. Left commented for reference.
# bootstrap('repos'+ '_' + workspace_id, repos_client.get_repos_list)
loggr.info("Skipping repos; no SAT check uses this collector")

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

if any_check_enabled("7", "21", "41", cloud_type=cloud_type):
    bootstrap('tokens'+ '_' + workspace_id, tokens_client.get_tokens_list)
else:
    loggr.info("Skipping tokens; GOV-2/IA-4/IA-6 are disabled")

# COMMAND ----------

if any_check_enabled("118", cloud_type=cloud_type):
    bootstrap('token_permissions' + '_' + workspace_id, tokens_client.get_token_permissions)
else:
    loggr.info("Skipping token_permissions; IA-8 is disabled")

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

if any_check_enabled("1", cloud_type=cloud_type):
    bootstrap('secretscope'+ '_' + workspace_id, secrets_client.get_secret_scopes_list)
else:
    loggr.info("Skipping secretscope; DP-1 is disabled")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Secret List

# COMMAND ----------

if any_check_enabled("1", cloud_type=cloud_type):
    tbl_name = 'secretscope' + '_' + workspace_id
    sql = f'''select * from {tbl_name} '''
    try:
        df = spark.sql(sql)
        #vList = df.rdd.map(lambda x: x['name']).collect()
        vList=df.collect()
        bootstrap('secretslist'+ '_' + workspace_id, secrets_client.get_secrets, scope_list=vList)
    except Exception:
        loggr.exception("Exception encountered")
else:
    loggr.info("Skipping secretslist; DP-1 is disabled") 

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

if any_check_enabled("27", cloud_type=cloud_type):
    bootstrap('groups'+ '_' + workspace_id, scim_client.get_groups)
else:
    loggr.info("Skipping groups; INFO-6 is disabled")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('users'+ '_' + workspace_id, scim_client.get_users)
loggr.info("Skipping users; no SAT check uses this collector")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('serviceprincipals'+ '_' + workspace_id, scim_client.get_serviceprincipals)
loggr.info("Skipping serviceprincipals; no SAT check uses this collector")

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

# No SAT check reads this table. Left commented for reference.
# bootstrap('mlflowexperiments'+ '_' + workspace_id, mlflow_client.get_experiments_list)
loggr.info("Skipping mlflowexperiments; no SAT check uses this collector")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('mlflowmodels'+ '_' + workspace_id, mlflow_client.get_registered_models)
loggr.info("Skipping mlflowmodels; no SAT check uses this collector")

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

if any_check_enabled("5", "29", "30", "31", "32", "38", "41", "43", "44", "45", "49", "50", "51", "113", "116", "121", cloud_type=cloud_type):
    bootstrap('workspacesettings'+ '_' + workspace_id, ws_client.get_wssettings_list)
else:
    loggr.info("Skipping workspacesettings; related settings checks are disabled")

# COMMAND ----------

if any_check_enabled("107", cloud_type=cloud_type):
    bootstrap('automatic_cluster_update'+ '_' + workspace_id, ws_client.get_automatic_cluster_update)
else:
    loggr.info("Skipping automatic_cluster_update; GOV-36 is disabled")

# COMMAND ----------

if any_check_enabled("108", cloud_type=cloud_type):
    bootstrap('compliance_security_profile'+ '_' + workspace_id, ws_client.get_compliance_security_profile)
else:
    loggr.info("Skipping compliance_security_profile; INFO-39 is disabled")

# COMMAND ----------

if any_check_enabled("109", cloud_type=cloud_type):
    bootstrap('enhanced_security_monitoring'+ '_' + workspace_id, ws_client.get_enhanced_security_monitoring)
else:
    loggr.info("Skipping enhanced_security_monitoring; INFO-40 is disabled")

# COMMAND ----------

if any_check_enabled("106", cloud_type=cloud_type):
    bootstrap('restrict_workspace_admin_settings'+ '_' + workspace_id, ws_client.get_restrict_workspace_admin_settings)
else:
    loggr.info("Skipping restrict_workspace_admin_settings; GOV-35 is disabled")

# COMMAND ----------

if any_check_enabled("114", cloud_type=cloud_type):
    bootstrap('disable_legacy_dbfs'+ '_' + workspace_id, ws_client.get_disable_legacy_dbfs)
else:
    loggr.info("Skipping disable_legacy_dbfs; DP-10 is disabled")

# COMMAND ----------

if any_check_enabled("115", cloud_type=cloud_type):
    bootstrap('sql_results_download'+ '_' + workspace_id, ws_client.get_sql_results_download)
else:
    loggr.info("Skipping sql_results_download; DP-11 is disabled")

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

if any_check_enabled("15", cloud_type=cloud_type):
    bootstrap('dbfssettingsdirs'+ '_' + workspace_id, db_client.get_dbfs_directories, path='/user/hive/warehouse/')
else:
    loggr.info("Skipping dbfssettingsdirs; GOV-10 is disabled")

# COMMAND ----------

if any_check_enabled("16", cloud_type=cloud_type):
    bootstrap('dbfssettingsmounts'+ '_' + workspace_id, db_client.get_dbfs_mounts)
else:
    loggr.info("Skipping dbfssettingsmounts; GOV-11 is disabled")

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

if any_check_enabled("26", cloud_type=cloud_type):
    bootstrap('globalscripts'+ '_' + workspace_id, init_scripts_client.get_allglobalinitscripts_list)
else:
    loggr.info("Skipping globalscripts; INFO-5 is disabled")

# COMMAND ----------

if any_check_enabled("64", cloud_type=cloud_type):
    bootstrap('legacyinitscripts'+ '_' + workspace_id, db_client.get_dbfs_directories, path='/databricks/init/')
else:
    loggr.info("Skipping legacyinitscripts; check 64 is disabled")

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

if any_check_enabled("24", cloud_type=cloud_type):
    bootstrap('libraries'+ '_' + workspace_id, lib_client.get_libraries_status_list)
else:
    loggr.info("Skipping libraries; INFO-3 is disabled")

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

if any_check_enabled("57", cloud_type=cloud_type):
    bootstrap('unitycatalogmsv1' + '_' + workspace_id, uc_client.get_metastore_list)
else:
    loggr.info("Skipping unitycatalogmsv1; GOV-20 is disabled")

# COMMAND ----------

# GOV-16 and GOV-34 (systemschemas needs metastore_id from this table)
if any_check_enabled("53", "105", cloud_type=cloud_type):
    bootstrap('unitycatalogmsv2' + '_' + workspace_id, uc_client.get_workspace_metastore_assignments)
else:
    loggr.info("Skipping unitycatalogmsv2; GOV-16/GOV-34 are disabled")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('unitycatalogexternallocations' + '_' + workspace_id, uc_client.get_external_locations)
loggr.info("Skipping unitycatalogexternallocations; no SAT check uses this collector")

# COMMAND ----------

if any_check_enabled("59", cloud_type=cloud_type):
    bootstrap('unitycatalogcredentials' + '_' + workspace_id, uc_client.get_credentials)
else:
    loggr.info("Skipping unitycatalogcredentials; GOV-22 is disabled")

# COMMAND ----------

#bootstrap('unitycatalogshares' + '_' + workspace_id, uc_client.get_list_shares)

# COMMAND ----------

#bootstrap('unitycatalogshareproviders' + '_' + workspace_id, uc_client.get_sharing_providers_list)

# COMMAND ----------

#bootstrap('unitycatalogsharerecipients' + '_' + workspace_id, uc_client.get_sharing_recipients_list)

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('unitycatalogcatlist' + '_' + workspace_id, uc_client.get_catalogs_list)
loggr.info("Skipping unitycatalogcatlist; no SAT check uses this collector")

# COMMAND ----------

if any_check_enabled("62", cloud_type=cloud_type):
    bootstrap('metastorepermissions' + '_' + workspace_id, uc_client.get_grants_effective_permissions_ext)
else:
    loggr.info("Skipping metastorepermissions; INFO-18 is disabled")

# COMMAND ----------

if any_check_enabled("78", cloud_type=cloud_type):
    bootstrap('registered_models' + '_' + workspace_id, uc_client.get_registered_models)
else:
    loggr.info("Skipping registered_models; GOV-28 is disabled")

# COMMAND ----------

if any_check_enabled("54", "58", cloud_type=cloud_type):
    bootstrap('workspace_metastore_summary' + '_' + workspace_id, uc_client.get_workspace_metastore_summary)
else:
    loggr.info("Skipping workspace_metastore_summary; GOV-17/GOV-21 are disabled")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('artifacts_allowlists_init_scripts' + '_' + workspace_id, uc_client.get_artifacts_allowlists, artifact_type="INIT_SCRIPT")
loggr.info("Skipping artifacts_allowlists_init_scripts; no SAT check uses this collector")

# COMMAND ----------

if any_check_enabled("104", cloud_type=cloud_type):
    bootstrap('artifacts_allowlists_library_jars' + '_' + workspace_id, uc_client.get_artifacts_allowlists, artifact_type="LIBRARY_JAR")
else:
    loggr.info("Skipping artifacts_allowlists_library_jars; INFO-38 is disabled")

# COMMAND ----------

if any_check_enabled("104", cloud_type=cloud_type):
    bootstrap('artifacts_allowlists_library_mavens' + '_' + workspace_id, uc_client.get_artifacts_allowlists, artifact_type="LIBRARY_MAVEN")
else:
    loggr.info("Skipping artifacts_allowlists_library_mavens; INFO-38 is disabled")

# COMMAND ----------

if any_check_enabled("105", cloud_type=cloud_type):
    tbl_name = 'unitycatalogmsv2' + '_' + workspace_id
    sql = f'''SELECT metastore_id,workspace_id
            FROM {tbl_name} 
            WHERE workspace_id="{workspace_id}"'''
    try:
        df = spark.sql(sql)
        vList=df.collect()
        if vList is not None and len(vList) > 0:
            metastore_id= vList[0]['metastore_id']
            bootstrap('systemschemas'+ '_' + workspace_id, uc_client.get_systemschemas, metastore_id=metastore_id)
    except Exception:
        loggr.exception("Exception encountered")
else:
    loggr.info("Skipping systemschemas; GOV-34 is disabled") 

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Delta sharing

# COMMAND ----------

from clientpkgs.delta_sharing import DeltaSharingClient
try:
    delta_sharing = DeltaSharingClient(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('delta_sharing_providers_list' + '_' + workspace_id, delta_sharing.get_sharing_providers_list)
loggr.info("Skipping delta_sharing_providers_list; no SAT check uses this collector")

# COMMAND ----------

if any_check_enabled("55", "56", cloud_type=cloud_type):
    bootstrap('delta_sharing_recipients_list' + '_' + workspace_id, delta_sharing.get_sharing_recipients_list)
else:
    loggr.info("Skipping delta_sharing_recipients_list; GOV-18/GOV-19 are disabled")

# COMMAND ----------

# No SAT check reads this table. Left commented for reference.
# bootstrap('delta_list_shares' + '_' + workspace_id, delta_sharing.get_list_shares)
loggr.info("Skipping delta_list_shares; no SAT check uses this collector")

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

# MAGIC %md
# MAGIC ##### Model serving endpoints

# COMMAND ----------

from clientpkgs.serving_endpoints import ServingEndpoints
try:
    serving_endpoints = ServingEndpoints(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

if any_check_enabled("89", "90", cloud_type=cloud_type):
    bootstrap('model_serving_endpoints' + '_' + workspace_id, serving_endpoints.get_endpoints)
else:
    loggr.info("Skipping model_serving_endpoints; NS-7/INFO-29 are disabled")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Vector Search

# COMMAND ----------

from clientpkgs.vector_search import VectorSearch
try:
    vector_search = VectorSearch(json_)
except:
    loggr.exception("Exception encountered")

# COMMAND ----------

if any_check_enabled("101", cloud_type=cloud_type):
    bootstrap('vector_search_endpoint_list' + '_' + workspace_id, vector_search.get_endpoint_list)
else:
    loggr.info("Skipping vector_search_endpoint_list; DP-14 is disabled")

# COMMAND ----------

from clientpkgs.accounts_client import AccountsClient

try:
    acct_client = AccountsClient(json_)
except Exception:
    loggr.exception("Exception encountered")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Get Log Delivery Configurations

# COMMAND ----------

# only for azure. we go through the management api that does it on a workspace level
if cloud_type == 'azure' and any_check_enabled("8", cloud_type=cloud_type):
    bootstrap('acctlogdelivery' + '_' + workspace_id, acct_client.get_logdelivery_list)
elif cloud_type == 'azure':
    loggr.info("Skipping acctlogdelivery; GOV-3 is disabled")

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Egress Connectivity Test (classic compute only)

# COMMAND ----------

if not is_serverless:
    from clientpkgs.egress_test_client import EgressTestClient
    try:
        egress_test_client = EgressTestClient(json_)
    except Exception:
        loggr.exception("Exception encountered")

# COMMAND ----------

if not is_serverless and any_check_enabled("125", cloud_type=cloud_type):
    bootstrap('egress_test_results' + '_' + workspace_id, egress_test_client.get_egress_test_results)
elif not is_serverless:
    loggr.info("Skipping egress_test_results; NS-14 is disabled")

# COMMAND ----------

tcomp = time.time() - start_time
print(f"Workspace Bootstrap - {tcomp} seconds to run")

# COMMAND ----------

dbutils.notebook.exit(f'Completed SAT workspace bootstrap in {tcomp} seconds')
