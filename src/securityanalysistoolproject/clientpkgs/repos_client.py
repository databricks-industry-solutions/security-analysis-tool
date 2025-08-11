''' repos client module'''
from core.dbclient import SatDBClient

class ReposClient(SatDBClient):
    ''' repos helper'''

    def get_repos_list(self):
        """
        Returns an array of json objects for repos
        """
        # fetch all repos list
        reposlist = self.get("/repos", version='2.0').get('repos', [])
        return reposlist
    

    def get_git_credentials_list(self):
        """
        Returns an array of json objects for repos
        """
        # fetch all repos list
        reposlist = self.get(f"/git-credentials", version='2.0').get('credentials', [])
        return reposlist
    

    # permissions are implemented in the permissions_client.py
    # def get_repo_permissions(self, repo_id):
    #     """
    #     Returns an array of json objects for repos
    #     """
    #     # fetch all repos list
    #     reposlist = self.get(f"/permissions/repos/{repo_id}", version='2.0').get('access_control_list', [])
    #     return reposlist
    

    # def get_repo_permission_levels(self, repo_id):
    #     """
    #     Returns an array of json objects for repos
    #     """
    #     # fetch all repos list
    #     reposlist = self.get(f"/permissions/repos/{repo_id}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return reposlist
    
    def get_repo(self, repo_id):
        """
        Returns an array of json objects for repos
        """
        # fetch all repos list
        reposlist = self.get(f"/repos/{repo_id}", version='2.0').get('satelements', [])
        return reposlist
    
    