# Databricks notebook source
# MAGIC %md
# MAGIC **Notebook name:** workspace_analysis  
# MAGIC **Functionality:** runs analysis logic on the workspace api respones and writes the results into a checks tables 

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

import requests, json, re
from core.dbclient import SatDBClient

# if (json_['use_mastercreds']) is False:
#     tokenscope = json_['workspace_pat_scope']
#     tokenkey = f"{json_['workspace_pat_token_prefix']}-{json_['workspace_id']}"
#     token = dbutils.secrets.get(tokenscope, tokenkey)
#     json_.update({'token':token})
# else: #mastercreds is true
#     token = ''
#     if cloud_type =='azure': #use client secret
#         client_secret = dbutils.secrets.get(json_['master_name_scope'], json_["client_secret_key"])
#         json_.update({'token':token, 'client_secret': client_secret})
#     else: #use master key for all other clouds
#         mastername = dbutils.secrets.get(json_['master_name_scope'], json_['master_name_key'])
#         masterpwd = dbutils.secrets.get(json_['master_pwd_scope'], json_['master_pwd_key'])
#         json_.update({'token':token, 'mastername':mastername, 'masterpwd':masterpwd})

# db_client = SatDBClient(json_)        
        
cloud_type = json_['cloud_type']
workspace_id = json_['workspace_id']
workspaceId = workspace_id

# COMMAND ----------


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
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql=f'''
          SELECT * 
          FROM {tbl_name} 
          WHERE size(ssh_public_keys) > 0  AND 
            (cluster_source='UI' OR cluster_source='API') AND workspace_id = "{workspaceId}" 
    '''
    sqlctrl(workspace_id, sql, ssh_public_keys)

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
    tbl_name = 'global_temp.jobs' + '_' + workspace_id
    sql =f'''
      SELECT job_id 
      FROM  {tbl_name}
      WHERE settings.new_cluster.ssh_public_keys is not null AND workspace_id = "{workspaceId}" 
    '''
    sqlctrl(workspace_id, sql, ssh_public_keys)

# COMMAND ----------

# DBTITLE 1,Private Link
check_id='35' #Private Link
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id
private_link = False
def private_link_enabled(df):
    if df is not None and not df.rdd.isEmpty():
        private_link = True
        return (check_id, 0, {})
    else:
        private_link = False
        return (check_id, 1, {'workspaceId' : workspaceId})     

if enabled:
    tbl_name = 'global_temp.acctworkspaces' 
    sql = f'''
        SELECT *
        FROM {tbl_name}
        WHERE private_access_settings_id is not null AND workspace_id = "{workspaceId}"
    ''' 
    sqlctrl(workspace_id, sql, private_link_enabled) 

# COMMAND ----------

# DBTITLE 1,BYOVPC
check_id='36' #BYOVPC
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id

def byopc(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {})
    else:
        return (check_id, 1,  {'workspaceId': workspaceId})  

if enabled:
    tbl_name = 'global_temp.acctworkspaces' 
    sql = f'''
        SELECT *
        FROM {tbl_name}
        WHERE network_id is not null AND workspace_id ="{workspaceId}"
    '''
    sqlctrl(workspace_id, sql, byopc)

# COMMAND ----------

# DBTITLE 1,IP Access List
check_id='37' #IP Access List
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id
ip_access_list = False
def public_access_enabled(df):
    if df is not None and len(df.columns)==0:
        ip_access_list = False
        return (check_id, 1, {'workspaceId': workspaceId})    
    if df is not None and not df.rdd.isEmpty():
        ip_access_list = True
        return (check_id, 0, {})
    else:
        ip_access_list = False
        return (check_id, 1, {'workspaceId': workspaceId})   
    
if enabled: 
    tbl_name = 'global_temp.ipaccesslist' + '_' + workspace_id
    sql=f'''
      SELECT label,list_type, enabled
      FROM {tbl_name}
      WHERE enabled=true
    '''
    sqlctrl(workspace_id, sql, public_access_enabled)

# COMMAND ----------

check_id='39' #Secure cluster connectivity - azure
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id

def secure_cluster_connectivity_enabled(df):
    if df is not None and len(df.columns)==0:
        return (check_id, 1, {'workspaceId': workspaceId})    
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {})
    else:
        return (check_id, 1, {'workspaceId': workspaceId})   
    
if enabled: 
    tbl_name = 'global_temp.acctworkspaces' 
    sql = f'''
          SELECT workspace_id
          FROM {tbl_name}
          WHERE enableNoPublicIp = true and workspace_id="{workspaceId}"
    '''
    sqlctrl(workspace_id, sql, secure_cluster_connectivity_enabled)

# COMMAND ----------

