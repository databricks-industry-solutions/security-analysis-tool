from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.dbsql_client import DBSQLClient


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

def test_get_query_history(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_query_history()
    print(settingsList)

