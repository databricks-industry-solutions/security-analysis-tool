
from core.dbclient import SatDBClient
import clientpkgs.azure_accounts_client as azfunc

class AccountsProvisioningCLient(SatDBClient):
    '''accounts helper'''

    def get_credentials_list(self):
        """
        Returns an array of json objects for credentials
        """
        account_id=self._account_id
        credentials_list = self.get(f"/accounts/{account_id}/credentials", master_acct=True).get('satelements',[])
        return credentials_list

    def get_credential_info(self, credentials_id):
        """
        Returns an array of json objects for credentials
        """
        account_id=self._account_id
        credentials_list = self.get(f"/accounts/{account_id}/credentials/{credentials_id}", master_acct=True).get('satelements',[])
        return credentials_list

    def get_cmk_list(self):
        """
        Returns an array of json objects for networks
        """     
        account_id=self._account_id
        cmk_list = self.get(f"/accounts/{account_id}/customer-managed-keys", master_acct=True).get('satelements',[])
        return cmk_list
    
    def get_cmk_info(self, customer_managed_key_id):
        """
        Returns an array of json objects for networks
        """     
        account_id=self._account_id
        cmk_list = self.get(f"/accounts/{account_id}/customer-managed-keys/{customer_managed_key_id}", master_acct=True).get('satelements',[])
        return cmk_list

    def get_network_list(self):
        """
        Returns an array of json objects for networks
        """
        account_id=self._account_id
        network_list = self.get(f"/accounts/{account_id}/networks", master_acct=True).get('satelements',[])
        return network_list

    def get_network_info(self, network_id):
        """
        Returns an array of json objects for networks
        """
        account_id=self._account_id
        network_list = self.get(f"/accounts/{account_id}/networks/{network_id}", master_acct=True).get('satelements',[])
        return network_list

    def get_privatelink_list(self):
        """
        Returns an array of json objects for privatelink
        """
        pvtlinkinfo=[]
        account_id=self._account_id
        pvtlinkinfo = self.get(f"/accounts/{account_id}/private-access-settings", master_acct=True).get('satelements',[])
        return pvtlinkinfo

    def get_privatelink_info(self, private_access_settings_id):
        """
        Returns an array of json objects for privatelink
        """
        pvtlinkinfo=[]
        account_id=self._account_id
        pvtlinkinfo = self.get(f"/accounts/{account_id}/private-access-settings/{private_access_settings_id}", master_acct=True).get('satelements',[])
        return pvtlinkinfo


    def get_storage_list(self):
        """
        Returns an array of json objects for storage
        """
        account_id=self._account_id
        storage_list = self.get(f"/accounts/{account_id}/storage-configurations", master_acct=True).get('satelements',[])
        return storage_list

    def get_storage_info(self, storage_configuration_id):
        """
        Returns an array of json objects for storage
        """
        account_id=self._account_id
        storage_list = self.get(f"/accounts/{account_id}/storage-configurations/{storage_configuration_id}", master_acct=True).get('satelements',[])
        return storage_list
    
    def get_vpcconfig_list(self):
        """
        Returns an array of json objects for storage
        """
        account_id=self._account_id
        vpcconfig_list = self.get(f"/accounts/{account_id}/vpc-endpoints", master_acct=True).get('satelements',[])
        return vpcconfig_list

    def get_vpcconfig_info(self, vpc_endpoint_id):
        """
        Returns an array of json objects for storage
        """
        account_id=self._account_id
        vpcconfig_list = self.get(f"/accounts/{account_id}/vpc-endpoints/{vpc_endpoint_id}", master_acct=True).get('satelements',[])
        return vpcconfig_list

    def get_workspace_list(self):
        """
        Returns an array of json objects for workspace
        """
        account_id=self._account_id
        workspaces_list = self.get(f"/accounts/{account_id}/workspaces", master_acct=True).get('satelements',[])
        return workspaces_list

    def get_workspace_info(self, workspace_id):
        """
        Returns an array of json objects for workspace
        """
        account_id=self._account_id
        workspaces_list = self.get(f"/accounts/{account_id}/workspaces/{workspace_id}", master_acct=True).get('satelements',[])
        return workspaces_list



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
            workspaces_list = self.get(f"/accounts/{accountid}/workspaces", master_acct=True).get('satelements',[])
        return workspaces_list





    def get_logdelivery_list(self):
        """
        Returns an array of json objects for log delivery
        """
        logdeliveryinfo = []
        if self._cloud_type == 'azure':
            if bool(self.subslist) is False:
                self.subslist = self.get_azure_subscription_list()
            logdeliveryinfo = self.get_azure_diagnostic_logs(self.subslist)   
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
            pvtlinkinfo = self.get(f"/accounts/{accountid}/private-access-settings", master_acct=True).get('satelements',[])
        return pvtlinkinfo


    def get_azure_subscription_list(self):
        """
        Get the Azure subscription list from the Azure management APIs
        """
        subscriptions_list=[]
        if self._cloud_type!='azure':
            return subscriptions_list
        subscriptions_list = self.get(f"/subscriptions/{self._subscription_id}/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01",
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

    def get_azure_diagnostic_logs(self, subslist):
        diag_list = []
        if bool(self.subslist) is False:
            self.subslist = self.get_azure_subscription_list()

        for rec in self.subslist:
            if azfunc.getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                    or azfunc.getItem(rec, ['properties', 'workspaceId'], True) is None \
                    or azfunc.getItem(rec, ['properties','parameters', 'encryption'], True) is None \
                    or azfunc.getItem(rec, ['id'], True) is None:
                continue
            diagresid = azfunc.getItem(rec, ['id'], True)

            diag_subs_list = self.get(f"/{diagresid}/providers/microsoft.insights/diagnosticSettings?api-version=2021-05-01-preview",
                        master_acct=True).get('value', [])            
            if bool(diag_subs_list) is False:
                continue

            diag = {}
            diag['account_id']=azfunc.getItem(rec, ['properties', 'workspaceId'])
            diag['workspace_id']=azfunc.getItem(rec, ['properties', 'workspaceId'])        
            diag['status']="ENABLED"
            diag['config_name']=azfunc.getItem(diag_subs_list[0], ['name']) #just the first one will do
            diag['config_id']=azfunc.getItem(diag_subs_list[0], ['id'])
            diag['location']=azfunc.getItem(diag_subs_list[0], ['location']) #just the first one will do
            diag['log_type']='AUDIT_LOGS'
            diag_list.append(diag)

        return diag_list   