# DBTITLE 1,VPC Peer
check_id='28' #VPC Peering
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id

def vpc_peering(df):
    if vpc_peering:
        return (check_id, 0,  {})
    else:
        return (check_id, 1, {'workspaceId': workspaceId})

    
# The 1=1 logic is intentional to get the human input as an answer for this check 
if enabled:  
    sqlctrl(workspace_id, '''select * where 1=1''', vpc_peering) 

# COMMAND ----------

check_id='89' #NS-7 Secure model serving endpoints
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def model_serving_endpoints(df):
    if df is not None and not df.rdd.isEmpty() and (ip_access_list==False and private_link == False):
        model_serving_endpoints_list = df.collect()
        model_serving_endpoints_dict = {i.model_name : [i.endpoint_type,i.config] for i in model_serving_endpoints_list}
        
        return (check_id, 1, model_serving_endpoints_dict)
    else:
        return (check_id, 0, {'model_serving_endpoints':'Model serving endpoints protected with IP access list or private link'})   
if enabled:    
    tbl_name = 'global_temp.model_serving_endpoints' + '_' + workspace_id
    sql=f'''
        SELECT model_name, endpoint_type, config
        FROM {tbl_name} 
        
    '''
    sqlctrl(workspace_id, sql, model_serving_endpoints)

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
expiry_limit_evaluation_value = sbp_rec['evaluation_value']
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
    tbl_name = 'global_temp.tokens' + '_' + workspace_id
    sql = f'''
            SELECT `comment`, `created_by_username`, from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss") as exp_date, `token_id` 
            FROM {tbl_name} 
              WHERE (datediff(from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss"), current_date()) > {expiry_limit_evaluation_value}) OR 
                  expiry_time = -1 
    '''
    sqlctrl(workspace_id, sql, token_rule)

# COMMAND ----------

check_id='7' # PAT Tokens About to Expire
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
expiry_limit_evaluation_value = sbp_rec['evaluation_value']
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
    tbl_name = 'global_temp.tokens' + '_' + workspace_id
    sql = f'''
        SELECT `comment`, `created_by_username`, `token_id` 
        FROM {tbl_name} 
        WHERE (datediff(from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss"), current_date()) <= {expiry_limit_evaluation_value}) AND 
            expiry_time != -1 
    '''
    sqlctrl(workspace_id, sql, token_rule)

# COMMAND ----------

check_id='41' # Check for active tokens that have a lifetime that exceeds the max lifetime set - this happens for the old tokes
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
    
def token_max_life_rule(df):
    #Check for count of tokens that expiring in expiry_limit_evaluation_value days from today. 
    if df is not None and not df.rdd.isEmpty() and len(df.collect()) > 1:
        df = df.rdd.map(lambda x: (x['created_by_username'], re.sub('[\"\'\\\\]', '_', x['comment']), x['token_id'])).toDF(['created_by_username', 'comment', 'token_id'])            
        tokenslst = df.collect()
        tokens_dict = {i.token_id : [i.created_by_username, i.comment] for i in tokenslst}
        print(tokens_dict)
        return (check_id, 1, tokens_dict )
    else:
        return (check_id, 0, {})   


if enabled and ('workspacesettings' + '_' + workspace_id in sqlContext.tableNames("global_temp")):
    # get maxTokenLifetimeDays  and check if it is set 
    tbl_name = 'global_temp.workspacesettings' + '_' + workspace_id
    sql = f'''
            SELECT * 
            FROM {tbl_name} 
            WHERE name="maxTokenLifetimeDays"
    '''
    df = spark.sql(sql)
    if df.count()>0:        
        dict_elems = df.collect()[0]
        expiry_limit_evaluation_value = dict_elems['value']
    if expiry_limit_evaluation_value is not None and expiry_limit_evaluation_value != "null" and  expiry_limit_evaluation_value != "false" and int(expiry_limit_evaluation_value) > 0:
        tbl_name = 'global_temp.tokens' + '_' + workspace_id
        sql = f'''
            SELECT `comment`, `created_by_username`, `token_id` 
            FROM {tbl_name} 
            WHERE (datediff(from_unixtime(expiry_time / 1000,"yyyy-MM-dd HH:mm:ss"), current_date()) > {expiry_limit_evaluation_value} OR 
                expiry_time = -1) 
        '''
        sqlctrl(workspace_id, sql, token_max_life_rule)

# COMMAND ----------

