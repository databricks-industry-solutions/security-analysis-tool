'''Tokens module'''
from core.dbclient import SatDBClient

class TokensClient(SatDBClient):
    '''tokens client helper'''

    def get_tokens_list(self):
        """
        Returns an array of json objects for tokens.
        fetch all jobsruns
        """

        tokenslist = self.get("/token-management/tokens", version='2.0').get('token_infos', [])
        return tokenslist
