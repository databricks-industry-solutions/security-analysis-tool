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
    deploymentsList = appsClient.list_apps_deployments("data-app")
    LOGGR.debug(deploymentsList)
