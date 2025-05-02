'''Managed Libraries Client'''
from core.dbclient import SatDBClient
import json

class ManagedLibrariesClient(SatDBClient):
    '''managed libraries client helper'''
    def get_library_statuses(self):
        """
        Returns an array of json objects for marketplace.
        """
        mgdlist = self.get(f"/libraries/all-cluster-statuses", version='2.0').get("statuses",[])
        return mgdlist



    def get_library_status(self, cluster_id):
        """
        Returns an array of json objects for marketplace.
        """
        json_params = {'cluster_id': cluster_id}
        mgdlist = self.get(f"/libraries/cluster-status", json_params=json_params, version='2.0').get("library_statuses",[])
        return mgdlist