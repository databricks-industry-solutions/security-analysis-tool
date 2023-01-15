'''testing'''
### Run from terminal with pytest -s


from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.workspace_client import WorkspaceClient
from clientpkgs.scim_client import ScimClient
from clientpkgs.accounts_client import AccountsClient

def test_workspace(get_db_client):
    LOGGR = LoggingUtils.get_logger()

    jsonstr = get_db_client 
    workspaceClient = WorkspaceClient(jsonstr)
    notebookList = workspaceClient.get_all_notebooks()
    notebookListspecific = workspaceClient.get_list_notebooks('/Repos/ramdas.murali+tzar@databricks.com/CSE/gold/workspace_analysis/dev')
    print(notebookList)
    print(notebookListspecific)


def test_scim(get_db_client):
    jsonstr = get_db_client
    scimClient = ScimClient(jsonstr)
    groups = scimClient.get_groups()
    users = scimClient.get_users()
    spns = scimClient.get_serviceprincipals()
    print('--groups--')
    print(groups)
    print('--users--')
    print(users)
    print('--spns--')
    print(spns)

def test_azure_ws(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    wslist = azure_accounts.get_workspace_list()
    print(wslist)

 
def test_azure_storage(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    wslist = azure_accounts.get_storage_list()
    print(wslist)    

def test_azure_network(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    wslist = azure_accounts.get_network_list()
    print(wslist)    

def test_azure_cmk(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    wslist = azure_accounts.get_cmk_list()
    print(wslist)      


def test_azure_pvtlink(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    wslist = azure_accounts.get_privatelink_info()
    print(wslist)  

def test_azure_diag(get_db_client):
    jsonstr = get_db_client
    azure_accounts = AccountsClient(jsonstr)
    diaglist = azure_accounts.get_logdelivery_list()
    print(len(diaglist))
    print(diaglist)      