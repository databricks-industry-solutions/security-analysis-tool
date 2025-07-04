'''workspace client module'''
from clientpkgs.scim_client import ScimClient
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils

class WorkspaceClient(SatDBClient):
    '''workspace client helper'''

    def get_list_notebooks(self, path):
        """
        Returns an array of json objects for notebooks in a path
        """
        # fetch all poolslist
        notebooklist = self.get(f"/workspace/list", json_params={'path': path}, version='2.0').get('objects', [])
        return notebooklist


    def get_all_notebooks(self):
        '''get list of notebooks'''
        # pylint: disable=modified-iterating-list
        scimclient = ScimClient(self._inp_configs)
        userslst = scimclient.get_users()
        pathlst = []
        notebooklst = []
        LOGGR = LoggingUtils.get_logger()
        LOGGR.info('getting notebooks...')
        for user in userslst:
            pathlst.append('/Users/' + user['userName'])
            pathlst.append('/Repos/' + user['userName'])
        for path in pathlst:
            nblist = self.get_list_notebooks(path)
            for entity in nblist:
                if entity['object_type']=='DIRECTORY' or entity['object_type']=='REPO':
                    pathlst.append(entity['path'])
                elif entity['object_type']=='NOTEBOOK' or entity['object_type']=='FILE':
                    notebooklst.append(entity['path'])
        # pylint: enable=modified-iterating-list
        LOGGR.info('finished notebooks...')
        return notebooklst
    

    # permissions are implemented in permissions_client.py
    # def get_workspace_object_permissions(self,workspace_object_type, workspace_object_id):
    #     """
    #     Returns workspace object permissions
    #     object type: Expected one of {alerts,apps,authorization,clusters,cluster-policies,dashboards,
    #     dbsql-dashboards,directories,experiments,files,instance-pools,jobs,notebooks,pipelines,queries,
    #     registered-models,repos,serving-endpoints,warehouses,vector-search-endpoints}
    #     """
    #     # fetch all workspacelist
    #     workspacelist = self.get(f"/permissions/{workspace_object_type}/{workspace_object_id}",  version='2.0').get('access_control_list', [])
    #     return workspacelist