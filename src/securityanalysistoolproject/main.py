'''testing'''
import sys
import configparser
import json
from core import parser as pars
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
import requests
import msal
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

    except requests.exceptions.RequestException:
        LOGGR.exception('Unsuccessful connection. Verify credentials.')
        sys.exit(1)
    except Exception:
        LOGGR.exception("Exception encountered")






if __name__ == '__main__':
    main()




