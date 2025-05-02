from core.logging_utils import LoggingUtils
from clientpkgs.cleanrooms_client import CleanRoomsClient

def test_list_clean_rooms(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    cleanRoomsClient = CleanRoomsClient(jsonstr)
    cleanRoomsList = cleanRoomsClient.list_clean_rooms()
    LOGGR.debug(cleanRoomsList)

def test_get_clean_room_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    cleanRoomsClient = CleanRoomsClient(jsonstr)
    cleanRoomInfo = cleanRoomsClient.get_clean_room_info("retail_audience_overlap")
    LOGGR.debug(cleanRoomInfo)


def test_list_clean_room_task_runs(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    cleanRoomsClient = CleanRoomsClient(jsonstr)
    taskRunsList = cleanRoomsClient.list_clean_room_task_runs("retail_audience_overlap")
    LOGGR.debug(taskRunsList)