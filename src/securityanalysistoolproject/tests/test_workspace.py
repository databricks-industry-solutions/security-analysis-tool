from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.workspace_client import WorkspaceClient

def test_get_list_notebooks(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WorkspaceClient(jsonstr)
    notebookList=wsclient.get_list_notebooks('/Workspace/Users/ramdas.murali@databricks.com')
    print(notebookList)



def test_get_workspace_object_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    wsclient = WorkspaceClient(jsonstr)
    wsList=wsclient.get_workspace_object_permissions('notebooks', '4313537760981963')
    print(wsList)