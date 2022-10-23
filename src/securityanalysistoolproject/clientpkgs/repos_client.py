''' repos client module'''
from core.dbclient import SatDBClient

class ReposClient(SatDBClient):
    ''' repos helper'''

    def get_repos_list(self):
        """
        Returns an array of json objects for repos
        """
        # fetch all repos list
        reposlist = self.get("/repos", version='2.0').get('repos', [])
        return reposlist
