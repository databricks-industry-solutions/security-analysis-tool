from core.logging_utils import LoggingUtils
from clientpkgs.apps_client import AppsClient

def test_list_apps(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    appsClient = AppsClient(jsonstr)
    appsList = appsClient.list_apps()
    LOGGR.debug(appsList)

def test_list_apps_deployments(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    appsClient = AppsClient(jsonstr)
    deploymentsList = appsClient.list_apps_deployments("wools-app")
    LOGGR.debug(deploymentsList)

def test_get_apps_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    appsClient = AppsClient(jsonstr)
    permissionsList = appsClient.get_apps_permissions("wools-app")
    LOGGR.debug(permissionsList)

def test_get_apps_permission_levels(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    appsClient = AppsClient(jsonstr)
    permissionLevels = appsClient.get_apps_permission_levels("wools-app")
    LOGGR.debug(permissionLevels)