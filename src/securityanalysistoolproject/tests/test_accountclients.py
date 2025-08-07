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



def test_get_workspace_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    workspaceList = accountsClient.get_workspace_list()
    LOGGR.debug(workspaceList)

def test_get_credentials_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    credentialsList = accountsClient.get_credentials_list()
    LOGGR.debug(credentialsList)

def test_get_storage_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    storageList = accountsClient.get_storage_list()
    LOGGR.debug(storageList)

def test_get_cmk_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    cmkList = accountsClient.get_cmk_list()
    LOGGR.debug(cmkList)

def test_get_logdelivery_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    logDeliveryList = accountsClient.get_logdelivery_list()
    LOGGR.debug(logDeliveryList)

def test_get_privatelink_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    privateLinkInfo = accountsClient.get_privatelink_info()
    LOGGR.debug(privateLinkInfo)

def test_get_azure_subscription_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    azureSubscriptionList = accountsClient.get_azure_subscription_list()
    LOGGR.debug(azureSubscriptionList)

def test_get_azure_resource_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    azureResourceList = accountsClient.get_azure_resource_list("test_url_from_subscription")
    LOGGR.debug(azureResourceList)

def test_get_azure_diagnostic_logs(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsClient(jsonstr)
    azureDiagnosticLogs = accountsClient.get_azure_diagnostic_logs([], '5635596728267912') #'5635596728267912'
    LOGGR.debug(azureDiagnosticLogs)