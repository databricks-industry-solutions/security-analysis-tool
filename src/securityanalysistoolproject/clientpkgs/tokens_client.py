'''Tokens module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils

LOGGR = LoggingUtils.get_logger()

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

    def get_token_permissions(self):
        """
        Returns flattened ACL for workspace token management.
        Endpoint: GET /api/2.0/permissions/authorization/tokens
        Each ACL entry is expanded into one row per permission_level.
        Returns empty list if token ACLs are disabled (FEATURE_DISABLED).
        """
        try:
            acl_list = self.get("/permissions/authorization/tokens", version='2.0').get('access_control_list', [])
        except Exception as e:
            if 'FEATURE_DISABLED' in str(e):
                LOGGR.info("Token ACLs are disabled on this workspace — returning empty list for IA-8")
                return []
            raise
        result = []
        for entry in acl_list:
            for perm in entry.get('all_permissions', []):
                result.append({
                    'group_name': entry.get('group_name', ''),
                    'user_name': entry.get('user_name', ''),
                    'service_principal_name': entry.get('service_principal_name', ''),
                    'display_name': entry.get('display_name', ''),
                    'permission_level': perm.get('permission_level', ''),
                    'inherited': perm.get('inherited', False)
                })
        return result