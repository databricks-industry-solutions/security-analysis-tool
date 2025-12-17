'''job runs module'''
from core.dbclient import SatDBClient

class JobRunsClient(SatDBClient):
    '''get job runs'''

    def get_jobruns_list(self):
        """
        Returns an array of json objects for jobruns.
        """
        # fetch all jobsruns
        runslist = self.get("/jobs/runs/list", version='2.0').get('runs', [])
        return runslist
