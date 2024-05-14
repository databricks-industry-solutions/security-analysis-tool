'''VectoSearch Module'''
from core.dbclient import SatDBClient
import json

class VectorSearch(SatDBClient):
    '''vectorsearch client helper'''

    def get_endpoint_list(self, pageToken=None):
        """
        Returns an array of json objects for jobruns.
        """
        # fetch all endpoints
        if pageToken is None:
            pageToken=''
        endpoints_list = self.get(f"/vector-search/endpoints?page_token={pageToken}", version='2.0').get('endpoints', [])
        return endpoints_list

    def get_endpoint(self, endpointName):
        """
        Returns details of an endpoint.
        """
        endpointjson= self.get(f"/vector-search/endpoints/{endpointName}", version='2.0')
        endpointlist = []
        endpointlist.append(json.loads(json.dumps(endpointjson)))
        return endpointlist      

    def get_index_list(self, endpointName, pageToken=None):
        """
        Returns an array for the indexes.
        """
        # fetch all indicies
        if pageToken is None:
            pageToken=''
        indices_list = self.get(f"/vector-search/indexes?endpoint_name={endpointName}&page_token={pageToken}", version='2.0').get('vector_indexes', [])
        return indices_list

    def get_index(self, indexName):
        """
        Returns an array for the index.
        """
        # fetch the specific index
        indexjson = self.get(f"/vector-search/indexes/{indexName}", version='2.0')
        indexlist = []
        indexlist.append(json.loads(json.dumps(indexjson)))
        return indexlist   


    