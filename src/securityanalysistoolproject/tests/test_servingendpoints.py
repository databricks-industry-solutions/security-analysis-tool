'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.serving_endpoints import ServingEndpoints
import requests
import pytest



def test_endpoints(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbservendobj = ServingEndpoints(jsonstr)
    endpointsList = dbservendobj.get_endpoints()
    print(endpointsList)

def test_getendpoint_byname(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbservendobj = ServingEndpoints(jsonstr)
    endpointlst = dbservendobj.get_endpoint_byname('yuki_shiga_workshop202404_machine_learning')
    print(endpointlst)

def test_getpermissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbservendobj = ServingEndpoints(jsonstr)
    permissionlst = dbservendobj.get_permissions_by_id('f2b3a072b3e542fe99c3f178a0494488')
    print(permissionlst)




