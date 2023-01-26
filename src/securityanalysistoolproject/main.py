'''testing'''
import sys
import configparser
import json
from core import parser as pars
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
import requests
import urllib3


#pylint: disable=unused-import
from clientpkgs.clusters_client import ClustersClient
from clientpkgs.dbfs_client import DbfsClient
from clientpkgs.scim_client import ScimClient
from clientpkgs.jobs_client import JobsClient
from clientpkgs.secrets_client import SecretsClient
from clientpkgs.accounts_client import AccountsClient
from clientpkgs.job_runs_client import JobRunsClient
from clientpkgs.pools_client import PoolsClient
from clientpkgs.ws_settings_client import WSSettingsClient
from clientpkgs.init_scripts_client import InitScriptsClient
from clientpkgs.libraries_client import LibrariesClient
from clientpkgs.ip_access_list import IPAccessClient
from clientpkgs.tokens_client import TokensClient
from clientpkgs.workspace_client import WorkspaceClient
from clientpkgs.azure_accounts_client import get_msal_token
#pylint: enable=unused-import


def main():
    configParser = configparser.ConfigParser()   
    configFilePath = '/Users/ramdas.murali/_dev_stuff/config.txt'
    configParser.read(configFilePath)
    jsonstr = configParser['MEISTERSTUFF']['json']
    workspace_id = json.loads(jsonstr)['workspace_id']
    LOGGR = LoggingUtils.get_logger()

    sat_db_client = SatDBClient(jsonstr)
    try:
        # is_successful = sat_db_client.test_connection()

        # if is_successful:
        #     LOGGR.info("Workspace Connection successful!")
        # else:
        #     LOGGR.info("Unsuccessful connection. Verify credentials.")

        # is_successful = sat_db_client.test_connection(master_acct=True)

        # if is_successful:
        #     LOGGR.info("Accunts API Connection successful!")
        # else:
        #     LOGGR.info("Unsuccessful connection. Verify credentials.")

        # origstr = '''{"FirstName":"Ram","LastName":"Murali1#$%$"}'''
        # str_var = pars.simple_sat_fn(origstr, workspace_id)
        # print(str_var)
        # str_var = pars.simple_sat_fn(str_var, workspace_id)
        # print(str_var)

        wsclient = WSSettingsClient(jsonstr)
        tokensList=wsclient.get_wssettings_list()
        print(tokensList)


        get_msal_token()
        acctClient = AccountsClient(jsonstr)
        lst = acctClient.get_workspace_list()
        print(lst)

        lst = acctClient.get_credentials_list()
        print(lst)

        lst = acctClient.get_network_list()
        print(lst)

        lst = acctClient.get_storage_list()
        print(lst)

        lst = acctClient.get_cmk_list()
        print(lst)

        lst = acctClient.get_logdelivery_list()
        print(lst)

        lst = acctClient.get_privatelink_info()
        print(lst)

        return
        # workspaceClient = WorkspaceClient(client_config)
        # notebookList = workspaceClient.get_all_notebooks()
        #notebookList = workspaceClient.get_list_notebooks('/Repos/ramdas.murali+tzar@databricks.com/CSE/gold/workspace_analysis/dev')
        # print(notebookList)
        # libClient = LibrariesClient(client_config)
        # libList = libClient.get_libraries_status_list()
        # print(libList)

        # secretsClient = SecretsClient(client_config)
        # scopeslist = secretsClient.get_secret_scopes_list()

        # secretslist = secretsClient.get_secrets(scopeslist)
        # print(secretslist)

        #acctClient = AccountsClient(client_config)
        #lst = acctClient.get_workspace_list()
        #lst = acctClient.get_privatelink_info()
        #print(lst)
        # initClient = InitScriptsClient(client_config)
        # scriptsList = initClient.get_allglobalinitscripts_list()
        # print(scriptsList)



        # dbfsclient = DbfsClient(client_config)
        # dirlist = dbfsclient.get_dbfs_directories('/user/hive/warehouse/')
        # print(dirlist)

        # dbfsmounts = dbfsclient.get_dbfs_mounts()
        # print(dbfsmounts)



        # wsclient = WSSettingsClient(client_config)
        # tokensList=wsclient.get_wssettings_list()
        # print(tokensList)


        # ipaccessClient = IPAccessClient(client_config)
        # iplist=ipaccessClient.get_ipaccess_list()
        # print(iplist)


        # tokensClient = TokensClient(client_config)
        # tokensList=tokensClient.get_tokens_list()
        # print(tokensList)


        # jobrunsClient = JobRunsClient(client_config)
        # lst = jobrunsClient.get_jobruns_list()
        # print(lst)

        # instancepoolsClient = PoolsClient(client_config)
        # lst = instancepoolsClient.get_pools_list()
        # print(lst)


        # acctClient = AccountsClient(client_config)
        # lst = acctClient.get_privatelink_info()
        # lst = acctClient.get_workspace_list()
        # print(lst)
        # lst = acctClient.get_credentials_list()
        # print(lst)
        # lst = acctClient.get_network_list()
        # print(lst)
        # lst = acctClient.get_storage_list()
        # print(lst)
        # lst = acctClient.get_cmk_list()
        # print(lst)
        # lst = acctClient.get_logdelivery_list()
        # print(lst)

        #Azure
        acctClient = AzureAccountsClient(jsonstr)
        lst = acctClient.get_workspace_list()
        print(lst)

        # clusterClient = ClustersClient(client_config)
        # clusterLst = clusterClient.get_cluster_list(alive=False)
        # print(clusterLst)
        # clusterLst2 = clusterClient.get_cluster_acls("1234-204226-yq5nnyt7", '')
        # clusterLst3 = clusterClient.get_cluster_id_by_name('rkmjdbc')
        # clusterLst4 = clusterClient.get_global_init_scripts()
        # clusterLst5 = clusterClient.get_instance_pools()
        # clusterLst6 = clusterClient.get_spark_versions()
        # clusterLst7 = clusterClient.get_instance_profiles_list()
        # clusterLst8 = clusterClient.get_iam_role_by_cid('1234-090100-bait793')
        # clusterLst9 = clusterClient.get_policies()
        # print('spark3:' + str(clusterClient.is_spark_3('1234-090100-bait793')))
        # #clusterClient.start_cluster_by_name('at&t_test')

        # #print(clusterLst9)
        # dbfsClient = DbfsClient(client_config)
        # lst = dbfsClient.get_dbfs_mounts(cid='1234-090100-bait793')
        # #for jsonobj in lst:
        # #    print(jsonobj['path'] + "---->" + jsonobj['source'])
        # jobsClient = JobsClient(client_config)
        # joblist = jobsClient.get_jobs_list()
        # #print(joblist)
        # scimClient = ScimClient(client_config)
        # users = scimClient.get_users()
        # #print(users)
        # groups = scimClient.get_groups()
        # #print(groups)

        # secretsClient = SecretsClient(client_config)
        # scopeslist = secretsClient.get_secret_scopes_list()
   
        # #print(scopeslist)
        # for scope in scopeslist:
        #     secretslist = secretsClient.get_secrets(scope['name'])
        #     #print(secretslist)

    except requests.exceptions.RequestException:
        LOGGR.exception('Unsuccessful connection. Verify credentials.')
        sys.exit(1)
    except Exception:
        LOGGR.exception("Exception encountered")






if __name__ == '__main__':
    main()




