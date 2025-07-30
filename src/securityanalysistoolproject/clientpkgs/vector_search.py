'''VectoSearch Module'''
from core.dbclient import SatDBClient
import json

class VectorSearch(SatDBClient):
    '''vectorsearch client helper'''

    def get_endpoint_list(self):
        """
        Returns an array of json objects for jobruns.
        """
        # fetch all endpoints
        endpoints_list = self.get(f"/vector-search/endpoints", version='2.0').get('endpoints', [])
        return endpoints_list

    def get_endpoint(self, endpointName):
        """
        Returns details of an endpoint.
        """
        endpointlist= self.get(f"/vector-search/endpoints/{endpointName}", version='2.0').get('satelements',[])
        # endpointlist = []
        # endpointlist.append(json.loads(json.dumps(endpointjson)))
        return endpointlist      

    def get_index_list(self, endpointName):
        """
        Returns an array for the indexes.
        """
        # fetch all indicies
        json_params={'endpoint_name': endpointName}
        indices_list = self.get(f"/vector-search/indexes", json_params=json_params, version='2.0').get('vector_indexes', [])
        return indices_list

    def get_index(self, indexName):
        """
        Returns an array for the index.
        """
        # fetch the specific index
        indexlist = self.get(f"/vector-search/indexes/{indexName}", version='2.0').get('satelements', [])
        return indexlist   


    