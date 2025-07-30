from core.logging_utils import LoggingUtils
from clientpkgs.tokens_client import TokensClient

def test_get_tokens_list_mgmt(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    tokensClient = TokensClient(jsonstr)
    tokensListMgmt = tokensClient.get_tokens_list_mgmt()
    LOGGR.debug(tokensListMgmt)

def test_get_token(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    tokensClient = TokensClient(jsonstr)
    tokenInfo = tokensClient.get_token("test_token_id")
    LOGGR.debug(tokenInfo)

def test_get_tokens_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    tokensClient = TokensClient(jsonstr)
    tokensList = tokensClient.get_tokens_list()
    LOGGR.debug(tokensList)