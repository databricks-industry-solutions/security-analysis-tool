'''Policies client module'''
from core.dbclient import SatDBClient

class PoliciesClient(SatDBClient):
    '''policies client helper'''

    def get_cluster_policies_list(self):
        """
        Returns an array of json objects for policies
        """
        # fetch all policies
        poolslist = self.get(f"/policies/clusters/list", version='2.0').get('policies', [])
        return poolslist


    def list_cluster_policy_compliance(self, policy_id):
        """
        Returns an array of json objects for policies
        """
        # fetch all policies
        json_params = {'policy_id': policy_id}
        poolslist = self.get(f"/policies/clusters/list-compliance", json_params=json_params, version='2.0').get('clusters', [])
        return poolslist
    
    def get_cluster_policy_compliance(self, cluster_id):
        """
        Returns an array of json objects for policies
        """
        # fetch a policies
        json_params = {'cluster_id': cluster_id}
        poolslist = self.get(f"/policies/clusters/get-compliance", json_params=json_params, version='2.0').get('satelements', [])
        return poolslist
    

    def get_cluster_policy(self, cluster_policy_id):
        """
        get a policy
        :return: str of new policy id
        """
        json_params = {'policy_id': cluster_policy_id}
        current_policy = self.get(f'/policies/clusters/get', json_params=json_params).get('satelements', [])
        return current_policy    


    def list_jobs_policy_compliance(self, policy_id):
        """
        Returns an array of json objects for policies
        """
        # fetch all policies
        json_params = {'policy_id': policy_id}
        poolslist = self.get(f"/policies/jobs/list-compliance", json_params=json_params, version='2.0').get('jobs', [])
        return poolslist


    def get_job_policy_compliance(self, job_id):
        """
        Returns an array of json objects for policies
        """
        # fetch a policies
        json_params = {'job_id': job_id}
        poolslist = self.get(f"/policies/jobs/get-compliance", json_params=json_params, version='2.0').get('satelements', [])
        return poolslist


    def list_policy_families(self):
        """
        Returns an array of json objects for policies
        """
        # fetch all policies
        poolslist = self.get(f"/policy-families", version='2.0').get('policy_families', [])
        return poolslist
    


