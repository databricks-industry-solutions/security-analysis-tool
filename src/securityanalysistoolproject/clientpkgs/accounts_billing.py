
from core.dbclient import SatDBClient
import json

class AccountsBilling(SatDBClient):
    '''accounts billing helper'''

    def get_budget_policies(self):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/budget-policies", version='2.1', master_acct=True).get('policies',[])
        return policies_lst

    def get_budget_policy(self, policy_id):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/budget-policies/{policy_id}", version='2.1', master_acct=True).get('satelements',[])
        return policies_lst

    def get_logdelivery_config_list(self):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        logdel_lst = self.get(f"/accounts/{account_id}/log-delivery", master_acct=True).get('log_delivery_configurations',[])
        return logdel_lst

    def get_logdelivery_config_info(self, log_delivery_configuration_id):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        logdel_lst = self.get(f"/accounts/{account_id}/log-delivery/{log_delivery_configuration_id}",  master_acct=True).get('satelements',[])
        return logdel_lst

    def get_budgets_list(self):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        budgets_lst = self.get(f"/accounts/{account_id}/budgets", version='2.1', master_acct=True).get('budgets',[])
        return budgets_lst

    def get_budgets_info(self, budget_id):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        logdel_lst = self.get(f"/accounts/{account_id}/budgets/{budget_id}",  version='2.1', master_acct=True).get('satelements',[])
        return logdel_lst
    