# DBTITLE 1,Admin count
check_id='27' #Admin Count
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
admin_count_evaluation_value = sbp_rec['evaluation_value']
def admin_rule(df):  
    if df is not None and not df.rdd.isEmpty() and  len(df.collect()) > admin_count_evaluation_value:
        df = df.rdd.map(lambda x: (re.sub('[\"\'\\\\]', '_', x['Admins']),)).toDF(['Admins'])           
        adminlist = df.collect()
        adminlist_1 = [i.Admins for i in adminlist]
        adminlist_dict = {"admins" : adminlist_1}
    
        return (check_id, 1, adminlist_dict)
    else:
        return (check_id, 0, {})

if enabled:
    tbl_name = 'global_temp.groups' + '_' + workspace_id
    sql = f'''
        SELECT explode(members.display) as Admins 
        FROM {tbl_name} 
        WHERE displayname="admins" 
    '''
    sqlctrl(workspace_id, sql, admin_rule)

# COMMAND ----------

check_id='42' #Use service principals
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
service_principals_evaluation_value = sbp_rec['evaluation_value']
def use_service_principals(df):  
    if df is not None and not df.rdd.isEmpty() and  len(df.collect()) >= service_principals_evaluation_value:
        return (check_id, 0, {'SPs': len(df.collect())})
    else:
        return (check_id, 1, {'SPs':'no serviceprincipals found'})

if enabled:
    tbl_name = 'global_temp.serviceprincipals' + '_' + workspace_id
    sql=f'''
         SELECT displayName as serviceprincipals 
         FROM {tbl_name} 
    '''
    sqlctrl(workspace_id, sql, use_service_principals)

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
secrets_count_evaluation_value = sbp_rec['evaluation_value']
def secrets_rule(df):
    if df is not None and not df.rdd.isEmpty() and df.collect()[0][0] >= secrets_count_evaluation_value:
        num_secrets = df.collect()[0][0]
        secrets_dict = {'num_secrets' : num_secrets}
        print(secrets_dict)
        return (check_id, 0, secrets_dict )
    else:
        return (check_id, 1, {})   

if enabled:
    tbl_name = 'global_temp.secretslist' + '_' + workspace_id
    sql = f'''
               SELECT count(*) 
               FROM {tbl_name}
               
    ''' 
    sqlctrl(workspace_id,sql, secrets_rule)

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
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql = f'''
        SELECT cluster_id, cluster_name
        FROM {tbl_name}
        WHERE enable_local_disk_encryption=False and (cluster_source='UI' OR cluster_source='API') 
        '''
    sqlctrl(workspace_id, sql, local_disk_encryption)

# COMMAND ----------

# DBTITLE 1,BYOK
check_id='3' #BYOK
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

workspaceId = workspace_id
# Report on workspaces that do not have a byok id associated with them
def byok_check(df):   
    if df is not None and not df.rdd.isEmpty():
        ws = df.collect()
        ws_dict = {'workspaces' : ws}
        return (check_id, 1, ws_dict)
    else:
        return (check_id, 0, {})   

if enabled:
    tbl_name = 'global_temp.acctworkspaces' 
    sql = f'''
        SELECT workspace_id
          FROM {tbl_name}
          WHERE (storage_customer_managed_key_id is null and managed_services_customer_managed_key_id is null) and workspace_id="{workspaceId}"
    '''
    sqlctrl(workspace_id, sql, byok_check)

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

check_id='101' #DP-14 Store and retrieve embeddings securely
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def vector_search_endpoint_list(df):
    if df is not None and not df.rdd.isEmpty():
        vector_search_endpoint_list = df.collect()
        vector_search_endpoint_dict = {i.name : [i.endpoint_type, i.creator, i.num_indexes] for i in vector_search_endpoint_list}
        
        return (check_id, 0, vector_search_endpoint_dict )
    else:
        return (check_id, 1, {'vector_search_endpoint_list':'No Vector Search Endpoints found'})  
