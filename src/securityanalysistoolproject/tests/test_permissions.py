from core.logging_utils import LoggingUtils
from clientpkgs.permissions_client import UserGroupObjectsClient

def test_get_warehouse_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    permissionsClient = UserGroupObjectsClient(jsonstr)
    out = permissionsClient.get_object_permissions(request_object_type='warehouses', request_object_id='0c54acf921fdd04f')
    LOGGR.debug(f"{out}")


def test_get_warehouse_permission_levels(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    permissionsClient = UserGroupObjectsClient(jsonstr)
    out = permissionsClient.get_object_permission_levels(request_object_type='warehouses', request_object_id='0c54acf921fdd04f')
    LOGGR.debug(f"{out}")


def test_list_assign_resources(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    permissionsClient = UserGroupObjectsClient(jsonstr)
    out = permissionsClient.list_assign_resources()
    LOGGR.debug(f"{out}")



