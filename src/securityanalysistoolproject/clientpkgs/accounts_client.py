'''accounts client module'''
from core.dbclient import SatDBClient


class AccountsClient(SatDBClient):
    '''accounts helper'''

    def get_workspace_list(self):
        """
        Returns an array of json objects for workspace
        """
        accountid=self._account_id
        workspaces_list = self.get(f"/accounts/{accountid}/workspaces", master_acct=True).get('elements',[])
        return workspaces_list

    def get_credentials_list(self):
        """
        Returns an array of json objects for credentials
        """
        accountid=self._account_id
        credentials_list = self.get(f"/accounts/{accountid}/credentials", master_acct=True).get('elements',[])
        return credentials_list

    def get_storage_list(self):
        """
        Returns an array of json objects for storage
        """
        accountid=self._account_id
        storage_list = self.get(f"/accounts/{accountid}/storage-configurations", master_acct=True).get('elements',[])
        return storage_list

    def get_network_list(self):
        """
        Returns an array of json objects for networks
        """
        accountid=self._account_id
        network_list = self.get(f"/accounts/{accountid}/networks", master_acct=True).get('elements',[])
        return network_list

    def get_cmk_list(self):
        """
        Returns an array of json objects for networks
        """
        accountid=self._account_id
        cmk_list = self.get(f"/accounts/{accountid}/customer-managed-keys", master_acct=True).get('elements',[])
        return cmk_list

    def get_logdelivery_list(self):
        """
        Returns an array of json objects for log delivery
        """
        accountid=self._account_id
        logdeliveryinfo = self.get(f"/accounts/{accountid}/log-delivery", master_acct=True).\
                get('log_delivery_configurations',[])
        return logdeliveryinfo

    def get_privatelink_info(self):
        """
        Returns an array of json objects for privatelink
        """
        accountid=self._account_id
        pvtlinkinfo = self.get(f"/accounts/{accountid}/private-access-settings", master_acct=True).get('elements',[])
        return pvtlinkinfo
