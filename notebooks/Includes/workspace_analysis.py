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
import logging
LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
loggr = LoggingUtils.get_logger()


# COMMAND ----------

import requests, json, re
from core.dbclient import SatDBClient

mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])

if(bool(eval(json_['use_mastercreds'])) is False):
    tokenscope = json_['workspace_pat_scope']
    tokenkey = f"{json_['workspace_pat_token_prefix']}_{json_['workspace_id']}"
    token = dbutils.secrets.get(tokenscope, tokenkey)
else:
    token = ''

json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})

db_client = SatDBClient(json_)


# COMMAND ----------

cloud_type = json_['cloud_type']
workspace_id = json_['workspace_id']

sso = bool(json_['sso'])
scim = bool(json_['scim'])
object_storage_encryption = bool(json_['object_storage_encryption'])
vpc_peering = bool(json_['vpc_peering'])
table_access_control =  bool(json_['table_access_control_enabled'])

# COMMAND ----------

# MAGIC %md
# MAGIC # Network Security
# MAGIC * NPIP
# MAGIC * PrivateLink
# MAGIC * BYOVPC
# MAGIC * IPAccessList
# MAGIC * VPC Peering

# COMMAND ----------

# DBTITLE 1,NPIP - SSH Public Keys
check_id='33' #All Purpose Cluster Public Keys
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

#ssh_public_keys
def ssh_public_keys(df):
  if df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (x['cluster_id'], re.sub('[\"\'\\\\]', '_', x['cluster_name']))).toDF(['cluster_id', 'cluster_name'])  
    clusters = df.collect()
    cluster_dict = {i.cluster_id:i.cluster_name for i in clusters}
    print(cluster_dict)
    return (check_id, 1, cluster_dict)
  else:
    return (check_id, 0, {})   

if enabled:
  sqlctrl(workspace_id, '''SELECT *
    FROM global_temp.clusters
    WHERE size(ssh_public_keys) > 0  and cluster_source='UI' ''', ssh_public_keys)

# COMMAND ----------

# DBTITLE 1,NPIP - SSH Public Keys - Job Cluster
check_id='34' #Job Cluster Public Keys
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

#ssh_public_keys
def ssh_public_keysjob(df):
  if df is not None and len(df.columns)==0:
    return (check_id, 0, {'ssh':'no clusters have ssh public key'})
  elif df is not None and not df.rdd.isEmpty():
    jobcluster = df.collect()
    jobcluster_dict = {i.job_id:"ssh_key_present" for i in jobcluster}    
    print(jobcluster_dict)
    return (check_id, 1, jobcluster_dict)
  else:
    return (check_id, 0, {})    

if enabled:
  sqlctrl(workspace_id, '''select job_id from `global_temp`.`jobs` where settings.new_cluster.ssh_public_keys is not null ''', ssh_public_keysjob)

# COMMAND ----------

# DBTITLE 1,Private Link
check_id='35' #Private Link
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id

def private_link(df):
  if df is not None and not df.rdd.isEmpty():
    return (check_id, 0, {})
  else:
    return (check_id, 1, {'workspaceId' : workspaceId})     

if enabled:
  sqlctrl(workspace_id, f'''SELECT *
        FROM global_temp.`acctworkspaces`
        WHERE private_access_settings_id is not null AND workspace_id = "{workspaceId}"''', private_link) 

# COMMAND ----------

# DBTITLE 1,BYOVPC
check_id='36' #BYOVPC
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id

def byopc(df):
  if df is not None and not df.rdd.isEmpty():
    return (check_id, 0, {})
  else:
    return (check_id, 1,  {'workspaceId': workspaceId})  

if enabled:
  sql = f'''SELECT *
      FROM global_temp.`acctworkspaces`
      WHERE network_id is not null AND workspace_id = {workspaceId}'''
  sqlctrl(workspace_id, sql, byopc)

# COMMAND ----------

# DBTITLE 1,IP Access List
check_id='37' #IP Access List
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id

def public_access_enabled(df):
  if df is not None and len(df.columns)==0:
    return (check_id, 1, {'workspaceId': workspaceId})    
  if df is not None and not df.rdd.isEmpty():
    return (check_id, 0, {})
  else:
    return (check_id, 1, {'workspaceId': workspaceId})   
    
if enabled: 
  sqlctrl(workspace_id, '''SELECT label,list_type, enabled
      FROM global_temp.`ipaccesslist`
      WHERE enabled=true''', public_access_enabled)

# COMMAND ----------

