from core.logging_utils import LoggingUtils
from clientpkgs.ip_access_list import IPAccessClient

def test_get_ip_access_lists(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    ipAccessClient = IPAccessClient(jsonstr)
    ip_access_lists = ipAccessClient.get_ip_access_list()
    LOGGR.debug(ip_access_lists)

def test_get_ip_access_id(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    ipAccessClient = IPAccessClient(jsonstr)
    ip_access = ipAccessClient.get_ip_access("test_ip_access_list_id")
    LOGGR.debug(ip_access)