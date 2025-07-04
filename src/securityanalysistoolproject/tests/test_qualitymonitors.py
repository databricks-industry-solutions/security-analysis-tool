'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.qualitymonitors_client import QualityMonitors
import requests
import pytest



def test_get_monitors(get_db_client):
    tbl='main.security_analysis.account_info'
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info('---------------------')    
    jsonstr = get_db_client
    qmobj = QualityMonitors(jsonstr)
    artifactsList = qmobj.get_monitors(tbl)
    print(artifactsList)

