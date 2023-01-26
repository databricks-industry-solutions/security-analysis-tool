'''Scim client module'''
from core.dbclient import SatDBClient

class ScimClient(SatDBClient):
    '''scim client helper'''

    def get_users(self):
        '''get list of users'''
        user_list = self.get('/preview/scim/v2/Users').get('Resources', None)
        return user_list if user_list else None

    def get_groups(self):
        '''get list of groups'''
        group_list = self.get("/preview/scim/v2/Groups").get('Resources', [])
        return group_list if group_list else None


    def get_serviceprincipals(self):
        '''get list of spns'''
        spn_list = self.get("/preview/scim/v2/ServicePrincipals").get('Resources', [])
        return spn_list if spn_list else None        
