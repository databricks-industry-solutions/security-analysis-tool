'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.accounts_settings import AccountsSettings
import requests




def test_get_ipaccess_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountobj = AccountsSettings(jsonstr)
    
    ipaccessList = accountobj.get_ipaccess_list()
    print(ipaccessList)


def test_get_compliancesecurityprofile(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountobj = AccountsSettings(jsonstr)
    
    csplist = accountobj.get_compliancesecurityprofile()
    print(csplist)

def test_get_networkconnectivityconfigurations(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountobj = AccountsSettings(jsonstr)
    ncclist = accountobj.get_networkconnectivityconfigurations()
    print(ncclist)


