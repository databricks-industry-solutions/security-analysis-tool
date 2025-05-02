'''Tokens module'''
from core.dbclient import SatDBClient

class TokensClient(SatDBClient):
    '''tokens client helper'''

    #permissions in permissions_client.py

    def get_tokens_list_mgmt(self):
        """
        Returns an array of json objects for tokens.
        """
        tokenslist = self.get("/token-management/tokens", version='2.0').get('token_infos', [])
        return tokenslist


    def get_token(self, token_id):
        """
        Returns an array of json objects for tokens.
        """
        tokenlist = self.get("/token-management/tokens/{token_id}", version='2.0').get('token_info', [])
        return tokenlist
    
    

    def get_tokens_list(self):
        """
        Lists all the valid tokens for a user-workspace pair.
        """
        tokenslist = self.get("/token/list", version='2.0').get('token_infos', [])
        return tokenslist