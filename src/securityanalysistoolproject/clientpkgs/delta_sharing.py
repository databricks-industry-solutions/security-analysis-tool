'''unity catalog client module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils
from clientpkgs.unity_catalog_client import UnityCatalogClient
import json

LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()

class DeltaSharingClient(SatDBClient):
    '''delta sharing helper'''

    def get_sharing_providers_list(self):
        """
        Returns an array of json objects for sharing providers
        """
        # fetch all sharing providers list
        query = f"/unity-catalog/providers"
        sharingproviderslist = self.get(query, version='2.1').get('providers', [])
        return sharingproviderslist

    def get_sharing_provider(self, sharename):
        """
        Returns an array of json objects for sharing providers. fetch a sharing provider
        """
        sharingjsonlist = self.get(f"/unity-catalog/providers/{sharename}", version='2.1').get('satelements', [])
        return sharingjsonlist  

    def get_sharing_providers_info(self, name):
        """
        Returns an array of json objects for sharing providers
        """
        # list shares by provider
        query = f"/unity-catalog/providers/{name}/shares"
        sharingproviderslist = self.get(query, version='2.1').get('shares', [])
        return sharingproviderslist


    def get_sharing_recepients_list(self):
        """
        Returns an array of json objects for sharing recepients
        """
        # fetch all sharing recepients list
        sharingrecepientslist = self.get(f"/unity-catalog/recipients", version='2.1').get('recipients', [])
        return sharingrecepientslist
    
    def get_sharing_recepient(self, sharename):
        """
        Returns an array of json objects for sharing recepients
        """
        sharingjsonlist = self.get(f"/unity-catalog/recipients/{sharename}", version='2.1').get('satelements', [])
        return sharingjsonlist  
    
    def get_sharing_recepient_permissions(self, sharename):
        """
        Returns an array of json objects for sharing recepients permission
        """
        # fetch all acls list
        sharingacl = self.get(f"/unity-catalog/recipients/{sharename}/share-permissions", version='2.1').get('permissions_out', [])
        return sharingacl

    def get_list_shares(self):
        """
        Returns an array of json objects for shares
        """
        # fetch all shares 
        shareslist = self.get(f"/unity-catalog/shares", version='2.1').get('shares', [])
        return shareslist   

    def get_share(self, sharename):
        """
        Returns an array of json objects for shares
        """
        # fetch all shares 
        sharingjsonlist = self.get(f"/unity-catalog/shares/{sharename}", version='2.1').get('satelements', [])
        return sharingjsonlist  



    def get_share_permissions(self, sharename):
        """
        Returns an array of json objects for share permission
        """
        # fetch all acls list
        sharingacl = self.get(f"/unity-catalog/shares/{sharename}/permissions", version='2.1').get('privilege_assignments', [])
        return sharingacl
    
