from core.dbclient import SatDBClient
import clientpkgs.azure_accounts_client as azfunc

class AccountsIAMClient(SatDBClient):
    '''accounts helper'''
   
    def get_groupdetails(self, filter=None):
        """
        Returns an array of json objects
        filter=displayName co "foo" and displayName co "bar"
        Supported operators are equals(eq), contains(co), starts with(sw) and not equals(ne). Additionally, simple expressions can be formed using logical operators - and and or. 
        """
        account_id=self._account_id
        json_params={}
        if filter is not None:
            json_params = {'filter': filter}
            
        grpinfo = self.get(f"/accounts/{account_id}/scim/v2/Groups", json_params=json_params, master_acct=True).get('Resources',[])
        return grpinfo    
    
    
    def get_groupdetail(self, id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        grpinfo = self.get(f"/accounts/{account_id}/scim/v2/Groups/{id}", master_acct=True).get('satelements',[])
        return grpinfo   
    
    def get_spndetails(self, filter=None):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        json_params={}
        if filter is not None:
            json_params = {'filter': filter}
        spninfo = self.get(f"/accounts/{account_id}/scim/v2/ServicePrincipals", json_params=json_params, master_acct=True).get('Resources',[])
        return spninfo   

    def get_spndetail(self, id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        spninfo = self.get(f"/accounts/{account_id}/scim/v2/ServicePrincipals/{id}", master_acct=True).get('satelements',[])
        return spninfo   

    def get_userdetails(self, filter=None):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        json_params={}
        if filter is not None:
            json_params = {'filter': filter}
        userinfo = self.get(f"/accounts/{account_id}/scim/v2/Users", json_params=json_params, master_acct=True).get('Resources',[])
        return userinfo   

    def get_userdetail(self, id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        userinfo = self.get(f"/accounts/{account_id}/scim/v2/Users/{id}", master_acct=True).get('satelements',[])
        return userinfo   


    def get_permissions_assignment(self, workspace_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        perminfo = self.get(f"/accounts/{account_id}/workspaces/{workspace_id}/permissionassignments",  master_acct=True).get('permission_assignments',[])
        return perminfo  
     
    def get_permissions(self, workspace_id):
        """
        Returns an array of json objects
        """
        account_id=self._account_id
        perminfo = self.get(f"/accounts/{account_id}/workspaces/{workspace_id}/permissionassignments/permissions",  master_acct=True).get('permissions',[])
        return perminfo   