if enabled:    
    tbl_name = 'global_temp.vector_search_endpoint_list' + '_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name} 
        
    '''
    sqlctrl(workspace_id, sql, vector_search_endpoint_list)


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
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql = f'''
        SELECT cluster_id, cluster_name, policy_id
        FROM {tbl_name}
        WHERE policy_id is null  and (cluster_source='UI' OR cluster_source='API')
    '''
    sqlctrl(workspace_id, sql, cluster_policy_check)

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
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql = f'''
        SELECT cluster_id, cluster_name
          FROM {tbl_name}
          WHERE custom_tags is null and (cluster_source='UI' OR cluster_source='API') 
    '''
    sqlctrl(workspace_id, sql, ctags_check)

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
    tbl_name = 'global_temp.jobs' + '_' + workspace_id
    sql = f'''
        SELECT job_id
          FROM {tbl_name}
          WHERE settings.new_cluster.custom_tags is null 
      '''
    sqlctrl(workspace_id, sql, ctags_checkjobs)

# COMMAND ----------

# DBTITLE 1,AllPurpose Cluster Log Conf
check_id='13' #All Purpose Cluster Log Configuration
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def logconf_check(df):
    if df is not None and len(df.columns)==0:
        cluster_dict = {'clusters' : 'no log conf in any job'}
        print(cluster_dict)
        return (check_id, 1, cluster_dict)     
    elif df is not None and not df.rdd.isEmpty():
        df = df.rdd.map(lambda x: (x['cluster_id'],  re.sub('[\"\'\\\\]', '_', x['cluster_name']))).toDF(['cluster_id', 'cluster_name'])  
        clusters = df.collect()
        clusters_dict = {'clusters' : [[i.cluster_id, i.cluster_name] for i in clusters]}
        print(clusters_dict)
        return (check_id, 1, clusters_dict)
    else:
        return (check_id, 0, {})   
    
if enabled:
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql=f'''
      SELECT cluster_id, cluster_name
      FROM {tbl_name}
      WHERE cluster_log_conf is null  and (cluster_source='UI' OR cluster_source='API') 
    '''
    sqlctrl(workspace_id, sql, logconf_check)

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
    tbl_name = 'global_temp.jobs' + '_' + workspace_id
    sql = f'''
        SELECT job_id 
        FROM {tbl_name} 
        WHERE settings.new_cluster.cluster_log_conf is null AND workspace_id="{workspaceId}"
    '''
    sqlctrl(workspace_id, sql, logconf_check_job)

# COMMAND ----------

# DBTITLE 1,DBFS /user/hive/warehouse - managed tables
check_id='15'  #Managed Tables
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
dbfs_warehouses_evaluation_value = sbp_rec['evaluation_value']
def dbfs_check(df):
  
    if df is not None and not df.rdd.isEmpty() and len(df.collect()) >= dbfs_warehouses_evaluation_value:
        paths = df.collect()
        paths_dict = {'paths' : [i.path for i in paths]}
        return (check_id, 1, paths_dict)
    else:
        return (check_id, 0, {})   

    
if enabled:    
    tbl_name = 'global_temp.dbfssettingsdirs' + '_' + workspace_id
    sql = f'''
        SELECT path
          FROM {tbl_name}
    '''
    sqlctrl(workspace_id, sql, dbfs_check)

# COMMAND ----------

# DBTITLE 1,DBFS /mnt check
check_id='16' #Mounts
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
dbfs_fuse_mnt_evaluation_value = sbp_rec['evaluation_value']
def dbfs_mnt_check(df):
  
    if df is not None and not df.rdd.isEmpty() and len(df.collect())>=dbfs_fuse_mnt_evaluation_value:
        mounts = df.collect()
        mounts_dict = {'mnts' : [i.path for i in mounts]}
        print(mounts_dict)
        return (check_id, 1, mounts_dict)
    else:
        return (check_id, 0, {})   

    
if enabled:     
    tbl_name = 'global_temp.dbfssettingsdirs' + '_' + workspace_id
    sql =f'''
        SELECT path
        FROM {tbl_name}
    '''
    sqlctrl(workspace_id, sql, dbfs_mnt_check)

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
    tbl_name = 'global_temp.globalscripts' + '_' + workspace_id
    sql = f'''
        SELECT name, created_by, enabled
          FROM {tbl_name}
    ''' 
    sqlctrl(workspace_id, sql, initscr_check)

# COMMAND ----------

check_id='64' #Init Scripts on DBFS
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def initscr_on_dbfs(df):
    if df is not None and not df.rdd.isEmpty():   
        df = df.rdd.map(lambda x: (x['is_dir'],  re.sub('[\"\'\\\\]', '_', x['path']))).toDF(['is_dir', 'path']) 
        iscript = df.collect()
        iscripts_dict = {'scripts' : [[i.path, i.is_dir] for i in iscript]}
        print(iscripts_dict)
        return (check_id,1, iscripts_dict)
    else:
        return (check_id,0, {})   

    
if enabled:   
    tbl_name = 'global_temp.legacyinitscripts' + '_' + workspace_id
    sql = f'''
        SELECT path, is_dir
          FROM {tbl_name}
    ''' 
    sqlctrl(workspace_id, sql, initscr_on_dbfs)

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
    tbl_name = 'global_temp.pools' + '_' + workspace_id
    sql = f'''
        SELECT instance_pool_name, instance_pool_id
          FROM {tbl_name} 
            where custom_tags is null 
    '''
    sqlctrl(workspace_id, sql, pool_check)

# COMMAND ----------

# DBTITLE 1,jobs - max concurrent runs >=5 (Denial of Service)
check_id='23' #Max concurrent runs
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
max_concurrent_runs_evaluation_value = sbp_rec['evaluation_value']
def mcr_check(df):
    if df is not None and not df.rdd.isEmpty():
        mcr = df.collect()
        mcr_dict = {'maxruns' : [[i.job_id, i.max_concurrent_runs] for i in mcr]}
        print(mcr_dict)
        return (check_id, 1, mcr_dict)
    else:
        return (check_id, 0, {})   

    
if enabled:  
    tbl_name = 'global_temp.jobs' + '_' + workspace_id
    sql = f'''
        SELECT job_id, settings.max_concurrent_runs
        FROM {tbl_name}
        WHERE settings.max_concurrent_runs >= {max_concurrent_runs_evaluation_value} 
    '''
    sqlctrl(workspace_id, sql, mcr_check)

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
    tbl_name = 'global_temp.libraries' + '_' + workspace_id
    sql = f'''
        SELECT * 
        FROM
            (SELECT cluster_id, explode(library_statuses.is_library_for_all_clusters) as glob_lib FROM {tbl_name})a
        WHERE glob_lib=true 
    '''
    sqlctrl(workspace_id, sql, lib_check) 

# COMMAND ----------

# DBTITLE 1,Multiple users have cluster create privileges
check_id='25' #User Privileges
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
max_cluster_create_count_evaluation_value = sbp_rec['evaluation_value']
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
    tbl_name = 'global_temp.users' + '_' + workspace_id
    sql=f'''
        SELECT userName, perm 
        FROM 
         (SELECT userName, explode(entitlements.value) as perm  
          FROM {tbl_name} 
         ) a
        WHERE perm in ('allow-cluster-create', 'allow-instance-pool-create')     
    '''
    sqlctrl(workspace_id, sql, cc_check)

# COMMAND ----------

# DBTITLE 1,Get all audit log delivery configurations. Should be enabled.
check_id='8' #Log delivery configurations
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
workspaceId = workspace_id

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
    tbl_name = 'global_temp.acctlogdelivery' 
    sql=f'''
        SELECT config_name, config_id from  
        FROM {tbl_name} 
        WHERE log_type="AUDIT_LOGS" and status="ENABLED" 
        '''
    sqlctrl(workspace_id, sql, log_check)

# COMMAND ----------

# DBTITLE 1,How long since the last cluster restart
check_id='9' #Long running clusters
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
days_since_restart_evaluation_value = sbp_rec['evaluation_value']
def time_check(df):
    if df is not None and not df.rdd.isEmpty() and len(df.collect())>=1:
        timlst = df.collect()
        timlst_dict = {irow.cluster_id:irow.diff for irow in timlst if irow.diff is not None and irow.diff > days_since_restart_evaluation_value} #adjust TIME in minutes
        print(timlst_dict)
        if (len(timlst_dict)) > 0:
            return (check_id, 1, timlst_dict)
    return (check_id, 0, {})   

if enabled:   
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql=f'''
        SELECT cluster_id, current_time, last_restart, datediff(current_time,last_restart) as diff 
        FROM (SELECT cluster_id,cluster_name,start_time,last_restarted_time, greatest(start_time,last_restarted_time) as last_start,   
                to_timestamp(from_unixtime(greatest(start_time,last_restarted_time) / 1000, "yyyy-MM-dd hh:mm:ss")) as last_restart , current_timestamp() as 
                current_time 
              FROM {tbl_name} 
              WHERE state="RUNNING" and (cluster_source='UI' OR cluster_source='API') ) 
    '''
    sqlctrl(workspace_id, sql, time_check)

# COMMAND ----------

# DBTITLE 1,Any Deprecated versions still running
check_id='10' #Deprecated runtime versions
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def versions_check(df):
    if df is not None and not df.rdd.isEmpty() and len(df.collect())>=1:
        df = df.rdd.map(lambda x: (x['cluster_id'], x['spark_version'], re.sub('[\"\'\\\\]', '_',x['cluster_name']))).toDF(['cluster_id', 'spark_version','cluster_name'])  
        verlst = df.collect()
        verlst_dict = {irow.cluster_id: "cluster_name:"+irow.cluster_name+" version:"+irow.spark_version for irow in verlst} 
        print(verlst_dict)
        return (check_id, 1, verlst_dict)
    return (check_id, 0, {})   

if enabled:    
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    tbl_name_inner = 'global_temp.spark_versions' + '_' + workspace_id
    sql=f'''SELECT cluster_id, cluster_name, spark_version 
          FROM {tbl_name}
          WHERE spark_version not in (select key from {tbl_name_inner}) 
    '''
    sqlctrl(workspace_id, sql, versions_check)

# COMMAND ----------

# DBTITLE 1,Unity Catalog Check
check_id='17' #UC enabled clusters
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_check(df):
    if df is not None and not df.rdd.isEmpty():
        df = df.rdd.map(lambda x: (x[0],  re.sub('[\"\'\\\\]', '_',x[1]))).toDF(['cluster_id', 'cluster_name'])        
        uclst = df.collect()
        uclst_dict = {i.cluster_id : [i.cluster_name] for i in uclst}
    
        return (check_id, 1, uclst_dict)
    return (check_id, 0, {})   

if enabled:    
    tbl_name = 'global_temp.clusters' + '_' + workspace_id
    sql=f'''
        SELECT cluster_id, cluster_name 
        FROM {tbl_name} 
        WHERE (cluster_source='UI' OR cluster_source='API') 
            and (data_security_mode not in ('USER_ISOLATION', 'SINGLE_USER') or data_security_mode is null)
            
    '''
    sqlctrl(workspace_id, sql, uc_check)

# COMMAND ----------

check_id='53' #	GOV-16 Workspace Unity Catalog metastore assignment
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_metasore_assignment(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {i.metastore_id : [i.workspace_id] for i in uc_metasore}
        return (check_id, 0, uc_metasore_dict )
    else:
        return (check_id, 1, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogmsv2' + '_' + workspace_id
    sql=f'''
        SELECT metastore_id,workspace_id
        FROM {tbl_name} 
        WHERE workspace_id="{workspaceId}"
            
    '''
    sqlctrl(workspace_id, sql, uc_metasore_assignment)

# COMMAND ----------

check_id='54' #	GOV-17 Lifetime of metastore delta sharing recipient token set less than 90 days
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_metasore_token(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {num: [row.name,row.delta_sharing_recipient_token_lifetime_in_seconds] for num,row in enumerate(uc_metasore)}
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogmsv1' + '_' + workspace_id
    sql=f'''
        SELECT name, delta_sharing_recipient_token_lifetime_in_seconds
        FROM {tbl_name} 
        WHERE delta_sharing_scope ="INTERNAL_AND_EXTERNAL" AND delta_sharing_recipient_token_lifetime_in_seconds < 7776000
    '''
    sqlctrl(workspace_id, sql, uc_metasore_token)
    

# COMMAND ----------

check_id='55' #	GOV-18  Check if there are any token based sharing without IP access lists ip_access_list
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_delta_share_ip_accesslist(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {num: [row.name,row.owner] for num,row in enumerate(uc_metasore)}
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogsharerecipients' + '_' + workspace_id
    sql=f'''
        SELECT name, owner
        FROM {tbl_name} 
        where authentication_type = 'TOKEN' and ip_access_list is NULL
    '''
    sqlctrl(workspace_id, sql, uc_delta_share_ip_accesslist)
    

# COMMAND ----------

check_id='56' #	GOV-19  Check if Delta sharing Token Expiration
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_delta_share_expiration_time(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {num: [row.name,row.owner] for num,row in enumerate(uc_metasore)}
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogsharerecipients' + '_' + workspace_id
    sql=f'''
        SELECT tokens.* FROM (select explode(tokens) as tokens, full_name, owner
        FROM {tbl_name} 
        WHERE authentication_type = 'TOKEN')   WHERE tokens.expiration_time is NULL 
    '''
    sqlctrl(workspace_id, sql, uc_delta_share_expiration_time)
 

# COMMAND ----------

check_id='57' #	GOV-20  Check Use of Metastore
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_metastore(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {i.name : [i.owner] for i in uc_metasore}
        return (check_id, 0, uc_metasore_dict )
    else:
        return (check_id, 1, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogmsv1' + '_' + workspace_id
    sql=f'''
        SELECT name,owner
        FROM {tbl_name} 
        WHERE securable_type = 'METASTORE'
    '''
    sqlctrl(workspace_id, sql, uc_metastore)
 

# COMMAND ----------

check_id='58' #	GOV-21  Check Metastore Admin is also the creator
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_metastore_owner(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {i.name : [i.owner, i.created_by] for i in uc_metasore}
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogmsv1' + '_' + workspace_id
    sql=f'''
        SELECT name,owner,created_by
        FROM {tbl_name} 
        WHERE securable_type = 'METASTORE' and owner == created_by
    '''
    sqlctrl(workspace_id, sql, uc_metastore_owner)
 

# COMMAND ----------

check_id='59' #	GOV-22  Check Metastore Storage Credentials
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_metastore_storage_creds(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {num: [row.name,row.owner, row.created_by] for num,row in enumerate(uc_metasore)}
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.unitycatalogcredentials' + '_' + workspace_id
    sql=f'''
        SELECT name,owner,created_by
        FROM {tbl_name} 
        WHERE securable_type = "STORAGE_CREDENTIAL" 
    '''
    sqlctrl(workspace_id, sql, uc_metastore_storage_creds)
 

# COMMAND ----------

check_id='60' #	GOV-23  Check UC enabled Data warehouses
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def uc_dws(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {i.name : [i.creator_name] for i in uc_metasore}
        
        return (check_id, 1, uc_metasore_dict )
    else:
        return (check_id, 0, {})   
if enabled:    
    tbl_name = 'global_temp.dbsql_warehouselistv2' + '_' + workspace_id
    sql=f'''
        SELECT warehouse.name as name , warehouse.creator_name as creator_name  from (select explode(warehouses) as warehouse  
        FROM {tbl_name} ) 
        where warehouse.disable_uc = true
    '''
    sqlctrl(workspace_id, sql, uc_dws)
 

# COMMAND ----------

check_id='78' #	GOV-28  Check Govern model assets
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def models_in_uc(df):
    if df is not None and not df.rdd.isEmpty():
        uc_models = df.collect()
        uc_models_dict = {i.name : [i.full_name] for i in uc_models}
        
        return (check_id, 0, uc_models_dict )
    else:
        return (check_id, 1, {})   
if enabled:    
    tbl_name = 'global_temp.registered_models' + '_' + workspace_id
    sql=f'''
        SELECT name, catalog_name,schema_name,owner, full_name
        FROM {tbl_name} 
        
    '''
    sqlctrl(workspace_id, sql, models_in_uc)

# COMMAND ----------

check_id='105' #GOV-34,Governance,Monitor audit logs with system tables
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
metastores= {} # hold all the metastores that have no 'access' schema with state ENABLE_COMPLETED
def uc_systemschemas(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'enable_serverless_compute':'access schema with state ENABLE_COMPLETED found'} )
    else:
        return (check_id, 1, {'enable_serverless_compute':'access schema with state ENABLE_COMPLETED not found'}) 
    
if enabled:    
    tbl_name = 'global_temp.systemschemas' + '_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name} 
        where schema ="access" and state ="ENABLE_COMPLETED"
    '''
    sqlctrl(workspace_id, sql, uc_systemschemas)

