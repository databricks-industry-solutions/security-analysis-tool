'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
import requests
import pytest

def test_connection():
    configParser = configparser.ConfigParser()   
    configFilePath = '/Users/ramdas.murali/_dev_stuff/config.txt'
    configParser.read(configFilePath)
    jsonstr = configParser['MEISTERSTUFF']['json']
    json_ = json.loads(jsonstr)
    #workspace_id = json_['workspace_id']
    LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
    LOGGR = LoggingUtils.get_logger()

    sat_db_client = SatDBClient(jsonstr)
    try:
        is_successful = sat_db_client.test_connection()

        if is_successful:
            print('connection success')
            LOGGR.info("Connection successful!")
        else:
            LOGGR.info("Unsuccessful connection. Verify credentials.")

        is_successful = sat_db_client.test_connection(master_acct=True)

        if is_successful:
            LOGGR.info("Connection successful!")
        else:
            pytest.fail('Connection Failed')
            LOGGR.info("Unsuccessful connection. Verify credentials.")    
    except requests.exceptions.RequestException:
        pytest.fail('Connection Failed')
        LOGGR.exception('Unsuccessful connection. Verify credentials.')

    except Exception:
        pytest.fail('Connection Failed')
        LOGGR.exception("Exception encountered")


