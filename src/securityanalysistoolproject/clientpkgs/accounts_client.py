
from core.dbclient import SatDBClient
import clientpkgs.azure_accounts_client as azfunc
from core.logging_utils import LoggingUtils
#account_provisioning_client has the same methods as accounts_client
# deprecate this at some point.


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
            workspaces_list = self.get(f"/accounts/{accountid}/workspaces", master_acct=True).get('satelements',[])
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
            credentials_list = self.get(f"/accounts/{accountid}/credentials", master_acct=True).get('satelements',[])
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
            storage_list = self.get(f"/accounts/{accountid}/storage-configurations", master_acct=True).get('satelements',[])
        return storage_list

    def get_network_list(self):
        """
        Returns an array of json objects for networks
        """
        network_list=[]
        if self._cloud_type == 'azure':
            # this function in accounts_settings.py
            pass
        else:          
            accountid=self._account_id
            network_list = self.get(f"/accounts/{accountid}/networks", master_acct=True).get('satelements',[])
        return network_list

    def get_cmk_list(self):
        """
        Returns an array of json objects for networks
        """
        cmk_list = []
        if self._cloud_type == 'azure':
            if bool(self.subslist) is False:
                self.subslist = self.get_azure_subscription_list()
            cmk_list = azfunc.remap_cmk_list(self.subslist)   
        else:           
            accountid=self._account_id
            cmk_list = self.get(f"/accounts/{accountid}/customer-managed-keys", master_acct=True).get('satelements',[])
        return cmk_list

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
    
    
    # Refactored to do a single workspace.

    # # fixed this check jul 28 2025
    # #added this back. Remove once we finalize
    # # or azfunc.getItem(rec, ['properties','parameters', 'encryption'], True) is None \
    # def get_azure_diagnostic_logs(self, subslist):
    #     diag_list = []
    #     if bool(self.subslist) is False:
    #         self.subslist = self.get_azure_subscription_list()

    #     for rec in self.subslist:
    #         if azfunc.getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
    #                 or azfunc.getItem(rec, ['properties', 'workspaceId'], True) is None \
    #                 or azfunc.getItem(rec, ['properties','parameters', 'encryption'], True) is None \
    #                 or azfunc.getItem(rec, ['id'], True) is None:
    #             continue
    #         diagresid = azfunc.getItem(rec, ['id'], True)
    #         if diagresid.startswith('/'):
    #             diagresid = diagresid[1:]
    #         diag_subs_list = self.get(f"/{diagresid}/providers/microsoft.insights/diagnosticSettings?api-version=2021-05-01-preview",
    #                     master_acct=True).get('value', [])            
    #         if bool(diag_subs_list) is False:
    #             continue
    #         diag = {}
    #         diag['account_id']=azfunc.getItem(rec, ['properties', 'workspaceId'])
    #         diag['workspace_id']=azfunc.getItem(rec, ['properties', 'workspaceId'])        
    #         diag['status']="ENABLED"
    #         diag['config_name']=azfunc.getItem(diag_subs_list[0], ['name']) #just the first one will do
    #         diag['config_id']=azfunc.getItem(diag_subs_list[0], ['id'])
    #         diag['location']=azfunc.getItem(diag_subs_list[0], ['location']) #just the first one will do
    #         diag['log_type']='AUDIT_LOGS'

    #         diag_list.append(diag)

    #     return diag_list   

    #if workspace_id is None, then use the one coming in from the workspace.
    # workspace_id useful for testing only
    def get_azure_diagnostic_logs(self, subslist, workspace_id=None):
        diag_list = []
        if workspace_id is None:       
            workspace_id = self._workspace_id
        if bool(self.subslist) is False:
            self.subslist = self.get_azure_subscription_list()
        for rec in self.subslist:
            if azfunc.getItem(rec, ['type']) != 'Microsoft.Databricks/workspaces' \
                    or azfunc.getItem(rec, ['properties', 'workspaceId'], True) is None \
                    or azfunc.getItem(rec, ['id'], True) is None:
                continue
            lworkspaceId = azfunc.getItem(rec, ['properties', 'workspaceId'])
            if lworkspaceId != str(workspace_id):  
                continue           
            
            diagresid = azfunc.getItem(rec, ['id'], True)
            if diagresid.startswith('/'):
                diagresid = diagresid[1:]
            diag_subs_list = self.get(f"/{diagresid}/providers/microsoft.insights/diagnosticSettings?api-version=2021-05-01-preview",
                        master_acct=True).get('value', [])            
            if bool(diag_subs_list) is False:
                continue #maybe break here since only one workspace is being checked

            diag = {}
            diag['account_id']=self._account_id
            diag['workspace_id']=azfunc.getItem(rec, ['properties', 'workspaceId'])        
            diag['status']="ENABLED"
            diag['config_name']=azfunc.getItem(diag_subs_list[0], ['name']) #just the first one will do
            diag['config_id']=azfunc.getItem(diag_subs_list[0], ['id'])
            diag['location']=azfunc.getItem(diag_subs_list[0], ['location']) #just the first one will do
            diag['log_type']='AUDIT_LOGS'

            diag_list.append(diag)
        return diag_list  