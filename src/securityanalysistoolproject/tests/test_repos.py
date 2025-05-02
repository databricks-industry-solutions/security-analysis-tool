from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.repos_client import ReposClient


def test_get_repos_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    reposclient = ReposClient(jsonstr)
    reposres = reposclient.get_repos_list()
    print(reposres)


def test_get_git_credentials_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    reposclient = ReposClient(jsonstr)
    reposres = reposclient.get_git_credentials_list()
    print(reposres)

def test_get_repo_permission_levels(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    reposclient = ReposClient(jsonstr)
    reposres = reposclient.get_repo_permission_levels(4487195817655805)
    print(reposres)

def test_get_repo(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    reposclient = ReposClient(jsonstr)
    reposres = reposclient.get_repo(4487195817655805)
    print(reposres)