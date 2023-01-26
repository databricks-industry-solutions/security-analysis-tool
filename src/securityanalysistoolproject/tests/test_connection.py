'''testing'''
### Run from terminal with pytest -s

import configparser
import json
from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
import requests
import pytest

def test_connection(get_db_client):

    LOGGR = LoggingUtils.get_logger()

    sat_db_client = SatDBClient(get_db_client)
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



