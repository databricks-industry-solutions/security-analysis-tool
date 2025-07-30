from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.secrets_client import SecretsClient


def test_get_secrets_list(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    secretsclient = SecretsClient(jsonstr)
    secretsclientres = secretsclient.get_secrets([{'name':'rkm-scope'}, {'name':'redshift-profiler'}])
    print(secretsclientres)

