
from core.dbclient import SatDBClient
import json

class AccountsSettings(SatDBClient):
    '''accounts helper'''
    subslist=[]
    def get_ipaccess_list(self):
        """
        Returns an array of json objects for ip access
        """

        account_id=self._account_id
        ipaccess_list = self.get(f"/accounts/{account_id}/ip-access-lists", master_acct=True).get('ip_access_lists',[])
        return ipaccess_list

    def get_ipaccess_info(self, ip_access_list_id):
        """
        Returns an array of json objects for ip access
        """
        account_id=self._account_id
        ipaccess_list = self.get(f"/accounts/{account_id}/ip-access-lists/{ip_access_list_id}", master_acct=True).get('ip_access_list',[])
        return ipaccess_list

    def get_compliancesecurityprofile(self):
        """
        Returns an array of json objects for compliance security
        """
        #if self._cloud_type=='azure':
        #    pass
        account_id=self._account_id
        cspjsonlist = self.get(f"/accounts/{account_id}/settings/types/shield_csp_enablement_ac/names/default", master_acct=True).get("satelements", [])   
        return cspjsonlist

    def get_enhancedsecuritymonitoringprofile(self):
        """
        Returns an array of json objects for compliance security
        """
        #if self._cloud_type=='azure':
        #    pass
        account_id=self._account_id
        esmjsonlist = self.get(f"/accounts/{account_id}/settings/types/shield_esm_enablement_ac/names/default", master_acct=True).get("satelements", [])   
        return esmjsonlist    


    def get_networkconnectivityconfigurations(self, pageToken=None):
        """
        Returns an array of json objects for network connectivity
        """
        csp_list=[]
        #if self._cloud_type=='azure':
        #    pass
        accountid=self._account_id
        itemjson_list = self.get(f"/accounts/{accountid}/network-connectivity-configs", master_acct=True).get('items',[])     
        return itemjson_list

    def get_networkconnectivityconfiguration(self, ncc_configid):
        """
        Returns an array of json objects for compliance security
        """
        #if self._cloud_type=='azure':
        #    pass
        account_id=self._account_id
        nccjsonlist = self.get(f"/accounts/{account_id}/network-connectivity-configs/{ncc_configid}", master_acct=True).get('satelements',[])      
        return nccjsonlist
    
    def get_networkpolicies(self):
        account_id=self._account_id
        ncpoliciesjsonlist = self.get(f"/accounts/{account_id}/network-policies", master_acct=True).get('items',[])      
        return ncpoliciesjsonlist      
    
    
