'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
import pytest
from clientpkgs.workspace_client import WorkspaceClient

CONFIGPATH='/Users/ramdas.murali/_dev_stuff/config.txt'
def test_encryption():
    configParser = configparser.ConfigParser()   
    configFilePath = CONFIGPATH
    configParser.read(configFilePath)
    jsonstr = configParser['MEISTERSTUFF']['json']
    json_ = json.loads(jsonstr)
    workspace_id = json_['workspace_id']
    LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
    LOGGR = LoggingUtils.get_logger()

    origstr = '''{"FirstName":"Ram","LastName":"Murali1#$%$"}'''
    str_var = pars.simple_sat_fn(origstr, workspace_id)
    print(str_var)
    str_var2 = pars.simple_sat_fn(str_var, workspace_id)
    assert origstr == str_var2

def test_workspace():
    configParser = configparser.ConfigParser()   
    configFilePath = CONFIGPATH
    configParser.read(configFilePath)
    jsonstr = configParser['MEISTERSTUFF']['json']
    json_ = json.loads(jsonstr)
    #workspace_id = json_['workspace_id']
    LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
    LOGGR = LoggingUtils.get_logger()

    sat_db_client = SatDBClient(json_)    
    workspaceClient = WorkspaceClient(json_)
    notebookList = workspaceClient.get_all_notebooks()
    notebookListspecific = workspaceClient.get_list_notebooks('/Repos/ramdas.murali+tzar@databricks.com/CSE/gold/workspace_analysis/dev')
    print(notebookList)
    print(notebookListspecific)