# COMMAND ----------

check_id='106'#GOV-35,Governance,Restrict workspace admins
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
metastores= {} # hold all the metastores that have no 'access' schema with state ENABLE_COMPLETED
def restrict_workspace_admin_settings(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 1, {'restrict_workspace_admin_settings':'Found status as ALLOW_ALL, to disable the RestrictWorkspaceAdmins set the status to ALLOW_ALL'} )
    else:
        return (check_id, 0, {'restrict_workspace_admin_settings':'RestrictWorkspaceAdmins set the status to ALLOW_ALL'}) 
    
if enabled:    
    tbl_name = 'global_temp.restrict_workspace_admin_settings' + '_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name} 
        where restrict_workspace_admins.status = "ALLOW_ALL"
    '''
    sqlctrl(workspace_id, sql, restrict_workspace_admin_settings)

# COMMAND ----------

check_id='107'#GOV-36,Governance,Automatic cluster update
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)
def automatic_cluster_update(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'automatic_cluster_update':'Found status as true to automatic cluster update setting'} )
    else:
        return (check_id, 1, {'automatic_cluster_update':'Found status as false to automatic cluster update setting'}) 
    
if enabled:    
    tbl_name = 'global_temp.automatic_cluster_update' + '_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name} 
        where automatic_cluster_update_workspace.enabled = true
    '''
    sqlctrl(workspace_id, sql, automatic_cluster_update)

