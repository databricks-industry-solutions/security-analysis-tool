'''libraries client module'''
from core.dbclient import SatDBClient

class LibrariesClient(SatDBClient):
    '''libraries client module'''

    def get_libraries_status_list(self):
        """
        Returns an array of json objects for library status
        """
        # fetch all libraries
        librarieslist = self.get("/libraries/all-cluster-statuses", version='2.0').get('statuses', [])
        return librarieslist
