
import pytest
import configparser
import json

from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient

@pytest.fixture(scope="session")
def get_db_client():
    configParser = configparser.ConfigParser()   
    configFilePath = '/Users/ramdas.murali/_dev_stuff/config.txt'
    configParser.read(configFilePath)
    jsonstr = configParser['MEISTERSTUFF']['json']
    json_ = json.loads(jsonstr)

    #workspace_id = json_['workspace_id']
    LoggingUtils.set_logger_level(LoggingUtils.get_log_level(json_['verbosity']))
    LOGGR = LoggingUtils.get_logger()
    LOGGR.info(jsonstr)
    #sat_db_client = SatDBClient(jsonstr)
    return jsonstr
