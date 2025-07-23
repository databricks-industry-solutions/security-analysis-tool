from core.logging_utils import LoggingUtils
from clientpkgs.managed_libraries_client import ManagedLibrariesClient

def test_get_library_statuses_all_clusters(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    managedLibrariesClient = ManagedLibrariesClient(jsonstr)
    libraryStatuses = managedLibrariesClient.get_library_statuses()
    LOGGR.debug(libraryStatuses)

def test_get_library_statuses_by_cluster(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    managedLibrariesClient = ManagedLibrariesClient(jsonstr)
    libraryStatuses = managedLibrariesClient.get_library_status("0709-132523-cnhxf2p6")
    LOGGR.debug(libraryStatuses)