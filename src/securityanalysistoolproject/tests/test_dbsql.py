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
    settingsList = dbsqlobj.get_alert('aa69d805-7821-4923-8197-02f3574b31f3')
    print(settingsList)

def test_get_dashboards_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_dashboards_list(page_size='25', page='1', order='name', q='')
    print(settingsList)

def test_get_dashboard(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_dashboard(dashboard_id='6c76b851-0d29-4329-a082-b4b8ad331ba0')
    print(settingsList)

def test_get_sql_warehouse_permission(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_permissions(warehouse_id='475b94ddc7cd5211')
    print(settingsList)

def test_get_sql_warehouse_permission_level(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_warehouse_permission_level(warehouse_id='475b94ddc7cd5211')
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
    settingsList = dbsqlobj.get_sql_warehouse(warehouseid='38c315c073481654')
    print(settingsList)

def test_get_sql_acl(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_sql_acl(objectType='alerts',objectId='aa69d805-7821-4923-8197-02f3574b31f3' )
    print(settingsList)

def test_get_queries_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_queries_list(order='name', page='1',page_size='25', q='' )
    print(settingsList)

def test_get_querydefinition(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_querydefinition(query_id='ed45e6b0-d6f7-43b3-a60a-dae44023c994')
    print(settingsList)

def test_get_query_history(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    dbsqlobj = DBSQLClient(jsonstr)
    settingsList = dbsqlobj.get_query_history(filter_by='', include_metrics='true', max_results='10', page_token='')
    print(settingsList)

