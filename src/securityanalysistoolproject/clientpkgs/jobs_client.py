'''jobs client module'''
from core.dbclient import SatDBClient

class JobsClient(SatDBClient):
    '''jobs client helper'''

    # permissions are implemented in the permissions_client.py
    # def get_job_permissions(self, job_id):
    #     """
    #     Returns an array of json objects for job permissions.
    #     """
    #     res = self.get(f"/permissions/jobs/{job_id}", version='2.0').get('access_control_list', [])
    #     return res

    # def get_job_permission_levels(self, job_id):
    #     """
    #     Returns an array of json objects for job permissions.
    #     """
    #     res = self.get(f"/permissions/jobs/{job_id}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return res


    def get_jobs_list(self):
        """
        Returns an array of json objects for jobs. It might contain jobs in SINGLE_TASK and
        MULTI_TASK format.
        """
        res = self.get(f"/jobs/list", version='2.2').get('jobs', [])
        return res

    def get_single_job(self, job_id):
        """
        Returns a json object for a job.
        """
        json_params = {'job_id': job_id}
        res = self.get(f"/jobs/get", json_params=json_params, version='2.2').get('satelements', [])
        return res

    def get_job_id_by_name(self):
        """
        get a dict mapping of job name to job id for the new job ids
        :return:
        """
        jobs = self.get_jobs_list()
        job_ids = {}
        for job in jobs:
            job_ids[job['settings']['name']] = job['job_id']
        return job_ids

    def get_jobs_run_list(self):
        """
        Returns an array of json objects for job runs. 
        """
        res = self.get(f"/jobs/runs/list", version='2.2').get('runs', [])
        return res
    
    def get_jobs_run(self, run_id):
        """
        Returns an array of json objects for job runs. 
        """
        json_params = {'run_id': run_id}
        res = self.get(f"/jobs/runs/get", json_params=json_params, version='2.2').get('satelements', [])
        return res