'''pools client module'''
from core.dbclient import SatDBClient

class PoolsClient(SatDBClient):
    '''pools helper'''

    def get_pools_list(self):
        """
        Returns an array of json objects for poolslist
        """
        # fetch all poolslist
        poolslist = self.get("/instance-pools/list", version='2.0').get('instance_pools', [])
        return poolslist
