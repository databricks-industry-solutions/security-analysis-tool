

from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.ws_settings_client import WSSettingsClient

def test_ws_settings_globalinitscripts(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WSSettingsClient(jsonstr)
    tokensList=wsclient.get_wssettings_list()
    LOGGR.debug(tokensList)


def test_get_wssettings_listv2(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsSettingsClient = WSSettingsClient(jsonstr)
    wsSettingsListV2 = wsSettingsClient.get_wssettings_listv2()
    LOGGR.debug(wsSettingsListV2)

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





def test_get_aibi_dashboard_embedding_policy(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsSettingsClient = WSSettingsClient(jsonstr)
    embeddingPolicy = wsSettingsClient.get_aibi_dashboard_embedding_policy()
    LOGGR.debug(embeddingPolicy)

def test_get_aibi_dashboard_approved_host_embedding_policy(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsSettingsClient = WSSettingsClient(jsonstr)
    approvedHostPolicy = wsSettingsClient.get_aibi_dashboard_approved_host_embedding_policy()
    LOGGR.debug(approvedHostPolicy)


def test_get_legacy_access_disablement_setting(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsSettingsClient = WSSettingsClient(jsonstr)
    legacyAccessDisablement = wsSettingsClient.get_legacy_access_disablement_setting()
    LOGGR.debug(legacyAccessDisablement)

