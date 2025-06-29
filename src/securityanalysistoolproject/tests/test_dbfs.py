from core.logging_utils import LoggingUtils
from clientpkgs.dbfs_client import DbfsClient

def test_get_num_of_lines():
    LOGGR = LoggingUtils.get_logger()
    num_lines = DbfsClient.get_num_of_lines("test_file.txt")
    LOGGR.debug(f"Number of lines in file: {num_lines}")

def test_get_dbfs_mounts(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbfsClient = DbfsClient(jsonstr)
    dbfsMounts = dbfsClient.get_dbfs_mounts()
    LOGGR.debug(dbfsMounts)

def test_get_dbfs_directories(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    dbfsClient = DbfsClient(jsonstr)
    dbfsDirectories = dbfsClient.get_dbfs_directories("/mnt/rkmmnt")
    LOGGR.debug(dbfsDirectories)


  