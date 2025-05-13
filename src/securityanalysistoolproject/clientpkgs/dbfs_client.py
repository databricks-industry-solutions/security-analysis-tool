'''dbfs module'''
import ast
import os

from core.dbclient import SatDBClient


class DbfsClient(SatDBClient):
    '''dbfs client'''

    @staticmethod
    def get_num_of_lines(fname):
        ''' get num of lines'''
        if not os.path.exists(fname):
            return 0
        else:
            i = 0
            with open(fname, encoding='utf-8') as fphandle:
                for _ in fphandle:
                    i += 1
            return i

    def get_dbfs_mounts(self):
        '''get all mounts'''
        ec_id = self.get_execution_context()

        # get all dbfs mount metadata
        all_mounts_cmd = 'all_mounts = [{"path": x.mountPoint, "source": x.source, ' \
                '"encryptionType": x.encryptionType} for x in dbutils.fs.mounts() if "/mnt/" in x.mountPoint]'
        results = self.submit_command(ec_id, all_mounts_cmd)
        results = self.submit_command(ec_id, 'print(all_mounts)')
        resultsdict=results.get('satelements', [])
        dataresults = ast.literal_eval(results['data'])
        return dataresults

    def get_dbfs_directories(self, path):
        ''' get dbfs directories'''
        json_params_v = {"path" : path}
        dir_list = self.get("/dbfs/list", version='2.0', json_params=json_params_v).get('files', [])
        return dir_list
