'''init scripts module'''
from core.dbclient import SatDBClient

class InitScriptsClient(SatDBClient):
    '''init scripts helper'''

    def get_allglobalinitscripts_list(self):
        """
        Returns an array of json objects for global init sccripts.
        """
        # fetch all init scripts
        globallist = self.get("/global-init-scripts", version='2.0').get('scripts', [])
        return globallist
