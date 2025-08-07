from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.lakeview_client import LakeviewClient


def test_get_dashboard(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    lakeviewobj = LakeviewClient(jsonstr)
    lakeviewdash = lakeviewobj.get_dashboard(dashboard_id='01f026c8c8071c359181a73be3869819')
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
    lakeviewdash = lakeviewobj.get_dashboards_schedules(dashboard_id='01f026d2c9811a9ab91b97c2263a7ae4')
    print(lakeviewdash)

