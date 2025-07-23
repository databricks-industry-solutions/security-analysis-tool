from core.logging_utils import LoggingUtils
from clientpkgs.policies_client import PoliciesClient

def test_get_cluster_policies_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    policiesList = policiesClient.get_cluster_policies_list()
    LOGGR.debug(policiesList)

def test_list_cluster_policy_compliance(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    complianceList = policiesClient.list_cluster_policy_compliance('E0631F5C0D0006D3')
    LOGGR.debug(complianceList)

def test_get_cluster_policy_compliance(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    compliance = policiesClient.get_cluster_policy_compliance("0420-082734-g5g17crp")
    LOGGR.debug(compliance)

def test_get_cluster_policy(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    policy = policiesClient.get_cluster_policy("E0631F5C0D0006D3")
    LOGGR.debug(policy)

def test_list_jobs_policy_compliance(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    jobsComplianceList = policiesClient.list_jobs_policy_compliance('E0641B99CA001B6D')
    LOGGR.debug(jobsComplianceList)

def test_get_job_policy_compliance(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    jobCompliance = policiesClient.get_job_policy_compliance("439931807662384")
    LOGGR.debug(jobCompliance)

def test_list_policy_families(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    policiesClient = PoliciesClient(jsonstr)
    policyFamilies = policiesClient.list_policy_families()
    LOGGR.debug(policyFamilies)