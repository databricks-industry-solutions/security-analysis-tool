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
            LOGGR.info("Workspace Connection successful!")
        else:
            LOGGR.info("Unsuccessful connection. Verify credentials.")

        is_successful = sat_db_client.test_connection(master_acct=True)

        if is_successful:
            LOGGR.info("Account Connection successful!")
        else:
            pytest.fail('Account Connection Failed')
            LOGGR.info("Unsuccessful connection. Verify credentials.")    
    except requests.exceptions.RequestException as e:
        pytest.fail('Connection Failed')
        LOGGR.exception(f'Unsuccessful connection. Verify credentials.{e}')

    except Exception:
        pytest.fail('Connection Failed')
        LOGGR.exception(f"Exception encountered {e}")



