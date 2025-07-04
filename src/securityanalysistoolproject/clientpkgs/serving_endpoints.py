'''Serving Endpoints Module'''
from core.dbclient import SatDBClient
import json

class ServingEndpoints(SatDBClient):
    '''serving endpoints client helper'''


    # permissions are implemented in the permissions_client.py
    # def get_serving_permissions(self, serving_endpoint_id):
    #     """
    #     Returns endpoint permissions.
    #     """
    #     permissionlst= self.get(f"/permissions/serving-endpoints/{serving_endpoint_id}", version='2.0').get('access_control_list', [])
    #     return permissionlst    

    # def get_serving_permission_levels(self, serving_endpoint_id):
    #     """
    #     Returns endpoint permissions.
    #     """
    #     permissionlst= self.get(f"/permissions/serving-endpoints/{serving_endpoint_id}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return permissionlst    



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
    
          


    