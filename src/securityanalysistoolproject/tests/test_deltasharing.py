'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.delta_sharing import DeltaSharingClient
import requests
import pytest

def test_get_sharing_providers_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_sharing_providers_list()
    print(artifactsList) 

def test_get_sharing_provider(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_sharing_provider('americanairlines')
    print(artifactsList) 

def test_get_sharing_recepients_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_sharing_recepients_list()
    print(artifactsList)    

def test_get_sharing_recepient(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_sharing_recepient('aaron_binns_metronome_contigname_1')
    print(artifactsList)  

def test_get_sharing_recepient_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_sharing_recepient_permissions('aaron_binns_metronome_contigname_1')
    print(artifactsList)  

def test_get_list_shares(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_list_shares()
    print(artifactsList)    

def test_get_share(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_share('americanairlines')
    print(artifactsList)   

def test_get_share_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    deltasharingobj = DeltaSharingClient(jsonstr)
    artifactsList = deltasharingobj.get_share_permissions('americanairlines')
    print(artifactsList)   

