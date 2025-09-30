'''ip access list module'''
from core.dbclient import SatDBClient

class IPAccessClient(SatDBClient):
    ''' ip access list helper'''

    def get_ip_access_list(self):
        """
        Returns an array of json objects for compliance security profile update.
        """
        # fetch all endpoints
        endpointlist= self.get(f"/ip-access-lists", version='2.0').get('ip_access_lists', [])
        return endpointlist  

    def get_ip_access(self, ip_access_list_id):
        """
        Returns an array of json objects for compliance security profile update.
        """
        # fetch all endpoints
        endpointlist= self.get(f"/ip-access-lists/{ip_access_list_id}", version='2.0').get('ip_access_list', [])
        return endpointlist      