check_id='39' #Secure cluster connectivity - azure
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id

def secure_cluster_connectivity_enabled(df):
  if df is not None and len(df.columns)==0:
    return (check_id, 1, {'workspaceId': workspaceId})    
  if df is not None and not df.rdd.isEmpty():
    return (check_id, 0, {})
  else:
    return (check_id, 1, {'workspaceId': workspaceId})   
    
if enabled: 
  sqlctrl(workspace_id, f'''SELECT workspace_id
      FROM global_temp.`acctworkspaces`
      WHERE enableNoPublicIp = true and workspace_id={workspaceId}''', secure_cluster_connectivity_enabled)

# COMMAND ----------

# DBTITLE 1,VPC Peer
check_id='28' #VPC Peering
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id

def vpc_peering(df):
  if vpc_peering:
    return (check_id, 0,  {})
  else:
    return (check_id, 1, {'workspaceId': workspaceId})
  
#The 1=1 logic is intentional to get the human input as an answer for this check 
if enabled:  
    sqlctrl(workspace_id, '''select * where 1=1''', vpc_peering) 

# COMMAND ----------

# MAGIC %md
# MAGIC # Identity & Access
# MAGIC * SSO
# MAGIC * SCIM
# MAGIC * RBAC
# MAGIC * Token Management (IA-4)

# COMMAND ----------

# DBTITLE 1,SSO
check_id='18' #SSO
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def sso_rule(df):
  if sso:
      return (check_id, 0, {})
  else:
      return (check_id, 1, {'workspaceId': workspaceId})
    
#The 1=1 logic is intentional to get the human input as an answer for this check
if enabled:
   sqlctrl(workspace_id, '''select * where 1=1''', sso_rule) 

# COMMAND ----------

# DBTITLE 1,SCIM
check_id='19' #SCIM  
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def scim_rule(df):
    if scim:
        return (check_id, 0,  {})
    else:
        return (check_id, 1, {'workspaceId': workspaceId})
#The 1=1 logic is intentional to get the human input as an answer for this check
if enabled:
   sqlctrl(workspace_id, '''select * where 1=1''', scim_rule) 

# COMMAND ----------

# DBTITLE 1,Table Access Control - in workspace admin
check_id='20' #Table Access Control
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def rbac_rule(df):
  if table_access_control:
      return (check_id, 0,  {})
  else:
      return (check_id, 1, {'workspaceId': workspaceId})

#The 1=1 logic is intentional to get the human input as an answer for this check
if enabled:
   sqlctrl(workspace_id, '''select * where 1=1''', rbac_rule) 

# COMMAND ----------

# MAGIC %md
# MAGIC ## Token Management (IA-4)
# MAGIC 
# MAGIC ### Best Practice
# MAGIC Customers can use the token management API or UI controls to enable or disable personal access tokens (PATs), limit the users who are allowed to use PATs or their max lifetime, and list and manage existing PATs. Highly-secure customers will typically provision a max token lifetime for a workspace. 
# MAGIC 
# MAGIC ### Documentation
# MAGIC ([AWS](https://docs.databricks.com/administration-guide/access-control/tokens.html)) ([Azure](https://docs.microsoft.com/en-us/azure/databricks/dev-tools/api/latest/authentication))
# MAGIC 
# MAGIC  

# COMMAND ----------

# DBTITLE 1,Token Management
check_id='21' #PAT Token with no lifetime limit
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
expiry_limit_evaluation_value = int(sbp_rec['evaluation_value'])
def token_rule(df):
  #Check for count of tokens that are either set to expire in over 90 days from today or set to never expire. 
  if df is not None and not df.rdd.isEmpty() and len(df.collect()) > 1:
      df = df.rdd.map(lambda x: (x['created_by_username'], re.sub('[\"\'\\\\]', '_', x['comment']), x['token_id'])).toDF(['created_by_username', 'comment', 'token_id'])            
      tokenslst = df.collect()
      tokens_dict = {i.token_id : [i.created_by_username, i.comment] for i in tokenslst}
      print(tokens_dict)
      return (check_id, 1, tokens_dict )
  else:
      return (check_id, 0, {})   
    
if enabled:
  sqlctrl(workspace_id, f'''SELECT `comment`, `created_by_username`, `token_id` FROM `global_temp`.`tokens` WHERE (datediff(from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss"), current_date()) > {expiry_limit_evaluation_value}) OR expiry_time = -1''', token_rule)

# COMMAND ----------

