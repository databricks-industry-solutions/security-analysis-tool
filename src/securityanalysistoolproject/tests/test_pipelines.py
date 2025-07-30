from core.logging_utils import LoggingUtils
from clientpkgs.pipelines_client import PipelinesClient

def test_get_pipelines_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    permissions = pipelinesClient.get_pipelines_permissions("77de5050-84cb-46b8-b8f5-19014ca305d9")
    LOGGR.debug(permissions)

def test_get_pipelines_permission_levels(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    permissionLevels = pipelinesClient.get_pipelines_permission_levels("77de5050-84cb-46b8-b8f5-19014ca305d9")
    LOGGR.debug(permissionLevels)

def test_get_pipelines_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    pipelinesList = pipelinesClient.get_pipelines_list()
    LOGGR.debug(pipelinesList)

def test_get_pipeline(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    pipeline = pipelinesClient.get_pipeline("77de5050-84cb-46b8-b8f5-19014ca305d9")
    LOGGR.debug(pipeline)

def test_get_pipelines_events_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    eventsList = pipelinesClient.get_pipelines_events_list("77de5050-84cb-46b8-b8f5-19014ca305d9")
    LOGGR.debug(eventsList)

def test_get_pipelines_update_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    pipelinesClient = PipelinesClient(jsonstr)
    updatesList = pipelinesClient.get_pipelines_update_list("77de5050-84cb-46b8-b8f5-19014ca305d9", "c5b3caf9-54c1-42c8-b8f8-5717836a791e")
    LOGGR.debug(updatesList)