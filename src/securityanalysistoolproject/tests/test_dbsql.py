from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.dbsql_client import DBSQLClient

def test_get_alerts_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sqlendpoint_list()
    print(settingsList)

def test_get_alerts_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_alerts_list()
    print(settingsList)

def test_get_sql_warehouse_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_list()
    print(settingsList)

def test_get_sql_warehouse_listv2(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_listv2()
    print(settingsList)

def test_get_sql_workspace_config(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_workspace_config()
    print(settingsList)

    