check_id='7' # PAT Tokens About to Expire
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
expiry_limit_evaluation_value = int(sbp_rec['evaluation_value'])
def token_rule(df):
  #Check for count of tokens that expiring in expiry_limit_evaluation_value days from today. 
  if df is not None and not df.rdd.isEmpty() and len(df.collect()) > 1:
      df = df.rdd.map(lambda x: (x['created_by_username'], re.sub('[\"\'\\\\]', '_', x['comment']), x['token_id'])).toDF(['created_by_username', 'comment', 'token_id'])            
      tokenslst = df.collect()
      tokens_dict = {i.token_id : [i.created_by_username, i.comment] for i in tokenslst}
      print(tokens_dict)
      return (check_id, 1, tokens_dict )
  else:
      return (check_id, 0, {})   
    
if enabled:
  sqlctrl(workspace_id, f'''SELECT `comment`, `created_by_username`, `token_id` FROM `global_temp`.`tokens` WHERE (datediff(from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss"), current_date()) <= {expiry_limit_evaluation_value}) and expiry_time != -1''', token_rule)

# COMMAND ----------

# DBTITLE 1,Admin count
check_id='27' #Admin Count
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
admin_count_evaluation_value = int(sbp_rec['evaluation_value'])
def admin_rule(df):  
  if df is not None and not df.rdd.isEmpty() and  len(df.collect()) > admin_count_evaluation_value:
    df = df.rdd.map(lambda x: (re.sub('[\"\'\\\\]', '_', x['Admins']),)).toDF(['Admins'])           
    adminlist = df.collect()
    adminlist_1 = [i.Admins for i in adminlist]
    adminlist_dict = {"admins" : adminlist_1}
    print(adminlist_dict)
    return (check_id, 1, adminlist_dict)
  else:
    return (check_id, 0, {})

if enabled:
  sqlctrl(workspace_id, '''select explode(members.display) as Admins 
               from global_temp.groups where displayname="admins"''', admin_rule)

# COMMAND ----------

# MAGIC %md
# MAGIC # Data Protection
# MAGIC * Secrets
# MAGIC * Encryption 
# MAGIC * Table ACL

# COMMAND ----------

# DBTITLE 1,Secrets Management
check_id='1' #Secrets Management
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
secrets_count_evaluation_value = int(sbp_rec['evaluation_value'])
def secrets_rule(df):
  if df is not None and not df.rdd.isEmpty() and df.collect()[0][0] >= secrets_count_evaluation_value:
    num_secrets = df.collect()[0][0]
    secrets_dict = {'num_secrets' : num_secrets}
    print(secrets_dict)
    return (check_id, 0, secrets_dict )
  else:
    return (check_id, 1, {})   

if enabled:
  sqlctrl(workspace_id, '''select count(*) from `global_temp`.`secretslist`''', secrets_rule)

# COMMAND ----------

