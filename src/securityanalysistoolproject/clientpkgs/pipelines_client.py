'''MLFlow module'''
from core.dbclient import SatDBClient

class PipelinesClient(SatDBClient):
    '''Pipelines helper'''

    #for permissions use the permissions_client.py

    def get_pipelines_list(self):
        """
        Returns an array of json objects for pipelines.
        """
        # fetch all experiments
        pipelineslist = self.get(f"/pipelines", version='2.0').get('statuses', [])
        return pipelineslist

    def get_pipeline(self, pipeline_id):
        """
        Returns an array of json objects for pipelines.
        """
        # fetch all experiments
        pipelineslist = self.get(f"/pipelines/{pipeline_id}", version='2.0').get('satelements', [])
        return pipelineslist

    def get_pipelines_events_list(self, pipeline_id):
        """
        Returns an array of json objects for pipelines.
        """
        # fetch all experiments
        pipelineslist = self.get(f"/pipelines/{pipeline_id}/events", version='2.0').get('events', [])
        return pipelineslist
    
    def get_pipelines_update_list(self, pipeline_id, update_id):
        """
        Returns an array of json objects for pipeline.
        """
        # fetch all experiments
        pipelineslist = self.get(f"/pipelines/{pipeline_id}/updates/{update_id}", version='2.0').get('satelements', [])
        return pipelineslist