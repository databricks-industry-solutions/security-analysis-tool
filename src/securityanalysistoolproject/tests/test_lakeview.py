from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.lakeview_client import LakeviewClient


def test_get_dashboard(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    lakeviewobj = LakeviewClient(jsonstr)
    lakeviewdash = lakeviewobj.get_dashboard(dashboard_id='01f0167f69821271b5a7d7800400dbfd')
    print(lakeviewdash)

def test_get_dashboards_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    lakeviewobj = LakeviewClient(jsonstr)
    lakeviewdash = lakeviewobj.get_dashboards_list()
    print(lakeviewdash)


def test_get_dashboards_schedules(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    lakeviewobj = LakeviewClient(jsonstr)
    lakeviewdash = lakeviewobj.get_dashboards_schedules(dashboard_id='01f0167f69821271b5a7d7800400dbfe')
    print(lakeviewdash)

