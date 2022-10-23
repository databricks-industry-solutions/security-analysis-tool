'''ip access list module'''
from core.dbclient import SatDBClient

class IPAccessClient(SatDBClient):
    ''' ip access list helper'''

    def get_ipaccess_list(self):
        """
        Returns an array of json objects for ip access list.
        """
        # fetch all jobsruns
        endpointslist = self.get("/ip-access-lists", version='2.0').get('ip_access_lists', [])
        return endpointslist
