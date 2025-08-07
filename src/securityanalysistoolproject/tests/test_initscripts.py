from core.logging_utils import LoggingUtils
from clientpkgs.init_scripts_client import InitScriptsClient

def test_get_allglobalinitscripts_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    initScriptsClient = InitScriptsClient(jsonstr)
    globalInitScriptsList = initScriptsClient.get_allglobalinitscripts_list()
    LOGGR.debug(globalInitScriptsList)

def test_get_global_initscript(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    initScriptsClient = InitScriptsClient(jsonstr)
    globalInitScript = initScriptsClient.get_global_initscript("test_script_id")
    LOGGR.debug(globalInitScript)