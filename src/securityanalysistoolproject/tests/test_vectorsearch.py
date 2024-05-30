'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.vector_search import VectorSearch
import requests
import pytest



def test_getendpoints(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbvectorobj = VectorSearch(jsonstr)
    
    endpointsList = dbvectorobj.get_endpoint_list()
    print(endpointsList)

def test_getendpoint_byname(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbvectorobj = VectorSearch(jsonstr)
    
    endpointlst = dbvectorobj.get_endpoint('one-env-shared-endpoint-6')
    print(endpointlst)

def test_getindices(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbvectorobj = VectorSearch(jsonstr)
    
    indexlst = dbvectorobj.get_index_list('one-env-shared-endpoint-6')
    print(indexlst)

def test_getindex(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbvectorobj = VectorSearch(jsonstr)
    
    endpointlst = dbvectorobj.get_index('fsi.ccr.orders_index_ks')
    print(endpointlst)



