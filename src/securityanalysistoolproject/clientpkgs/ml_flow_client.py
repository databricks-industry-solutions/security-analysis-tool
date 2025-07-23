'''MLFlow module'''
from core.dbclient import SatDBClient

class MLFlowClient(SatDBClient):
    '''Mlflow helper'''

    def get_experiments_list(self):
        """
        Returns an array of json objects for experiments.
        """
        # fetch all experiments
        json_params = {'view_type': 'ACTIVE_ONLY'}
        explist = self.get(f"/mlflow/experiments/list", json_params=json_params, version='2.0').get('experiments', [])
        return explist
    
    #TODO pagination logic
    def get_registered_models(self):
        """
        Returns an array of json objects for registered models.
        """
        # fetch all registered models
        modlist = self.get(f"/mlflow/registered-models/list", version='2.0').get('registered_models', [])
        return modlist


    def get_list_artifacts(self, run_id, path_s):
        """
        Returns an array of json objects for registered models.
        """
        # fetch all registered models
        json_params = {'run_id': run_id, 'path': path_s}
        modlist = self.get(f"/mlflow/artifacts/list", json_params=json_params, version='2.0').get('files', [])
        return modlist
    

    def search_for_runs(self, experiment_ids, filter):
        """
        Returns an array of json objects for registered models.
        """
        # fetch all registered models
        json_params = {"experiment_ids": experiment_ids, "filter": filter}  
        modlist = self.post(f"/mlflow/runs/search", json_params=json_params, version='2.0').get('runs', [])
        return modlist
    

    
    #for permissions use the permissions_client.py
    
    def get_list_registry_webhooks(self, model_name):
        """
        Returns an array of json objects for registered models.
        """
        # fetch all registered models
        json_params = {'model_name': model_name}
        modlist = self.get(f"/mlflow/registry-webhooks/list", json_params=json_params, version='2.0').get('webhooks', [])
        return modlist

    def get_list_transition_requests(self, model_name, version):
        """
        Returns an array of json objects for webhooks
        """
        json_params = {'name': model_name, 'version': version}
        modlist = self.get(f"/mlflow/transition-requests/list", json_params=json_params, version='2.0').get('requests', [])
        return modlist
