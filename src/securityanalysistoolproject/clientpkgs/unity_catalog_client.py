'''unity catalog client module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils
import json

LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()

class UnityCatalogClient(SatDBClient):
    '''unity catalog helper'''

    def get_catalogs_list(self):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        catalogslist = self.get("/unity-catalog/catalogs", version='2.1').get('catalogs', [])
        return catalogslist

    def get_schemas_list(self, catalogname):
        """
        Returns list of schemas
        """
        # fetch all schemaslist
        schemaslist = self.get(f"/unity-catalog/schemas?catalog_name={catalogname}", version='2.1').get('schemas', [])
        return schemaslist 

    def get_tables(self, catalog_name, schema_name):
        """
        Returns list of tables
        """
        # fetch all schemaslist
        query = f"/unity-catalog/tables?catalog_name={catalog_name}&schema_name={schema_name}"
        tableslist = self.get(query, version='2.1').get('tables', [])
        return tableslist
    
    def get_functions(self, catalog_name, schema_name):
        """
        Returns an array of json objects for functions
        """
        # fetch all functions
        query = f"/unity-catalog/functions?catalog_name={catalog_name}&schema_name={schema_name}"
        funcs = self.get(query, version='2.1').get('schemas', [])
        return funcs

    def get_sharing_providers_list(self):
        """
        Returns an array of json objects for sharing providers
        """
        # fetch all sharing providers list
        query = f"/unity-catalog/providers"
        sharingproviderslist = self.get(query, version='2.1').get('providers', [])
        return sharingproviderslist
    
    def get_sharing_recepients_list(self):
        """
        Returns an array of json objects for sharing recepients
        """
        # fetch all sharing recepients list
        sharingrecepientslist = self.get("/unity-catalog/recipients", version='2.1').get('recipients', [])
        return sharingrecepientslist
    
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
        shareslist = self.get("/unity-catalog/shares", version='2.1').get('shares', [])
        return shareslist   
    
    def get_share_permissions(self, sharename):
        """
        Returns an array of json objects for share permission
        """
        # fetch all acls list
        sharingacl = self.get(f"/unity-catalog/shares/{sharename}/permissions", version='2.1').get('privilege_assignments', [])
        return sharingacl
    

    def get_external_locations(self):
        """
        Returns an array of json objects for external locations
        """
        # fetch all external locations
        extlocns = self.get("/unity-catalog/external-locations", version='2.1').get('external_locations', [])
        return extlocns
    
    def get_workspace_metastore_assignments(self):
        """
        Returns  workspace metastore assignment
        """
        # fetch all metastore assignment list
        metastorejson = self.get("/unity-catalog/current-metastore-assignment", version='2.1')
        metastoreassgnlist = []
        metastoreassgnlist.append(json.loads(json.dumps(metastorejson)))
        return metastoreassgnlist    
    

    def get_workspace_metastore_summary(self):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        metastoresumjson = self.get("/unity-catalog/metastore_summary", version='2.1')
        metastoresumlist = []
        metastoresumlist.append(json.loads(json.dumps(metastoresumjson)))
        return metastoresumlist    
    
    #Has to be an account admin to run this api
    def get_metastore_list(self):
        """
        Returns list of workspace metastore 
        """
        # fetch all metastores
        # Exception: Error: GET request failed with code 403 {"error_code":"PERMISSION_DENIED","message":"Only account admin can list metastores.","details":[{"@type":"type.googleapis.com/google.rpc.RequestInfo","request_id":"b9353080-94ea-47b6-b551-083336de7d84","serving_data":""}]
        try:
            metastores = self.get("/unity-catalog/metastores", version='2.1').get('metastores', [])
        except  Exception as e:
            LOGGR.exception(e)
            return []
        return metastores
    
    def get_credentials(self):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        credentialslist = self.get("/unity-catalog/storage-credentials", version='2.1').get('storage_credentials', [])
        return credentialslist
    
    def get_grants_effective_permissions(self, securable_type, full_name):
        """
        Returns effective permissions for securable type
        :param securable_type like METASTORE, CATALOG, SCHEMA
        :param full_name like metastore guid
        """
        # fetch all schemaslist
        permslist = self.get(f"/unity-catalog/permissions/{securable_type}/{full_name}", version='2.1').get('privilege_assignments', [])
        return permslist    
    
    def get_grants_permissions(self, securable_type, full_name):
        """
        Returns permissions for securable type
        :param securable_type like METASTORE, CATALOG, SCHEMA
        :param full_name like metastore guid
        """
        # fetch all schemaslist
        permslist = self.get("/unity-catalog/effective-permissions/{securable_type}/{full_name}", version='2.1').get('privilege_assignments', [])
        return permslist    
    
    #the user should have account admin privileges
    def get_grants_effective_permissions_ext(self):
        arrperms=[]
        arrlist = self.get_metastore_list()
        for meta in arrlist:
            metastore_id = meta['metastore_id']
            effperms = self.get_grants_effective_permissions('METASTORE', metastore_id)
            for effpermselem in effperms:
                effpermselem['metastore_id'] = meta['metastore_id']
                effpermselem['metastore_name'] = meta['name']
            arrperms.extend(effperms)
        jsonarr = json.dumps(arrperms)
        return arrperms

            