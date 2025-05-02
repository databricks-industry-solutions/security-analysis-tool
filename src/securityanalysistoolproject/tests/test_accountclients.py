'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.accounts_client import AccountsClient
import requests




def test_get_network_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountobj = AccountsClient(jsonstr)
    
    ipaccessList = accountobj.get_network_list()
    print(ipaccessList)
