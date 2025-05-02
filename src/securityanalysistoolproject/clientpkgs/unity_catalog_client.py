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
        cataloglist = self.get(f"/unity-catalog/catalogs/{catalog_name}", version='2.1')
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
        connlist = self.get(f"/unity-catalog/connections/{connection_name}", version='2.1').get('satelements', [])
        return connlist   

    def get_credentials(self):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        credentialslist = self.get(f"/unity-catalog/credentials", version='2.1').get('credentials', [])
        return credentialslist

    def get_credential(self, name_arg):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        credentiallist = self.get(f"/unity-catalog/credentials/{name_arg}", version='2.1').get('satelements', [])
        return credentiallist



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
        extlocnjsonlist = self.get(f"/unity-catalog/external-locations/{extlocn}", version='2.1').get ('satelements', [])
        return extlocnjsonlist   

    def get_functions(self, catalog_name, schema_name):
        """
        Returns an array of json objects for functions
        """
        json_params={'catalog_name': catalog_name, 'schema_name': schema_name}
        # fetch all functions
        query = f"/unity-catalog/functions"
        funcs = self.get(query, json_params=json_params, version='2.1').get('functions', [])
        return funcs 
    
    def get_function(self, functionname):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        funcjsonlist = self.get(f"/unity-catalog/functions/{functionname}", version='2.1').get('satelements', [])
        return funcjsonlist   

    #for permissions see permissions_client

    def get_grants_effective_permissions(self, securable_type, full_name):
        """
        Returns permissions for securable type
        :param securable_type like METASTORE, CATALOG, SCHEMA
        :param full_name like metastore guid
        """
        # fetch all schemaslist
        permslist = self.get(f"/unity-catalog/effective-permissions/{securable_type}/{full_name}", version='2.1').get('privilege_assignments', [])
        return permslist    

    def get_workspace_metastore_assignments(self):
        """
        Returns  workspace metastore assignment. Typo in function name. Should be singular.
        """
        # fetch all metastore assignment list
        metastorejsonlist = self.get(f"/unity-catalog/current-metastore-assignment", version='2.1').get('satelements', [])
        return metastorejsonlist    
    


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
    
    def get_metastore_id(self, id):
        """
        Returns  metastore detail
        """
        try:
            metastores = self.get(f"/unity-catalog/metastores/{id}", version='2.1').get('satelements', [])
        except  Exception as e:
            LOGGR.exception(e)
            return []
        return metastores
    

    def get_workspace_metastore_summary(self):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        metastoresumlist = self.get(f"/unity-catalog/metastore_summary", version='2.1').get('satelements', [])
        return metastoresumlist    
    
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
        modelversionjsonlist = self.get(f"/unity-catalog/models/{modelname}/versions/{version}", version='2.1').get('satelements', [])
        return modelversionjsonlist    


    def get_online_table(self, onlinetable):
        """
        Returns  online table
        """
        # return online table
        onlinetbllist = self.get(f"/online-tables/{onlinetable}", version='2.0').get('satelements', [])
        return onlinetbllist
    
        
    def get_table_monitor(self, table_name):
        """
        Returns an array of json objects for catalogs list
        """
        # fetch all catalogs list
        monitorlist = self.get(f"/unity-catalog/tables/{table_name}/monitor", version='2.1').get('satelements', [])
        return monitorlist   
    

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
        modeljsonlist = self.get(f"/unity-catalog/models/{modelname}", version='2.1').get('satelements', [])
        return modeljsonlist       

    def get_resource_quotas_metastore(self):
        """
        Returns resource quota summary
        """
        # fetch all metastore assignment list
        quotajsonlist = self.get(f"/unity-catalog/resource-quotas/all-resource-quotas", version='2.1').get('quotas', [])
        return quotajsonlist   


    def get_schemas_list(self, catalogname):
        """
        Returns list of schemas
        """
        # fetch all schemaslist
        json_params={'catalog_name': catalogname}
        schemaslist = self.get(f"/unity-catalog/schemas", json_params=json_params, version='2.1').get('schemas', [])
        return schemaslist 

    def get_schema(self, catalogname, schemaname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        schemajsonlist = self.get(f"/unity-catalog/schemas/{catalogname}.{schemaname}", version='2.1').get('satelements', [])
        return schemajsonlist    

    
    def get_storage_credentials(self):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        credentialslist = self.get(f"/unity-catalog/storage-credentials", version='2.1').get('storage_credentials', [])
        return credentialslist
    
    def get_storage_credential(self, credname):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        credjsonlist = self.get(f"/unity-catalog/storage-credentials/{credname}", version='2.1').get('satelements', [])
        return credjsonlist      
    
    def get_systemschemas(self, metastore_id):
        """
        Returns list of credentials
        """
        # fetch all schemaslist
        systemschemas = self.get(f"/unity-catalog/metastores/{metastore_id}/systemschemas", version='2.1').get('schemas', [])
        return systemschemas
    
    def get_tablesummaries(self, catalog_name, schema_name=None, table_name=None ):
        """
        Returns list of credentials
        """ 
        json_params={}

        if catalog_name:
            json_params.append({'catalog_name': catalog_name})
        if schema_name:
            json_params.append({'schema_name_pattern': schema_name})
        if table_name:
            json_params.append({'table_name_pattern': table_name})

        # fetch all schemaslist
        tablesummaries = self.get(f'/unity-catalog/table-summaries', json_params=json_params, version='2.1').get('tables', [])
        return tablesummaries

    def get_tables(self, catalog_name, schema_name,include_browse=True):
        """
        Returns list of tables
        """
        json_params={'catalog_name': catalog_name, 'schema_name': schema_name, 'include_browse': include_browse}
        strurl = f"/unity-catalog/tables"    
        # fetch all schemaslist
        tableslist = self.get(strurl, json_params=json_params, version='2.1').get('tables', [])
        return tableslist
    
    def get_table(self, table_name):
        """
        Returns  workspace metastore summary
        """
        # fetch all metastore assignment list
        tablejsonlist = self.get(f"/unity-catalog/tables/{table_name}", version='2.1').get('satelements', [])
        return tablejsonlist    

    def get_volumes(self, catalog_name, schema_name, page_token, include_browse=False):
        """
        Returns list of credentials
        """
        json_params={}

        if catalog_name:
            json_params.update({'catalog_name':catalog_name})
        if schema_name:
            json_params.update({'schema_name':schema_name})
        if include_browse:
            json_params.update({'include_browse':include_browse})

        # fetch all schemaslist
        volumes = self.get(f"/unity-catalog/volumes", json_params=json_params, version='2.1').get('volumes', [])
        return volumes

    def get_volume(self, volume_name):
        """
        Returns  workspace metastore summary
        """
        voljsonlist = self.get(f"/unity-catalog/volumes/{volume_name}", version='2.1').get('satelements', [])
        return voljsonlist  

    def get_securable_bindings(self, securable_type, securable_name):
        """
        Returns securable bindings summary
        """
        secjsonlist = self.get(f"/unity-catalog/bindings/{securable_type}/{securable_name}", version='2.1').get('bindings', [])
        return secjsonlist  

    def get_securable_binding(self, catname):
        """
        Returns securable bindings summary
        """
        secjsonlist = self.get(f"/unity-catalog/workspace-bindings/catalogs/{catname}", version='2.1').get('workspaces', [])
        return secjsonlist  
    


    
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

            