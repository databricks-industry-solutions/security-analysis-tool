'''Scim client module'''
from core.dbclient import SatDBClient

class ScimClient(SatDBClient):
    '''scim client helper
    filter should be like """ filter=displayName co "sp" and displayName co "foo" """
    Supported operators are equals(eq), contains(co), starts with(sw) and not equals(ne). 
    Additionally, simple expressions can be formed using logical operators - and and or
    '''

    def get_users(self, filter=None):
        '''get list of users'''
        if filter:
            json_params = {filter: filter}
        else:
            json_params = {}
        user_list = self.get('/preview/scim/v2/Users', json_params=json_params).get('Resources', None)
        return user_list if user_list else None

    def get_groups(self, filter=None):
        '''get list of groups'''
        if filter:
            json_params = {filter: filter}
        else:
            json_params = {}

        group_list = self.get("/preview/scim/v2/Groups", json_params=json_params).get('Resources', [])
        return group_list if group_list else None


    def get_serviceprincipals(self, filter=None):
        '''get list of spns'''
        if filter:
            json_params = {filter: filter}
        else:
            json_params = {}
            
        spn_list = self.get("/preview/scim/v2/ServicePrincipals", json_params=json_params).get('Resources', [])
        return spn_list if spn_list else None       

    def get_userdetails( self, user_id):
        '''get user details'''
        user_details = self.get(f"/preview/scim/v2/Users/{user_id}").get('satelements', [])
        return user_details if user_details else None