from core.logging_utils import LoggingUtils
from clientpkgs.accounts_billing import AccountsBilling

def test_get_budget_policies(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    policies = billingClient.get_budget_policies()
    LOGGR.debug(policies)

def test_get_budget_policy(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    policy = billingClient.get_budget_policy("fb8ed049-36e1-45ab-acfb-b5167cbd29e0")
    LOGGR.debug(policy)

def test_get_logdelivery_config_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    logdelivery = billingClient.get_logdelivery_config_list()
    LOGGR.debug(logdelivery)

def test_get_logdelivery_config_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    logdelivery_info = billingClient.get_logdelivery_config_info("test_logdelivery_id")
    LOGGR.debug(logdelivery_info)

def test_get_budgets_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    budgets = billingClient.get_budgets_list()
    LOGGR.debug(budgets)

def test_get_budgets_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    billingClient = AccountsBilling(jsonstr)
    budget_info = billingClient.get_budgets_info("a7fb19f9-ad14-4a36-b389-384f3d980f4d")
    LOGGR.debug(budget_info)