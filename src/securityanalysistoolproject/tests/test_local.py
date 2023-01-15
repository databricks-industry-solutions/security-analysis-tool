from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.workspace_client import WorkspaceClient
from clientpkgs.scim_client import ScimClient
from clientpkgs.ws_settings_client import WSSettingsClient

def test_workspace_settings(get_db_client):
    LOGGR = LoggingUtils.get_logger()

    jsonstr = get_db_client 
    workspaceClient = WSSettingsClient(jsonstr)
    settingsList = workspaceClient.get_wssettings_list()
    print(settingsList)
