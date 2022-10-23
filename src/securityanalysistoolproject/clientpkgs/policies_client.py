'''Policies client module'''
from core.dbclient import SatDBClient

class PoliciesClient(SatDBClient):
    '''policies client helper'''

    def get_policies_list(self):
        """
        Returns an array of json objects for policies
        """
        # fetch all policies
        poolslist = self.get("/policies/clusters/list", version='2.0').get('policies', [])
        return poolslist
