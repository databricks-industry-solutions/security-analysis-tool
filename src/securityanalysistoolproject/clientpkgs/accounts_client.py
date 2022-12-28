
from core.dbclient import SatDBClient
import clientpkgs.azure_accounts_client as azfunc

class AccountsClient(SatDBClient):
    '''accounts helper'''
    subslist=[]
    def get_workspace_list(self):
        """
        Returns an array of json objects for workspace
        """
        workspaces_list=[]
        if self._cloud_type=='azure':
            if bool(self.subslist) is False:
                self.subslist = self.get_azure_subscription_list()
            workspaces_list = azfunc.remap_workspace_list(self.subslist)
        else:
            accountid=self._account_id
            workspaces_list = self.get(f"/accounts/{accountid}/workspaces", master_acct=True).get('elements',[])
        return workspaces_list

    def get_credentials_list(self):
        """
        Returns an array of json objects for credentials
        """
        credentials_list = []
        if self._cloud_type == 'azure':
            pass
        else:
            accountid=self._account_id
            credentials_list = self.get(f"/accounts/{accountid}/credentials", master_acct=True).get('elements',[])
        return credentials_list

    def get_storage_list(self):
        """
        Returns an array of json objects for storage
        """
        storage_list=[]
        if self._cloud_type == 'azure':
            if bool(self.subslist) is False:
                self.subslist = self.get_azure_subscription_list()
            storage_list = azfunc.remap_storage_list(self.subslist)         
        else:    
            accountid=self._account_id
            storage_list = self.get(f"/accounts/{accountid}/storage-configurations", master_acct=True).get('elements',[])
        return storage_list

    def get_network_list(self):
        """
        Returns an array of json objects for networks
        """
        network_list=[]
        if self._cloud_type == 'azure':
            pass
        else:          
            accountid=self._account_id
            network_list = self.get(f"/accounts/{accountid}/networks", master_acct=True).get('elements',[])
        return network_list

    def get_cmk_list(self):
        """
        Returns an array of json objects for networks
        """
        cmk_list = []
        if self._cloud_type == 'azure':
            pass      
        else:           
            accountid=self._account_id
            cmk_list = self.get(f"/accounts/{accountid}/customer-managed-keys", master_acct=True).get('elements',[])
        return cmk_list

    def get_logdelivery_list(self):
        """
        Returns an array of json objects for log delivery
        """
        logdeliveryinfo = []
        if self._cloud_type == 'azure':
            pass      
        else:        
            accountid=self._account_id
            logdeliveryinfo = self.get(f"/accounts/{accountid}/log-delivery", master_acct=True).\
                get('log_delivery_configurations',[])
        return logdeliveryinfo


    def get_privatelink_info(self):
        """
        Returns an array of json objects for privatelink
        """
        pvtlinkinfo=[]
        if self._cloud_type == 'azure':
            if bool(self.subslist) is False:
                self.subslist = self.get_azure_subscription_list()
            pvtlinkinfo = azfunc.remap_pvtlink_list(self.subslist)         
        else:           
            accountid=self._account_id
            pvtlinkinfo = self.get(f"/accounts/{accountid}/private-access-settings", master_acct=True).get('elements',[])
        return pvtlinkinfo


    def get_azure_subscription_list(self):
        """
        Get the Azure subscription list from the Azure management APIs
        """
        subscriptions_list=[]
        if self._cloud_type!='azure':
            return subscriptions_list
        subscriptions_list = self.get(f"/{self._subscription_id}/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01",
                    master_acct=True).get('value', [])     
        return(subscriptions_list)

    def get_azure_resource_list(self, urlFromSubscription):
        """
        Get the Azure resource list from the Azure management APIs
        """
        resource_list=[]
        if self._cloud_type=='azure':
            resource_list = self.get(f"{urlFromSubscription}?api-version=2018-04-01",
                    master_acct=True).get('value', [])
        return(resource_list)
