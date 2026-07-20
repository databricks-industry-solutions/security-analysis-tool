'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.unity_catalog_client import UnityCatalogClient
import requests
import pytest



def test_artifact_allowlist(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_artifacts_allowlists('INIT_SCRIPT')
    print(artifactsList)
    artifactsList = unitycatalogobj.get_artifacts_allowlists('LIBRARY_JAR')
    print(artifactsList)    
    artifactsList = unitycatalogobj.get_artifacts_allowlists('LIBRARY_MAVEN')
    print(artifactsList)



def test_get_catalogs_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_catalogs_list()
    print(artifactsList)    

def test_get_catalog(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_catalog('example_catalog')
    print(artifactsList)    

def test_get_connections(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_connections_list()
    print(artifactsList)  

def test_get_connection(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_connection('example_connection')
    print(artifactsList)  

def test_get_external_locations(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_external_locations()
    print(artifactsList)  

def test_get_external_location(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_external_location('example-external-location-storage')
    print(artifactsList)      

def test_get_functions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_functions('feature_function_underscore', 'dbdemos_fs_travel')
    print(artifactsList)  

def test_get_function(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_function('feature_function_underscore.dbdemos_fs_travel.distance_udf')
    print(artifactsList)  

def test_get_grants_effective_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_grants_effective_permissions('catalog', 'example_catalog')
    print(artifactsList)  

def test_get_grants_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_grants_permissions('CATALOG', 'example_catalog')
    print(artifactsList)  

def test_get_table_monitor(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_table_monitor('example_catalog.example_monitor.parts')
    print(artifactsList)  

def test_get_workspace_metastore_assignments(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_workspace_metastore_assignments()
    print(artifactsList)      

def test_get_workspace_metastore_summary(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_workspace_metastore_summary()
    print(artifactsList)    

#user needs to be an account admin
def test_get_metastore_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_metastore_list()
    print(artifactsList)    

def test_get_model_versions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_model_versions('example_catalog.models.example_model')
    print(artifactsList)    

def test_get_model_version(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_model_version('example_catalog.models.example_model','3')
    print(artifactsList)    

def test_get_online_table(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_online_table('example_catalog.models.example_model')
    print(artifactsList)    

def test_get_registered_models(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_registered_models()
    print(artifactsList)    

def test_get_registered_model(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_registered_model('example_catalog.example_schema.dbdemos_chatbot_model')
    print(artifactsList)   

def test_get_schemas_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_schemas_list('example_catalog')
    print(artifactsList)    

def test_get_schema(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_schema('example_catalog', 'example_schema')
    print(artifactsList)  

def test_get_credentials(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_credentials()
    print(artifactsList)  

def test_get_credential(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_credential('example_credential')
    print(artifactsList)  

def test_get_tablesummaries(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_tablesummaries(catalog_name='example_catalog', schema_name='exam*', table_name=None, page_token=None)
    print(artifactsList)  


def test_get_tables(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_tables(catalog_name='example_catalog', schema_name='example_schema', page_token='', include_delta_metadata='true', omit_columns='', omit_properties='', include_browse='')
    print(artifactsList)    

def test_get_table(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_table('example_catalog.example_schema.logistics_table')
    print(artifactsList)    

def test_get_volumes(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_volumes(catalog_name='example_catalog', schema_name='example_schema', page_token='', include_browse='true')
    print(artifactsList)    

def test_get_volume(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_volume('example_catalog.example_schema.init_script_volume')
    print(artifactsList)    
    
#the user should have account admin privileges
def get_grants_effective_permissions_ext(self):
    arrperms=[]
    arrlist = self.get_metastore_list()
    for meta in arrlist:
        metastore_id = meta['metastore_id']
        effperms = self.get_grants_effective_permissions('METASTORE', metastore_id)
        for effpermselem in effperms:
            effpermselem['metastore_id'] = meta['metastore_id']
            effpermselem['metastore_name'] = meta['name']
        arrperms.extend(effperms)
    jsonarr = json.dumps(arrperms)
    return arrperms


def test_get_grants_effective_permissions_ext(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')
    jsonstr = get_db_client
    unitycatalogobj = UnityCatalogClient(jsonstr)
    artifactsList = unitycatalogobj.get_grants_effective_permissions_ext()
    print(artifactsList)  