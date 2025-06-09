''' apps module'''
import time
from core.dbclient import SatDBClient

class AppsClient(SatDBClient):
    '''apps helper'''

    def list_apps(self):
        ''' List apps '''
        apps_list = self.get(f'/apps').get('apps', "")
        return apps_list
    
    def list_apps_deployments(self, app_name):
        ''' List apps deployments'''
        apps_list = self.get(f'/apps/{app_name}/deployments').get('app_deployments', "")
        return apps_list
    
    def get_app(self, app_name):
        ''' Get app '''
        apps_list = self.get(f'/apps/{app_name}').get('active_deployment', "")
        return apps_list

    # permissions are implemented in the permissions_client.py
    # def get_apps_permissions(self, app_name):
    #     """
    #     Returns an array of json objects for permissions
    #     """
    #     # fetch all apps
    #     modlist = self.get(f"/permissions/apps/{app_name}", version='2.0').get('access_control_list', [])
    #     return modlist
    
    # def get_apps_permission_levels(self, app_name):
    #     """
    #     Returns an array of json objects for permission levels
    #     """
    #     # fetch all registered models
    #     modlist = self.get(f"/permissions/apps/{app_name}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return modlist