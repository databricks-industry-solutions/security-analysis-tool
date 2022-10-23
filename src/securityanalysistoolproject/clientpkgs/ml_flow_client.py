'''MLFlow module'''
from core.dbclient import SatDBClient

class MLFlowClient(SatDBClient):
    '''Mlflow helper'''

    def get_experiments_list(self):
        """
        TODO pagination logic
        Returns an array of json objects for experiments.
        """
        # fetch all experiments
        explist = self.get("/mlflow/experiments/list", version='2.0').get('experiments', [])
        return explist
    #TODO pagination logic
    def get_registered_models(self):
        """
        Returns an array of json objects for registered models.
        """
        # fetch all registered models
        modlist = self.get("/preview/mlflow/registered-models/list", version='2.0').get('registered_models', [])
        return modlist
