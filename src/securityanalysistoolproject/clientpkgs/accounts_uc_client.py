from core.dbclient import SatDBClient
import clientpkgs.azure_accounts_client as azfunc

class AccountsUCClient(SatDBClient):
    '''accounts helper'''
   
    def get_workspaces_to_metastore(self, metastore_id):
        """
        Returns an array of json objects
         """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/metastores/{metastore_id}/workspaces",  master_acct=True).get('workspace_ids',[])
        return resinfo

    def get_metastore_to_workspace(self, workspace_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/workspaces/{workspace_id}/metastore",  master_acct=True).get('metastore_assignment',[])
        return resinfo

    def get_all_metastores(self):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/metastores",  master_acct=True).get('metastores',[])
        return resinfo
    
    def get_metastore_info(self, metastore_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/metastores/{metastore_id}",  master_acct=True).get('metastore_info',[])
        return resinfo
    
    def get_storage_credentials_metastore(self, metastore_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/metastores/{metastore_id}/storage-credentials",  master_acct=True).get('storage_credentials',[])
        return resinfo

    def get_named_storage_credential_metastore(self, metastore_id, storage_credential_name):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
            
        resinfo = self.get(f"/accounts/{account_id}/metastores/{metastore_id}/storage-credentials/{storage_credential_name}",  master_acct=True).get('satelements',[])
        return resinfo
    
    