'''parser module for json'''
import json
import re
from itertools import cycle
from core.logging_utils import LoggingUtils #rkm changed
LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()

def set_defaults(args):
    '''set defaults if not detected in incoming json'''
    if 'url' not in args.keys():
        args.update({'url':''})
    if 'verbosity' not in args.keys():
        args.update({'verbosity':'info'})
    if 'client_id' not in args.keys():
        args.update({'client_id':''})
    if 'client_secret' not in args.keys():
        args.update({'client_secret':''})
    if 'maxpages' not in args.keys():
        args.update({'maxpages':10})
    if 'timebetweencalls' not in args.keys():
        args.update({'timebetweencalls':1})     
    # if 'use_sp_auth' not in args.keys():
    #     args.update({'use_sp_auth':False})

def url_validation(url):
    '''validate url patterns'''
    # pylint: disable=anomalous-backslash-in-string
    if '/?o=' in url:
        # if the workspace_id exists, lets remove it from the URL
        url = re.sub(r"/\?o=.*", '', url)
    # if '/?o=' in url:
    #     # if the workspace_id exists, lets remove it from the URL
    #     url = re.sub("\/\?o=.*", '', url)
    # elif 'net/' == url[-4:]:
    #     url = url[:-1]
    # elif 'com/' == url[-4:]:
    #     url = url[:-1]
    return url.rstrip("/")
    # pylint: enable=anomalous-backslash-in-string



def str2bool(vinput):
    '''convert string to bool'''
    return vinput.lower() in ("yes", "true", "t", "1")

#dummy values. Not real values

# {"account_id": "ccb842e7-2376", "sql_warehouse_id": "966f94",
#   "analysis_schema_name": "`hive_metastore`.security_analysis", "verbosity": "info", "proxies": {}, 
#   "intermediate_schema": "`hive_metastore`.intermediate_schema", 
#   "master_name_scope": "sat_scope", "master_name_key": "user", #used?
#   "master_pwd_scope": "sat_scope", "master_pwd_key": "pass",   #used?
#   "workspace_pat_scope": "sat_scope", "workspace_pat_token_prefix": "sat-token", #used?
#   "dashboard_id": "317f4812217", "dashboard_folder": "/Workspace/Users/ramdas.murali@databricks.com", 
#   "dashboard_tag": "SAT", "use_parallel_runs": true, "sat_version": "0.3.4", 
#   "subscription_id": "edd4cc45-85c7-4aec-8bf5-648062d519bf", 
#   "tenant_id": "bf465dc7-3bc8-4944-b018-092572b5c20d", 
#   "client_id": "2df864fe-30df-4f69-a680-967144bb1d09", 
#   "client_secret_key": "client-secret", 
#   "url": "https://adb-3850794576023421.1.azuredatabricks.net/", 
#   "workspace_id": "3836674955606356", "cloud_type": "azure", "clusterid": "0510-171242-vqha0apn", 
#   "sso": true, "scim": false, "object_storage_encryption": true, "vpc_peering": true, "table_access_control_enabled": false, 
#   "token": "dapijedi", #used?
#   "client_secret": "d"}
def parse_input_jsonargs(inp_configs):
    '''parse and validate incoming json string and return json'''
    if isinstance(inp_configs, str):
        inp_configs =json.loads(inp_configs)
    set_defaults(inp_configs)
    url = url_validation(inp_configs['url'])
    inp_configs.update({'url':url})

    if 'clusterid' in inp_configs and inp_configs['clusterid'] == '':
        raise ValueError('Cluster ID cannot be empty')

    return inp_configs

@staticmethod
def get_domain(url):
    '''get domain from url'''
    regex = r"https://.*databricks\.(.*?)/?$"
    match = re.match(regex, url)
    if match:
        domain = match.group(1)
        return domain
    raise ValueError('Invalid URL')
