from core.logging_utils import LoggingUtils
from core.dbclient import SatDBClient
from clientpkgs.clusters_client import ClustersClient




def test_cluster_events(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    eventsList = clustersClient.get_cluster_events("0709-132523-cnhxf2p6", "1700000000000", "1744890000000")
    LOGGR.debug(eventsList)


def test_get_cluster_info(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    clusterInfo = clustersClient.get_cluster_info("0709-132523-cnhxf2p6")
    LOGGR.debug(clusterInfo)


def test_listclusters(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    clustersList = clustersClient.get_cluster_list()
    LOGGR.debug(SatDBClient.debugminijson(clustersList, "cl"))
    LOGGR.debug(f"test_listclusters1-{len(clustersList)}-type-{type(clustersList)}")
    j = 0
    for i in clustersList:
        j += 1
        SatDBClient.debugminijson(i, "cl")
    LOGGR.debug(f"test_listclusters2-{j}")


def test_get_cluster_acls(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    clusterAcls = clustersClient.get_cluster_acls("0709-132523-cnhxf2p6", "test_cluster")
    LOGGR.debug(clusterAcls)



def test_get_cluster_id_by_name(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    clusterId = clustersClient.get_cluster_id_by_name("Akash Sihag's Cluster")
    LOGGR.debug(clusterId)

def test_listinstancepools(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    instanceList = clustersClient.get_instance_pools()
    LOGGR.debug(instanceList)


def test_getinstancepoolinfo(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    instanceList = clustersClient.get_instance_pool_info("0418-031214-mooch18-pool-bpzupc7m")
    LOGGR.debug(instanceList)

def test_list_instance_profiles_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    instanceList = clustersClient.get_instance_profiles_list()
    LOGGR.debug(instanceList)






def test_start_cluster_by_name(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    clusterId = clustersClient.start_cluster_by_name("test_cluster")
    LOGGR.debug(clusterId)


def test_get_iam_role_by_cid(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    iamRole = clustersClient.get_iam_role_by_cid("cluster_id_123")
    LOGGR.debug(iamRole)


def test_get_global_init_scripts(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    initScripts = clustersClient.get_global_init_scripts()
    LOGGR.debug(initScripts)


def test_get_spark_versions(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    sparkVersions = clustersClient.get_spark_versions()
    LOGGR.debug(sparkVersions)


def test_is_spark_3(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client
    clustersClient = ClustersClient(jsonstr)
    isSpark3 = clustersClient.is_spark_3("cluster_id_123")
    LOGGR.debug(isSpark3)