# COMMAND ----------

check_id='61' #	INFO-17  Check Serverless Compute enabled
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def dbsql_enable_serverless_compute(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'enable_serverless_compute':'Serverless Compute enabled'} )
    else:
        return (check_id, 1, {'enable_serverless_compute':'Serverless Compute not enabled'})   
if enabled:    
    tbl_name = 'global_temp.dbsql_workspaceconfig' + '_' + workspace_id
    sql=f'''
        SELECT enable_serverless_compute FROM
        FROM {tbl_name} 
        WHERE enable_serverless_compute = true
    '''
    sqlctrl(workspace_id, sql, dbsql_enable_serverless_compute)
 

# COMMAND ----------

check_id='62' #	INFO-18  Check Delta Sharing CREATE_RECIPIENT and CREATE_SHARE permissions
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def metastore_delta_sharing_permissions(df):
    if df is not None and not df.rdd.isEmpty():
        uc_metasore = df.collect()
        uc_metasore_dict = {num: [row.metastore_name,row.principal, row.privilege] for num,row in enumerate(uc_metasore)}
        return (check_id, 0, uc_metasore_dict ) # intentionally kept the score to 0 as its not a pass or fail. Its more of FYI
    else:
        return (check_id, 0, {})   # intentionally kept the score to 0 as its not a pass or fail. Its more of FYI
