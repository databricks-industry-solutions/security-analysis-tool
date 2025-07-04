from core.logging_utils import LoggingUtils
from core import parser as pars
from core.dbclient import SatDBClient
from clientpkgs.marketplace_client import MarketplaceClient


def test_get_exchanges_for_listing(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    jsonstr = get_db_client 
    marketplaceobj = MarketplaceClient(jsonstr)
    marketplaceres = marketplaceobj.get_exchanges_for_listing()
    print(marketplaceres)
