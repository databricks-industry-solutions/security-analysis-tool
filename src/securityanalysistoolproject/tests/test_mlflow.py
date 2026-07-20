from core.logging_utils import LoggingUtils
from clientpkgs.ml_flow_client import MLFlowClient

def test_get_experiments_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    experimentsList = mlFlowClient.get_experiments_list()
    LOGGR.debug(experimentsList)

def test_get_registered_models(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    registeredModels = mlFlowClient.get_registered_models()
    LOGGR.debug(registeredModels)

def test_get_list_artifacts(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    artifactsList = mlFlowClient.get_list_artifacts("43ef8a1846174ef4ac3dd8491500fd2c", "./")
    LOGGR.debug(artifactsList)

#may not be implemented
def test_search_for_runs(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    runsList = mlFlowClient.search_for_runs(["893528767666988"], "")
    LOGGR.debug(runsList)

def test_get_list_registry_webhooks(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    webhooksList = mlFlowClient.get_list_registry_webhooks("example_catalog.example_schema.basic_rag_demo")
    LOGGR.debug(webhooksList)

def test_get_list_transition_requests(get_db_client):
    from mlflow.tracking import MlflowClient
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    mlFlowClient = MLFlowClient(jsonstr)
    transitionRequests = mlFlowClient.get_list_transition_requests("example_catalog.example_schema.example_model", "1")
    LOGGR.debug(transitionRequests)