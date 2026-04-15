'''jobs client module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils

LOGGR = LoggingUtils.get_logger()

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


    def get_job_permissions_for_jobs(self, job_list):
        """
        Returns a flat list of permission records for the given jobs.
        Each row is one (job, principal, permission_level) combination.
        job_list: list of Row objects with job_id and job_name fields.
        """
        result = []
        for row in job_list:
            job_id = row.job_id
            job_name = row.job_name or ''
            try:
                acl = self.get(f"/permissions/jobs/{job_id}", version='2.0').get('access_control_list', [])
                for entry in acl:
                    group_name = entry.get('group_name') or ''
                    user_name = entry.get('user_name') or ''
                    service_principal_name = entry.get('service_principal_name') or ''
                    for perm in entry.get('all_permissions', []):
                        result.append({
                            'job_id': str(job_id),
                            'job_name': job_name,
                            'group_name': group_name,
                            'user_name': user_name,
                            'service_principal_name': service_principal_name,
                            'permission_level': perm.get('permission_level') or '',
                            'inherited': perm.get('inherited', False)
                        })
            except Exception as e:
                LOGGR.warning(f"Could not get permissions for job {job_id}: {e}")
        return result

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