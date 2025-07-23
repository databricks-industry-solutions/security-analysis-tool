'''pools client module'''
from core.dbclient import SatDBClient

class PoolsClient(SatDBClient):
    '''pools helper'''

    def get_pools_list(self):
        """
        Returns an array of json objects for poolslist
        """
        # fetch all poolslist
        poolslist = self.get(f"/instance-pools/list", version='2.0').get('instance_pools', [])
        return poolslist


    
    def get_instance_pool_information(self, instance_pool_id):
        """
        Returns an array of json objects for poolslist
        """
        # fetch all poolslist
        json_params = {'instance_pool_id': instance_pool_id}
        poolinfo = self.get(f"/instance-pools/get", json_params=json_params, version='2.0').get('satelements', [])
        return poolinfo
    
    # permissions are implemented in the permissions_client.py
    # def get_pool_permissions(self, instance_pool_id):
    #     """
    #     Returns an array of json objects for poolslist
    #     """
    #     # fetch all poolslist
    #     poolperms = self.get(f"/permissions/instance-pools/{instance_pool_id}", version='2.0').get('access_control_list', [])
    #     return poolperms


    # def get_pool_permission_levels(self, instance_pool_id):
    #     """
    #     Returns an array of json objects for poolslist
    #     """
    #     # fetch all poolslist
    #     poolpermlevels = self.get(f"/permissions/instance-pools/{instance_pool_id}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return poolpermlevels