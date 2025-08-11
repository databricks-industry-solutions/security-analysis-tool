'''Serving Endpoints Module'''
from core.dbclient import SatDBClient
import json

class ServingEndpoints(SatDBClient):
    '''serving endpoints client helper'''






    def get_endpoints(self):
        """
        Returns an array of json objects for serving endpoints.
        """
        # fetch all endpoints
        endpoints_list = self.get(f"/serving-endpoints", version='2.0').get('endpoints', [])
        return endpoints_list

    def get_endpoint_byname(self, endpointName):
        """
        Returns details of an endpoint.
        """
        endpointlist= self.get(f"/serving-endpoints/{endpointName}", version='2.0').get('satelements', [])  
        return endpointlist      
    
          


    