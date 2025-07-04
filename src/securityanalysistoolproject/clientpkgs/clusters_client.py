''' clusters module'''
import time
from core.dbclient import SatDBClient
import json
from core.logging_utils import LoggingUtils


class ClustersClient(SatDBClient):
    '''clusters helper'''

    create_configs = {'num_workers',
                      'autoscale',
                      'cluster_name',
                      'spark_version',
                      'spark_conf',
                      'aws_attributes',
                      'node_type_id',
                      'driver_node_type_id',
                      'ssh_public_keys',
                      'custom_tags',
                      'cluster_log_conf',
                      'init_scripts',
                      'docker_image',
                      'spark_env_vars',
                      'autotermination_minutes',
                      'enable_elastic_disk',
                      'instance_pool_id',
                      'policy_id',
                      'pinned_by_user_name',
                      'creator_user_name',
                      'cluster_id'}

    # def get_cluster_list(self, alive=True):
    #     """
    #     Returns an array of json objects for the running clusters.
    #     Grab the cluster_name or cluster_id
    #     """
    #     clusters_list = self.get("/clusters/list").get('clusters', [])
    #     if alive and clusters_list:
    #         running = filter(lambda x: x['state'] == "RUNNING", clusters_list)
    #         return list(running)
    #     else:
    #         return clusters_list

    # policies and permissions check policies_client.py and permissions_client.py


    def get_cluster_events(self, cluster_id, start_time=None, end_time=None):
        """
        Returns an array of json objects for the  cluster events.
        Grab the cluster_name or cluster_id
        """
        LOGGR = LoggingUtils.get_logger()
        params = {}
        params['cluster_id'] = cluster_id
        if start_time:
            params['start_time'] = start_time
        if end_time:
            params['end_time'] = end_time
        events_list = self.post(f"/clusters/events", json_params=params, version='2.1').get('events', [])
        return events_list

    def get_cluster_info(self, cluster_id):
        """
        Export all cluster permissions for a specific cluster id
        :return:
        """
        json_params = {'cluster_id': cluster_id}
        current_policy = self.get(f'/clusters/get', json_params=json_params, version='2.1').get('satelements', [])
        return current_policy        


    def get_cluster_list(self, alive=False):
        """
        Returns an array of json objects for the running clusters.
        Grab the cluster_name or cluster_id
        """
        LOGGR = LoggingUtils.get_logger()
        clusters_list = self.get("/clusters/list", json_params={}, version='2.1').get('clusters', [])
        if alive and clusters_list:
            running = filter(lambda x: x['state'] == "RUNNING", clusters_list)
            return list(running)
        else:
            return clusters_list

    def get_instance_pools(self):
        '''get instance pools'''
        current_pools = self.get('/instance-pools/list').get('instance_pools', None)
        return current_pools
    
    def get_instance_pool_info(self, instance_pool_id):
        '''get instance pools'''
        json_params = {'instance_pool_id': instance_pool_id}
        current_pools = self.get('/instance-pools/get', json_params=json_params).get('satelements', [])
        return current_pools

    def get_instance_profiles_list(self):
        '''get instance profiles list'''
        if self._cloud_type=='aws':
            iprof_json_list = self.get('/instance-profiles/list').get('instance_profiles', [])
            return iprof_json_list
        return []


    #deprecated this is legacy. for new version check permissions_client.py
    def get_cluster_acls(self, cluster_id, cluster_name):
        """
        preview api
        Export all cluster permissions for a specific cluster id
        :return:
        """
        perms = self.get(f'/preview/permissions/clusters/{cluster_id}/')
        perms['cluster_name'] = cluster_name
        return perms

    #returns cluster ID
    # def get_cluster_id_by_name(self, cname, running_only=False):
    #     '''get cluster id by name'''
    #     cluster_list = self.get('/clusters/list').get('clusters', [])
    #     if running_only:
    #         running = list(filter(lambda x: x['state'] == "RUNNING", cluster_list))
    #         for runclus in running:
    #             if cname == runclus['cluster_name']:
    #                 return runclus['cluster_id']
    #     else:
    #         for runclus in cluster_list:
    #             if cname == runclus['cluster_name']:
    #                 return runclus['cluster_id']
    #     return None


    def get_cluster_id_by_name(self, cname, running_only=False):
        clusters_list = self.get_cluster_list(alive=running_only)
        for i in clusters_list:
            if cname in i['cluster_name']:
                return i['cluster_id']

    def start_cluster_by_name(self, cluster_name):
        '''start the cluster'''
        cid = self.get_cluster_id_by_name(cluster_name)
        if cid is None:
            raise Exception('Error: Cluster name does not exist')
        resp = self.post('/clusters/start', {'cluster_id': cid})
        if 'error_code' in resp:
            if resp.get('error_code', None) == 'INVALID_STATE':
                pass
            else:
                raise Exception('Error: cluster does not exist, or is in a state that is unexpected. '
                                'Cluster should either be terminated state, or already running.')
        self.wait_for_cluster(cid)
        return cid

    def wait_for_cluster(self, cid):
        '''wait for cluster to come up'''
        c_state = self.get('/clusters/get', {'cluster_id': cid})
        while c_state['state'] != 'RUNNING' and c_state['state'] != 'TERMINATED':
            c_state = self.get('/clusters/get', {'cluster_id': cid})
            time.sleep(2)
        if c_state['state'] == 'TERMINATED':
            raise RuntimeError("Cluster is terminated. Please check EVENT history for details")
        return cid



    def get_iam_role_by_cid(self, cid):
        '''get iam role by cid'''
        if self._cloud_type=='aws':
            cluster_resp = self.get(f'/clusters/get?cluster_id={cid}')
            return cluster_resp.get('aws_attributes').get('instance_profile_arn', None)
        return None


    # This is legacy. for new version check init_scripts_client.py
    def get_global_init_scripts(self):
        """ return a list of global init scripts. Currently not logged """
        lsscripts = self.get('/dbfs/list', {'path': '/databricks/init/'}).get('files', None)
        if lsscripts is None:
            return []
        else:
            global_scripts = [{'path': x['path']} for x in lsscripts if not x['is_dir']]
            return global_scripts

    def get_spark_versions(self):
        '''get spark versions'''
        return self.get("/clusters/spark-versions").get('versions', [])



    def is_spark_3(self, cid):
        '''is this spark 3'''
        spark_version = self.get(f'/clusters/get?cluster_id={cid}').get('spark_version', "")
        svspk = int(spark_version.split('.')[0])
        if svspk >= 7:
            return True
        else:
            return False
