'''unity catalog client module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils
import json

LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()

class UnityCatalogClient(SatDBClient):
    '''unity catalog helper'''

    def get_artifacts_allowlists(self, artifact_type):
        """
        Returns an array of json objects for artifact type
        artifact_type=INIT_SCRIPT | LIBRARY_JAR | LIBRARY_MAVEN
        """
        # fetch all catalogs list
        matchlist = self.get(f"/unity-catalog/artifact-allowlists/{artifact_type}", version='2.1').get('artifact_matchers', [])
        return matchlist


    def get_catalogs_list(self):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        catalogslist = self.get(f"/unity-catalog/catalogs", version='2.1').get('catalogs', [])
        return catalogslist

    def get_catalog(self, catalog_name):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        catalogjson = self.get(f"/unity-catalog/catalogs/{catalog_name}", version='2.1')
        cataloglist = []
        cataloglist.append(json.loads(json.dumps(catalogjson)))
        return cataloglist      
    
    def get_connections_list(self):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        connectionslist = self.get(f"/unity-catalog/connections", version='2.1').get('connections', [])
        return connectionslist

    def get_connection(self, connection_name):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        connjson = self.get(f"/unity-catalog/connections/{connection_name}", version='2.1')
        connlist = []
        connlist.append(json.loads(json.dumps(connjson)))
        return connlist   

    def get_external_locations(self):
        """
        Returns an array of json objects for external locations
        """
        # fetch all external locations
        extlocns = self.get(f"/unity-catalog/external-locations", version='2.1').get('external_locations', [])
        return extlocns

    def get_external_location(self, extlocn):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        extlocnjson = self.get(f"/unity-catalog/external-locations/{extlocn}", version='2.1')
        extlocnlist = []
        extlocnlist.append(json.loads(json.dumps(extlocnjson)))
        return extlocnlist   

    def get_functions(self, catalog_name, schema_name):
        """
        Returns an array of json objects for functions
        """
        # fetch all functions
        query = f"/unity-catalog/functions?catalog_name={catalog_name}&schema_name={schema_name}"
        funcs = self.get(query, version='2.1').get('schemas', [])
        return funcs 
    
    def get_function(self, functionname):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        funcjson = self.get(f"/unity-catalog/functions/{functionname}", version='2.1')
        funcjsonlist = []
        funcjsonlist.append(json.loads(json.dumps(funcjson)))
        return funcjsonlist   

    def get_grants_permissions(self, securable_type, full_name):
        """
        Returns permissions for securable type
        :param securable_type like METASTORE, CATALOG, SCHEMA
        :param full_name like metastore guid
        """
        # fetch all schemaslist
        permslist = self.get(f"/unity-catalog/effective-permissions/{securable_type}/{full_name}", version='2.1').get('privilege_assignments', [])
        return permslist    


    def get_grants_effective_permissions(self, securable_type, full_name):
        """
        Returns effective permissions for securable type
        :param securable_type like METASTORE, CATALOG, SCHEMA
        catalog | schema | table | storage_credential | external_location | function | share | provider | recipient | metastore | pipeline | volume | connection
        :param full_name like metastore guid
        """
        # fetch all schemaslist
        permslist = self.get(f"/unity-catalog/permissions/{securable_type}/{full_name}", version='2.1').get('privilege_assignments', [])
        return permslist    
    
    def get_table_monitor(self, table_name):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        monitorjson = self.get(f"/unity-catalog/tables/{table_name}/monitor", version='2.1')
        monitorjsonlist = []
        monitorjsonlist.append(json.loads(json.dumps(monitorjson)))
        return monitorjsonlist   
    
    def get_workspace_metastore_assignments(self):
        """
        Returns  workspace metastore assignment. Typo in function name. Should be singular.
        """
        # fetch all metastore assignment list
        metastorejson = self.get(f"/unity-catalog/current-metastore-assignment", version='2.1')
        metastoreassgnlist = []
        metastoreassgnlist.append(json.loads(json.dumps(metastorejson)))
        return metastoreassgnlist    
    

    def get_workspace_metastore_summary(self):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        metastoresumjson = self.get(f"/unity-catalog/metastore_summary", version='2.1')
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
            metastores = self.get(f"/unity-catalog/metastores", version='2.1').get('metastores', [])
        except  Exception as e:
            LOGGR.exception(e)
            return []
        return metastores

    def get_model_versions(self, modelname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        modelversionlist = self.get(f"/unity-catalog/models/{modelname}/versions", version='2.1').get('model_versions', [])
        return modelversionlist    

    def get_model_version(self, modelname, version):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        modelversionjson = self.get(f"/unity-catalog/models/{modelname}/versions/{version}", version='2.1')
        modelversionjsonlist = []
        modelversionjsonlist.append(json.loads(json.dumps(modelversionjson)))
        return modelversionjsonlist    
    

    def get_online_table(self, onlinetable):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        onlinetbljson = self.get(f"/online-tables/{onlinetable}", version='2.0')
        onlinetbljsonlist = []
        onlinetbljsonlist.append(json.loads(json.dumps(onlinetbljson)))
        return onlinetbljsonlist

    def get_registered_models(self):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        modelversionlist = self.get(f"/unity-catalog/models", version='2.1').get('registered_models', [])
        return modelversionlist

    def get_registered_model(self, modelname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        modeljson = self.get(f"/unity-catalog/models/{modelname}", version='2.1')
        modeljsonlist = []
        modeljsonlist.append(json.loads(json.dumps(modeljson)))
        return modeljsonlist       

    def get_schemas_list(self, catalogname):
        """
        Returns list of schemas
        """
        # fetch all schemaslist
        schemaslist = self.get(f"/unity-catalog/schemas?catalog_name={catalogname}", version='2.1').get('schemas', [])
        return schemaslist 

    def get_schema(self, catalogname, schemaname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        schemajson = self.get(f"/unity-catalog/schemas/{catalogname}.{schemaname}", version='2.1')
        schemajsonlist = []
        schemajsonlist.append(json.loads(json.dumps(schemajson)))
        return schemajsonlist    

    
    def get_credentials(self):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        credentialslist = self.get(f"/unity-catalog/storage-credentials", version='2.1').get('storage_credentials', [])
        return credentialslist
    
    def get_credential(self, credname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        credentialjson = self.get(f"/unity-catalog/storage-credentials/{credname}", version='2.1')
        credjsonlist = []
        credjsonlist.append(json.loads(json.dumps(credentialjson)))
        return credjsonlist      
    

    def get_systemschemas(self, metastore_id):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        systemschemas = self.get(f"/unity-catalog/metastores/{metastore_id}/systemschemas", version='2.1').get('schemas', [])
        return systemschemas
    
    def get_tablesummaries(self, catalog_name, schema_name, table_name, page_token ):
        """
        Returns list of credentials
        """ 
        strquery=''
        if catalog_name:
            strquery=f'catalog_name={catalog_name}&'
        if schema_name:
            strquery=f'{strquery}schema_name={schema_name}&'
        if table_name:
            strquery=f'{strquery}table_name={table_name}&'
        if page_token:
            strquery=f'{strquery}page_token={page_token}&'
        strurl = f"/unity-catalog/table-summaries?{strquery}"
        # fetch all schemaslist
        tablesummaries = self.get(strurl, version='2.1').get('tables', [])
        return tablesummaries

    def get_tables(self, catalog_name, schema_name, page_token, include_delta_metadata, omit_columns, omit_properties, include_browse):
        """
        Returns list of tables
        """
        strquery=''
        if catalog_name:
            strquery=f'catalog_name={catalog_name}&'
        if schema_name:
            strquery=f'{strquery}schema_name={schema_name}&'
        if page_token:
            strquery=f'{strquery}page_token={page_token}&'
        if include_delta_metadata:
            strquery=f'{strquery}include_delta_metadata={include_delta_metadata}&'
        if omit_columns:
            strquery=f'{strquery}omit_columns={omit_columns}&'
        if omit_properties:
            strquery=f'{strquery}omit_properties={omit_properties}&'
        if include_browse:
            strquery=f'{strquery}include_browse={include_browse}'


        strurl = f"/unity-catalog/tables?{strquery}"    
        # fetch all schemaslist
        tableslist = self.get(strurl, version='2.1').get('tables', [])
        return tableslist
    
    def get_table(self, table_name):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        tablejson = self.get(f"/unity-catalog/tables/{table_name}", version='2.1')
        tablejsonlist = []
        tablejsonlist.append(json.loads(json.dumps(tablejson)))
        return tablejsonlist    

    def get_volumes(self, catalog_name, schema_name, page_token, include_browse):
        """
        Returns list of credentials
        """
        strquery=''
        if catalog_name:
            strquery=f'catalog_name={catalog_name}&'
        if schema_name:
            strquery=f'{strquery}schema_name={schema_name}&'
        if page_token:
            strquery=f'{strquery}page_token={page_token}&'
        if include_browse:
            strquery=f'{strquery}include_browse={include_browse}'


        strurl = f"/unity-catalog/volumes?{strquery}"       
        # fetch all schemaslist
        volumes = self.get(strurl, version='2.1').get('volumes', [])
        return volumes

    def get_volume(self, volume_name):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        voljson = self.get(f"/unity-catalog/volumes/{volume_name}", version='2.1')
        voljsonlist = []
        voljsonlist.append(json.loads(json.dumps(voljson)))
        return voljsonlist  


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
        sharingrecepientslist = self.get(f"/unity-catalog/recipients", version='2.1').get('recipients', [])
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
        shareslist = self.get(f"/unity-catalog/shares", version='2.1').get('shares', [])
        return shareslist   
    
    def get_share_permissions(self, sharename):
        """
        Returns an array of json objects for share permission
        """
        # fetch all acls list
        sharingacl = self.get(f"/unity-catalog/shares/{sharename}/permissions", version='2.1').get('privilege_assignments', [])
        return sharingacl
    
 

    
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

            