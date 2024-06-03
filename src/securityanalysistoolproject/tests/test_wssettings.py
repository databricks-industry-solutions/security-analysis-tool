

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

def test_automatic_cluster_update(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    adminsetting = wsclient.get_automatic_cluster_update()
    print(adminsetting)

def test_compliance_security_profile(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    adminsetting = wsclient.get_compliance_security_profile()
    print(adminsetting)

def test_enhanced_security_monitoring(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    adminsetting = wsclient.get_enhanced_security_monitoring()
    print(adminsetting)

def test_default_namespace_setting(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    adminsetting = wsclient.get_default_namespace_setting()
    print(adminsetting)

def test_settings_restrictwa(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    adminsetting = wsclient.get_restrict_workspace_admin_settings()
    print(adminsetting)
