

from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.ws_settings_client import WSSettingsClient

def test_ws_settings_globalinitscripts(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    tokensList=wsclient.get_wssettings_list()
    print(tokensList)