if enabled:    
    tbl_name = 'global_temp.metastorepermissions' + '_' + workspace_id
    sql=f'''
        SELECT * FROM (SELECT metastore_name,principal,explode(privileges) as privilege  
        FROM {tbl_name} )
        WHERE privilege= "CREATE_RECIPIENT" OR  privilege="CREATE_SHARE"
    '''
    sqlctrl(workspace_id, sql, metastore_delta_sharing_permissions)

# COMMAND ----------

check_id='90' #INFO-29 Streamline the usage and management of various large language model (LLM) providers
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def model_serving_endpoints_external_model(df):
    if df is not None and not df.rdd.isEmpty() and df.count()>1:
        model_serving_endpoints_list = df.collect()
        model_serving_endpoints_dict = {i.name : [i.endpoint_type,i.config] for i in model_serving_endpoints_list}
        
        return (check_id, 0, model_serving_endpoints_dict)
    else:
        return (check_id, 1, {'model_serving_endpoints_external_model':'No model serving endpoints with endpoint type EXTERNAL_MODEL found'})   
if enabled:    
    tbl_name = 'global_temp.model_serving_endpoints' + '_' + workspace_id
    sql=f'''
        SELECT name, endpoint_type, config
        FROM {tbl_name}  WHERE endpoint_type = 'EXTERNAL_MODEL'  
        
    '''
    sqlctrl(workspace_id, sql, model_serving_endpoints_external_model)

