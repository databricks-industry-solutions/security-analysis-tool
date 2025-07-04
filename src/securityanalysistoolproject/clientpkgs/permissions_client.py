''' assignable resoures module'''
import time
from core.dbclient import SatDBClient

class UserGroupObjectsClient(SatDBClient):
    '''Assignable resources helper'''

    def list_assign_resources(self):
        ''' Assign resources apps '''
        resources_list = self.get(f'/preview/accounts/access-control/assignable-roles').get('roles', "")
        return resources_list
    
    def get_object_permissions(self, request_object_type, request_object_id):
        """
        Returns an array of json objects for permissions
        can be one of alerts, authorization, clusters, cluster-policies, dashboards, dbsql-dashboards, directories, 
        experiments, files, instance-pools, jobs, notebooks, pipelines, queries, 
        registered-models, repos, serving-endpoints, or warehouses.

        """
        # fetch all apps
        modlist = self.get(f"/permissions/{request_object_type}/{request_object_id}", version='2.0').get('access_control_list', [])
        return modlist
    
    def get_object_permission_levels(self, request_object_type, request_object_id):
        """
        Returns an array of json objects for permissions
        can be one of alerts, authorization, clusters, cluster-policies, dashboards, dbsql-dashboards, directories, 
        experiments, files, instance-pools, jobs, notebooks, pipelines, queries, 
        registered-models, repos, serving-endpoints, or warehouses.

        """
        # fetch all apps
        modlist = self.get(f"/permissions/{request_object_type}/{request_object_id}/permissionLevels", version='2.0').get('permission_levels', [])
        return modlist