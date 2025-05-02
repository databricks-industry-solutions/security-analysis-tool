from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.unity_catalog_client import UnityCatalogClient

def test_get_catalogs_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    settingsList = catalogslist.get_catalogs_list()
    print(settingsList)

def test_get_schemas_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_schemas_list('akangsha_catalog')
    print(sList)  
    sList = catalogslist.get_schemas_list('nonexistentcat')
    print(sList)  

def test_get_tables(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_tables('akangsha_catalog', 'akangsha_schema')
    print(sList)      

def test_get_functions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_functions('akangsha_catalog', 'akangsha_schema')
    print(sList)

def test_get_external_locations(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_external_locations()
    print(sList)


def test_get_workspace_metastore_assignments(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_workspace_metastore_assignments()
    print(sList)      

def test_get_workspace_metastore_summary(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_workspace_metastore_summary()
    print(sList)     

#account admin
def test_get_metastore_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_metastore_list()
    print(sList)   

def test_credentials(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    sList = catalogslist.get_credentials()
    print(sList)   
           
#not implemented           
def test_grants_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    #guid of metastore
    sList = catalogslist.get_grants_permissions('METASTORE', 'b169b504-4c54-49f2-bc3a-adf4b128f36d')
    print('--------------------')
    print(sList)

def test_grants_effective_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    #guid of metastore
    sList = catalogslist.get_grants_effective_permissions('METASTORE', 'b169b504-4c54-49f2-bc3a-adf4b128f36d')
    print('--------------------')
    print(sList) 

#account admin
def test_grants_effective_permissions_ext(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    catalogslist = UnityCatalogClient(jsonstr)
    #guid of metastore
    sList = catalogslist.get_grants_effective_permissions_ext()
    print('--------------------')
    print(sList) 