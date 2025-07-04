from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.dbsql_client import DBSQLClient


def test_get_alerts_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_alerts_list()
    print(settingsList)

def test_get_alert(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr) 
    settingsList = dbsqlobj.get_alert('1f33040c-4ca6-4971-afc0-bff88df620da')
    print(settingsList)

def test_get_sql_warehouse_configuration(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_configuration()
    print(settingsList)

def test_get_sql_warehouse_listv2(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_listv2()
    print(settingsList)

def test_get_sql_warehouse(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_info('7385da041ce9b8f6')
    print(settingsList)

def test_get_queries_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_queries_list( )
    print(settingsList)


def test_get_query(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_query('70b0f51e-3dfe-4818-8b9f-fb9fe21577d3')
    print(settingsList)

def test_get_query_history(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_query_history()
    print(settingsList)

