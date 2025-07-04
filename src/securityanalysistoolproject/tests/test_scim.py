from core.logging_utils import LoggingUtils
from clientpkgs.scim_client import ScimClient

def test_get_users(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    scimClient = ScimClient(jsonstr)
    usersList = scimClient.get_users()
    LOGGR.debug(usersList)

def test_get_groups(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    scimClient = ScimClient(jsonstr)
    groupsList = scimClient.get_groups()
    LOGGR.debug(groupsList)

def test_get_serviceprincipals(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    scimClient = ScimClient(jsonstr)
    spnList = scimClient.get_serviceprincipals()
    LOGGR.debug(spnList)

def test_get_userdetails(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    scimClient = ScimClient(jsonstr)
    userDetails = scimClient.get_userdetails("test_user_id")
    LOGGR.debug(userDetails)