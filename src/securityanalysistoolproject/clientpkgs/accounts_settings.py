
from core.dbclient import SatDBClient
import json

class AccountsSettings(SatDBClient):
    '''accounts helper'''
    subslist=[]
    def get_ipaccess_list(self):
        """
        Returns an array of json objects for ip access
        """
        ipaccess_list=[]
        #if self._cloud_type=='azure':
        #    pass
        accountid=self._account_id
        ipaccess_list = self.get(f"/accounts/{accountid}/ip-access-lists", master_acct=True).get('ip_access_lists',[])
        return ipaccess_list

    def get_compliancesecurityprofile(self):
        """
        Returns an array of json objects for compliance security
        """
        #if self._cloud_type=='azure':
        #    pass
        accountid=self._account_id
        cspjson = self.get(f"/accounts/{accountid}/settings/types/shield_csp_enablement_ac/names/default", master_acct=True)
        cspjsonlist = []
        cspjsonlist.append(json.loads(json.dumps(cspjson)))        
        return cspjsonlist

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
        accountid=self._account_id
        nccjson = self.get(f"/accounts/{accountid}/network-connectivity-configs/{ncc_configid}", master_acct=True)
        nccjsonlist = []
        nccjsonlist.append(json.loads(json.dumps(nccjson)))        
        return nccjsonlist
    
    
