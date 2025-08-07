from core.logging_utils import LoggingUtils
from clientpkgs.accounts_oauth import AccountsOAuth

def test_get_account_federation_policies(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    policiesList = accountsClient.get_account_federation_policies()
    LOGGR.debug(policiesList)

def test_get_account_federation_policy_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    policyInfo = accountsClient.get_account_federation_policy_info("policy1")
    LOGGR.debug(policyInfo)

def test_get_custom_oauth_policies(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    customPolicies = accountsClient.get_custom_oauth_policies()
    LOGGR.debug(customPolicies)

def test_get_custom_oauth_policy_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    policyInfo = accountsClient.get_custom_oauth_policy_info("integration1")
    LOGGR.debug(policyInfo)

def test_get_published_oauth_apps(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    publishedApps = accountsClient.get_published_oauth_apps()
    LOGGR.debug(publishedApps)

def test_get_oauth_published_app_integrations(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    integrations = accountsClient.get_oauth_published_app_integrations()
    LOGGR.debug(integrations)

def test_get_oauth_published_app_integration_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    integrationInfo = accountsClient.get_oauth_published_app_integration_info("integration1")
    LOGGR.debug(integrationInfo)

def test_get_service_principal_federation_policies(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    policies = accountsClient.get_service_principal_federation_policies("sp1")
    LOGGR.debug(policies)

def test_get_service_principal_federation_policy_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    policyInfo = accountsClient.get_service_principal_federation_policy_info("sp1", "policy1")
    LOGGR.debug(policyInfo)

def test_get_service_principal_secrets(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    accountsClient = AccountsOAuth(jsonstr)
    secrets = accountsClient.get_service_principal_secrets("sp1")
    LOGGR.debug(secrets)