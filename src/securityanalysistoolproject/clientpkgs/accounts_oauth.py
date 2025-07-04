from core.dbclient import SatDBClient
import json

class AccountsOAuth(SatDBClient):
    '''accounts oauth helper'''

    def get_account_federation_policies(self):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/federationPolicies",  master_acct=True).get('policies',[])
        return policies_lst

    def get_account_federation_policy_info(self, policy_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/federationPolicies/{policy_id}",  master_acct=True).get('satelements',[])
        return policies_lst

    def get_custom_oauth_policies(self):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/oauth2/custom-app-integrations",  master_acct=True).get('apps',[])
        return policies_lst

    def get_custom_oauth_policy_info(self, integration_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policies_lst = self.get(f"/accounts/{account_id}/oauth2/custom-app-integrations/{integration_id}",  master_acct=True).get('satelements',[])
        return policies_lst

    def get_published_oauth_apps(self):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        apps_lst = self.get(f"/accounts/{account_id}/oauth2/published-apps",  master_acct=True).get('apps',[])
        return apps_lst

    def get_oauth_published_app_integrations(self):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        oauth_lst = self.get(f"/accounts/{account_id}/oauth2/published-app-integrations",  master_acct=True).get('apps',[])
        return oauth_lst

    def get_oauth_published_app_integration_info(self, integration_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        oauth_lst = self.get(f"/accounts/{account_id}/oauth2/published-app-integrations/{integration_id}",  master_acct=True).get('satelements',[])
        return oauth_lst
    

    def get_service_principal_federation_policies(self, service_principal_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policy_lst = self.get(f"/accounts/{account_id}/servicePrincipals/{service_principal_id}/federationPolicies",  master_acct=True).get('policies',[])
        return policy_lst

    def get_service_principal_federation_policy_info(self, service_principal_id, policy_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        policy_lst = self.get(f"/accounts/{account_id}/servicePrincipals/{service_principal_id}/federationPolicies/{policy_id}",  master_acct=True).get('satelements',[])
        return policy_lst
    
    def get_service_principal_secrets(self, service_principal_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        secrets_lst = self.get(f"/accounts/{account_id}/servicePrincipals/{service_principal_id}/credentials/secrets",  master_acct=True).get('secrets',[])
        return secrets_lst