# COMMAND ----------

check_id='104' #INFO-38 Third-party library control
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def third_party_library_control(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'third_party_library_control':'Artifact allowlist configured'})
    else:
        return (check_id, 1, {'third_party_library_control':'No artifact allowlist configured'})   
if enabled:    
    tbl_name_1 = 'global_temp.artifacts_allowlists_library_jars' + '_' + workspace_id
    tbl_name_2 = 'global_temp.artifacts_allowlists_library_mavens' + '_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name_1} 
        UNION
        SELECT *
        FROM {tbl_name_2} 
        
    '''
    sqlctrl(workspace_id, sql, third_party_library_control)

# COMMAND ----------

tcomp = time.time() - start_time
print(f"Workspace Analysis - {tcomp} seconds to run")

# COMMAND ----------

check_id='103'# INFO-37,Informational,Compliance security profile for new workspaces
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def compliance_security_profile_account(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'compliance security profile setting for new workspaces':'True'})
    else:
        return (check_id, 1, {'compliance security profile setting for new workspaces':'False'})   
if enabled:    
    tbl_name = 'global_temp.account_csp'
    sql=f'''
        SELECT *
        FROM {tbl_name}  WHERE csp_enablement_account.is_enforced = true
        
    '''
    sqlctrl(workspace_id, sql, compliance_security_profile_account)

# COMMAND ----------

check_id='108'#INFO-39,Informational,Compliance security profile for the workspace
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def compliance_security_profile(df):
    if df is not None and not df.rdd.isEmpty():
        compliance_security_profile_list = df.collect()
        return (check_id, 0, {'compliance_standards':compliance_security_profile_list[0]})
    else:
        return (check_id, 1, {'compliance security profile setting for this workspace':'False'})   
if enabled:    
    tbl_name = 'global_temp.compliance_security_profile'+'_' + workspace_id
    sql=f'''
        SELECT compliance_security_profile_workspace
        FROM {tbl_name}  WHERE compliance_security_profile_workspace.is_enabled = true
        
    '''
    sqlctrl(workspace_id, sql, compliance_security_profile)

# COMMAND ----------

check_id='109'#INFO-40,Informational,Enhanced security monitoring for the workspace
enabled, sbp_rec = getSecurityBestPracticeRecord(check_id, cloud_type)

def enhanced_security_monitoring(df):
    if df is not None and not df.rdd.isEmpty():
        return (check_id, 0, {'enhanced security monitoring setting for this workspace':'True'})
    else:
        return (check_id, 1, {'enhanced security monitoring for this workspace':'False'})   
if enabled:    
    tbl_name = 'global_temp.enhanced_security_monitoring'+'_' + workspace_id
    sql=f'''
        SELECT *
        FROM {tbl_name}  WHERE enhanced_security_monitoring_workspace.is_enabled = true
        
    '''
    sqlctrl(workspace_id, sql, enhanced_security_monitoring)

# COMMAND ----------

dbutils.notebook.exit(f'Completed SAT workspace analysis in {tcomp} seconds')