# DBTITLE 1,Local Disk Encryption
check_id='2' #Cluster Encryption
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def local_disk_encryption(df):
  if df is not None and len(df.columns)==0:
    cluster_dict = {'clusters' : 'all_interactive_clusters'}
    print(cluster_dict)
    return (check_id, 1, cluster_dict) 
  elif df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (x[0], re.sub('[\"\'\\\\]', '_', x[1]))).toDF(['cluster_id', 'cluster_name']) 
    clusters = df.collect()
    clusterslst = [[i.cluster_id,i.cluster_name] for i in clusters]
    clusters_dict = {"clusters" : clusterslst}
    print(clusters_dict)
    return (check_id, 1, clusters_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:
  sqlctrl(workspace_id, '''SELECT cluster_id, cluster_name
    FROM global_temp.clusters
    WHERE enable_local_disk_encryption=False and cluster_source='UI' ''', local_disk_encryption)

# COMMAND ----------

# DBTITLE 1,BYOK
check_id='3' #BYOK
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = db_client._workspace_id
# Report on workspaces that do not have a byok id associated with them
def byok_check(df):   
  if df is not None and not df.rdd.isEmpty():
    ws = df.collect()
    ws_dict = {'workspaces' : ws}
    return (check_id, 1, ws_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:
  sqlctrl(workspace_id, f'''SELECT workspace_id
      FROM global_temp.`acctworkspaces`
      WHERE (storage_customer_managed_key_id is null) and workspace_id={workspaceId}''', byok_check)

# COMMAND ----------

# DBTITLE 1,Object Storage  Encryption
check_id='4' #Object Storage  Encryption
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

# Report on Clusters that do not have a byok id associated with them
def object_storage_encryption_rule(df):
  if object_storage_encryption:
    return (check_id, 0, {})
  else:
    return (check_id, 1, {'workspaceId': workspaceId})

#The 1=1 logic is intentional to get the human/manual input as an answer for this check
if enabled:  
  sqlctrl(workspace_id, '''select * where 1=1''', object_storage_encryption_rule)

# COMMAND ----------

# MAGIC %md
# MAGIC # Compliance
# MAGIC * Cluster Policies
# MAGIC * BYOK

# COMMAND ----------

# DBTITLE 1,Cluster Policy Check
check_id='6' #Cluster Policies
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

# Report on Clusters that do not have a policy id associated with them
def cluster_policy_check(df):
  if df is not None and len(df.columns)==0:
    cluster_dict = {'clusters' : 'all_interactive_clusters'}
    print(cluster_dict)
    return (check_id, 1, cluster_dict)    
  elif df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (x['cluster_id'], re.sub('[\"\'\\\\]', '_', x['cluster_name']))).toDF(['cluster_id', 'cluster_name'])     
    clusters = df.collect()
    cluster_dict = {'clusters' : clusters}
    return (check_id, 1, cluster_dict)
  else:
    return (check_id, 0,  {})   
  
if enabled:  
    sqlctrl(workspace_id, '''SELECT cluster_id, cluster_name, policy_id
      FROM global_temp.clusters
      WHERE policy_id is null  and cluster_source='UI' ''', cluster_policy_check)

# COMMAND ----------

## Policy needed for job clusters?

# COMMAND ----------

# DBTITLE 1,Custom Tags All Purpose Cluster
check_id='11' #All Purpose Cluster Custom Tags 
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def ctags_check(df):
  
  if df is not None and not df.rdd.isEmpty() :
    df = df.rdd.map(lambda x: (x['cluster_id'],  re.sub('[\"\'\\\\]', '_', x['cluster_name']))).toDF(['cluster_id', 'cluster_name']) 
    clusters = df.collect()
    clusters_dict = {'clusters' : [[i.cluster_id, i.cluster_name] for i in clusters]}
    print(clusters_dict)
    return (check_id, 1, clusters_dict)
  else:
    return (check_id, 0, {})   
  
if enabled: 
  sqlctrl(workspace_id, '''SELECT cluster_id, cluster_name
      FROM global_temp.`clusters`
      WHERE custom_tags is null and cluster_source='UI' ''', ctags_check)

# COMMAND ----------

# DBTITLE 1,Custom Tags Job Clusters
check_id='12' #Job Cluster Custom Tags
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def ctags_checkjobs(df):
  
  if df is not None and not df.rdd.isEmpty():
    jobclusters = df.collect()
    jobclusters_dict = {'clusters' : [i.job_id for i in jobclusters]}
    print(jobclusters_dict)
    return (check_id, 1, jobclusters_dict)
  else:
    return (check_id, 0, {})   
  

if enabled:  
   sqlctrl(workspace_id, '''SELECT job_id
      FROM global_temp.`jobs`
      WHERE settings.new_cluster.custom_tags is null''', ctags_checkjobs)

# COMMAND ----------

# DBTITLE 1,AllPurpose Cluster Log Conf
check_id='13' #All Purpose Cluster Log Configuration
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def logconf_check(df):
  if df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (x['cluster_id'],  re.sub('[\"\'\\\\]', '_', x['cluster_name']))).toDF(['cluster_id', 'cluster_name'])  
    clusters = df.collect()
    clusters_dict = {'clusters' : [[i.cluster_id, i.cluster_name] for i in clusters]}
    print(clusters_dict)
    return (check_id, 1, clusters_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:
    sqlctrl(workspace_id, '''SELECT cluster_id, cluster_name
      FROM global_temp.`clusters`
      WHERE cluster_log_conf is null  and cluster_source='UI' ''', logconf_check)

# COMMAND ----------

# DBTITLE 1,Cluster Log Conf jobs
check_id='14' #Job Cluster Log Configuration 
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def logconf_check_job(df):
  
  if df is not None and len(df.columns)==0:
    cluster_dict = {'clusters' : 'no log conf in any job'}
    print(cluster_dict)
    return (check_id, 1, cluster_dict)    
  elif df is not None and not df.rdd.isEmpty():
    jobclusters = df.collect()
    jobclusters_dict = {'jobs' : [i.job_id for i in jobclusters]}
    print(jobclusters_dict)
    return (check_id, 1, jobclusters_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:   
  sqlctrl(workspace_id, '''select job_id from global_temp.jobs where settings.new_cluster.cluster_log_conf is null''', logconf_check_job)

# COMMAND ----------

# DBTITLE 1,DBFS /user/hive/warehouse - managed tables
check_id='15'  #Managed Tables
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
dbfs_warehouses_evaluation_value = int(sbp_rec['evaluation_value'])
def dbfs_check(df):
  
  if df is not None and not df.rdd.isEmpty() and len(df.collect()) > dbfs_warehouses_evaluation_value:
    paths = df.collect()
    paths_dict = {'clusters' : [i.path for i in paths]}
    return (check_id, 1, paths_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:    
  sqlctrl(workspace_id, '''SELECT path
      FROM global_temp.`dbfssettingsdirs`''', dbfs_check)

# COMMAND ----------

# DBTITLE 1,DBFS /mnt check
check_id='16' #Mounts
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
dbfs_fuse_mnt_evaluation_value = int(sbp_rec['evaluation_value'])
def dbfs_mnt_check(df):
  
  if df is not None and not df.rdd.isEmpty() and len(df.collect())>=dbfs_fuse_mnt_evaluation_value:
    mounts = df.collect()
    mounts_dict = {'mnts' : [i.path for i in mounts]}
    print(mounts_dict)
    return (check_id, 1, mounts_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:      
  sqlctrl(workspace_id, '''SELECT path
      FROM global_temp.`dbfssettingsmounts`''', dbfs_mnt_check)

# COMMAND ----------

# DBTITLE 1,Global init scripts 
check_id='26' #Global libraries
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def initscr_check(df):
  if df is not None and not df.rdd.isEmpty():   
    iscript = df.collect()
    iscripts_dict = {'scripts' : [[i.name, i.created_by, i.enabled] for i in iscript]}
    print(iscripts_dict)
    return (check_id,1, iscripts_dict)
  else:
    return (check_id,0, {})   
  
if enabled:       
  sqlctrl(workspace_id, '''SELECT name, created_by, enabled
      FROM `global_temp`.`globalscripts`''', initscr_check)


# COMMAND ----------

# DBTITLE 1,Instance pools - Custom tags
check_id='22' #Instance Pool Custom Tag
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def pool_check(df):
  if df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (re.sub('[\"\'\\\\]', '_', x[0]), x[1])).toDF(['instance_pool_name', 'instance_pool_id'])     
    ipool = df.collect()
    ipool_dict = {'instancepools' : [[i.instance_pool_name, i.instance_pool_id] for i in ipool]}
    print(ipool_dict)
    return (check_id, 1,  ipool_dict)  
  else:
    return (check_id, 0, {}) 
  
if enabled:       
    sqlctrl(workspace_id, '''SELECT instance_pool_name, instance_pool_id
      FROM `global_temp`.`pools` where custom_tags is null''', pool_check)


# COMMAND ----------

# DBTITLE 1,jobs - max concurrent runs >=5 (Denial of Service)
check_id='23' #Max concurrent runs
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
max_concurrent_runs_evaluation_value = int(sbp_rec['evaluation_value'])
def mcr_check(df):
  if df is not None and not df.rdd.isEmpty():
    mcr = df.collect()
    mcr_dict = {'maxruns' : [[i.job_id, i.max_concurrent_runs] for i in mcr]}
    print(mcr_dict)
    return (check_id, 1, mcr_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:         
    sqlctrl(workspace_id, f'''SELECT job_id, settings.max_concurrent_runs
      FROM `global_temp`.`jobs` where settings.max_concurrent_runs >= {max_concurrent_runs_evaluation_value}''', mcr_check)


# COMMAND ----------

# DBTITLE 1,Libraries api - is_library_for_all_clusters": TRUE
check_id='24' #Global libraries
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

# https://docs.databricks.com/release-notes/runtime/7.0.html#deprecations-and-removals. Global libraries does not work DBR > 7
def lib_check(df):
  if df is not None and not df.rdd.isEmpty():
    libc = df.collect()
    libc_dict = {'globlib' : [i.cluster_id for i in libc]}
    return (check_id, 1, libc_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:          
  sqlctrl(workspace_id, '''select * from
    (select cluster_id, explode(library_statuses.is_library_for_all_clusters) as glob_lib from `global_temp`.`libraries`)a
    where glob_lib=true''', lib_check)


# COMMAND ----------

# DBTITLE 1,Multiple users have cluster create privileges
check_id='25' #User Privileges
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
max_cluster_create_count_evaluation_value = int(sbp_rec['evaluation_value'])
# Report on Clusters that do not have a policy id associated with them
def cc_check(df):
  if df is not None and not df.rdd.isEmpty() and len(df.collect())>max_cluster_create_count_evaluation_value:
    libc = df.collect()
    libc_dict = {'clus_create' : [[i.userName, i.perm] for i in libc]}
    print(libc_dict)
    return (check_id, 1, libc_dict)
  else:
    return (check_id, 0, {})   
  
if enabled:  
  sqlctrl(workspace_id, '''select userName, perm from 
     (select userName, explode(entitlements.value) as perm  from `global_temp`.`users` ) a
     where perm in ('allow-cluster-create', 'allow-instance-pool-create')''', cc_check)


# COMMAND ----------

# DBTITLE 1,Get all audit log delivery configurations. Should be enabled.
check_id='8' #Log delivery configurations
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def log_check(df):
  if df is not None and not df.rdd.isEmpty() and len(df.collect())>=1:
    df = df.rdd.map(lambda x: ( re.sub('[\"\'\\\\]', '_',x[0]), x[1])).toDF(['config_name', 'config_id'])        
    logc = df.collect()
    logc_dict = {'audit_logs' : [[i.config_name, i.config_id] for i in logc]}
    print(logc_dict)
    return (check_id, 0, logc_dict)
  else:
    return (check_id, 1, {})   

if enabled:   
    sqlctrl(workspace_id, '''select config_name, config_id from  `global_temp`.`acctlogdelivery` where log_type="AUDIT_LOGS" and status="ENABLED"''', log_check)

# COMMAND ----------

# DBTITLE 1,How long since the last cluster restart
check_id='9' #Long running clusters
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
days_since_restart_evaluation_value = int(sbp_rec['evaluation_value'])
def time_check(df):
  if df is not None and not df.rdd.isEmpty() and len(df.collect())>=1:
    timlst = df.collect()
    timlst_dict = {irow.cluster_id:irow.diff for irow in timlst if irow.diff is not None and irow.diff > days_since_restart_evaluation_value} #adjust TIME in minutes
    print(timlst_dict)
    if (len(timlst_dict)) > 0:
      return (check_id, 1, timlst_dict)
  return (check_id, 0, {})   

if enabled:   
  sqlctrl(workspace_id, '''select cluster_id, current_time, last_restart, datediff(current_time,last_restart) as diff from (select cluster_id,cluster_name,start_time,last_restarted_time, greatest(start_time,last_restarted_time) as last_start, to_timestamp(from_unixtime(greatest(start_time,last_restarted_time) / 1000), "yyyy-MM-dd hh:mm:ss") as last_restart , current_timestamp() as current_time from global_temp.clusters where state="RUNNING" and cluster_source='UI')''', time_check)

# COMMAND ----------

# DBTITLE 1,Any Deprecated versions still running
check_id='10' #Deprecated runtime versions
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def versions_check(df):
  if df is not None and not df.rdd.isEmpty() and len(df.collect())>=1:
    verlst = df.collect()
    verlst_dict = {irow.cluster_id:irow.spark_version for irow in verlst} 
    print(verlst_dict)
    return (check_id, 1, verlst_dict)
  return (check_id, 0, {})   

if enabled:    
  sqlctrl(workspace_id, '''select cluster_id, spark_version from global_temp.`clusters` where spark_version not in (select key from global_temp.`spark_versions`)''', versions_check)

# COMMAND ----------

# DBTITLE 1,Unity Catalog Check
check_id='17' #UC enabled clusters
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_check(df):
  if df is not None and not df.rdd.isEmpty():
    df = df.rdd.map(lambda x: (x[0],  re.sub('[\"\'\\\\]', '_',x[1]), x[2])).toDF(['cluster_id', 'cluster_name', 'data_security_mode'])        
    uclst = df.collect()
    uclst_dict = {i.cluster_id : [i.cluster_name, i.data_security_mode] for i in uclst}
    
    return (check_id, 1, uclst_dict)
  return (check_id, 0, {})   

if enabled:    
  sqlctrl(workspace_id, '''select cluster_id, cluster_name, data_security_mode from global_temp.clusters where cluster_source='UI' and (data_security_mode not in ('USER_ISOLATION', 'SINGLE_USER') or data_security_mode is null)''', uc_check)

# COMMAND ----------

print(f"Workspace Analysis - {time.time() - start_time} seconds to run")
