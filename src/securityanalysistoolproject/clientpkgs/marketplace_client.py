'''Marketplace Module'''
from core.dbclient import SatDBClient
import json

class MarketplaceClient(SatDBClient):
    '''marketplace client helper'''

    def get_listing_content_metadata(self, listing_id):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/listings/{listing_id}/content", version='2.1').get("shared_data_objects",[])
        return mktlist


    def list_all_listing_fulfillments(self,listing_id):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/listings/{listing_id}/fulfillments", version='2.1').get("fulfillments",[])
        return mktlist



    def get_exchanges_for_listing(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-exchange/exchanges-for-listing", version='2.0').get("exchange_listing",[])
        return mktlist

    def get_exchange_filters(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-exchange/filters", version='2.0').get("filters",[])
        return mktlist

    def get_list_listings_for_exchange(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-exchange/listings-for-exchange", version='2.0').get("exchange_listings",[])
        return mktlist
    
    def get_list_files(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-provider/files", version='2.0').get("file_infos",[])
        return mktlist
    
    def get_mplist_providers(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-provider/providers", version='2.0').get("providers",[])
        return mktlist

    def get_mplist_listings(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-provider/listings", version='2.0').get("listings",[])
        return mktlist

    def get_personalization_requests_across_all_listings(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-provider/personalization-requests", version='2.0').get("listings",[])
        return mktlist


    def get_list_all_installations(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/installations", version='2.1').get("installations",[])
        return mktlist

    def get_mclist_listings(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/listings", version='2.1').get("listings",[])
        return mktlist
    


    def list_all_installations_for_listing(self,listing_id):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/listings/{listing_id}/installations", version='2.1').get("installations",[])
        return mktlist


    def list_all_personalization_requests(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/personalization-requests", version='2.1').get("personalization_requests",[])
        return mktlist
    
    

    def get_mclist_providers(self):
        """
        Returns an array of json objects for marketplace.
        """
        mktlist = self.get(f"/marketplace-consumer/providers", version='2.1').get("providers",[])
        return mktlist