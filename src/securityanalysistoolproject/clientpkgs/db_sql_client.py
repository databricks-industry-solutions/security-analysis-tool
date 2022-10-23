'''dbsql module'''
from core.dbclient import SatDBClient

class DBSqlClient(SatDBClient):
    '''dbsql helper'''

    def get_sqlendpoint_list(self):
        """
        Returns an array of json objects for jobruns.
        """
        # fetch all jobsruns
        endpoints_list = self.get("/sql/endpoints", version='2.0').get('endpoints', [])
        return endpoints_list
