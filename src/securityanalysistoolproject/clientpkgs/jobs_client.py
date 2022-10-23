'''jobs client module'''
from core.dbclient import SatDBClient

class JobsClient(SatDBClient):
    '''jobs client helper'''

    def get_jobs_list(self):
        """
        Returns an array of json objects for jobs. It might contain jobs in SINGLE_TASK and
        MULTI_TASK format.
        """
        jobsbyid = {}
        # fetch all jobs using API 2.0. The 'format' field of each job can either be SINGLE_TASK
        # or MULTI_TASK. MULTI_TASK jobs, however, are returned without task definitions (the
        # 'tasks' field) on API 2.0.
        res = self.get("/jobs/list", version='2.0')
        for job in res.get('jobs', []):
            jobsbyid[job.get('job_id')] = job

        limit = 25 # max limit supported by the API
        offset = 0
        has_more = True
        # fetch all jobs again, this time using API 2.1, in order to get MULTI_TASK jobs with
        # # task definitions. Note that the 'format' field will be set as MULTI_TASK for all jobs
        # # and the 'tasks' field will be present for all jobs as well
        while has_more:
            res = self.get(f'/jobs/list?expand_tasks=true&offset={offset}&limit={limit}', version='2.1')
            offset += limit
            has_more = res.get('has_more')
            for job in res.get('jobs', []):
                jobid = job.get('job_id')
                # only replaces "real" MULTI_TASK jobs, as they contain the task definitions.
                if jobsbyid[jobid].get('format') == 'MULTI_TASK':
                    jobsbyid[jobid] = job
        return jobsbyid.values()

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
