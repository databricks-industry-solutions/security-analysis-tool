from core.logging_utils import LoggingUtils
from clientpkgs.jobs_client import JobsClient

def test_get_job_permissions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    permissions = jobsClient.get_job_permissions("439931807662384")
    LOGGR.debug(permissions)

def test_get_job_permission_levels(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    permissionLevels = jobsClient.get_job_permission_levels("439931807662384")
    LOGGR.debug(permissionLevels)

def test_get_jobs_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    jobsList = jobsClient.get_jobs_list()
    LOGGR.debug(jobsList)

def test_get_single_job(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    singleJob = jobsClient.get_single_job("439931807662384")
    LOGGR.debug(singleJob)

def test_get_job_id_by_name(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    jobIds = jobsClient.get_job_id_by_name()
    LOGGR.debug(jobIds)

def test_get_jobs_run_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    jobsRunList = jobsClient.get_jobs_run_list()
    LOGGR.debug(jobsRunList)

def test_get_jobs_run(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    jobsClient = JobsClient(jsonstr)
    jobRun = jobsClient.get_jobs_run("515345645252901")
    LOGGR.debug(jobRun)