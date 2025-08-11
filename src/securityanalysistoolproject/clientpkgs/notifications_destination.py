
'''notifications client module'''
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils


class NotificationsClient(SatDBClient):
    '''notifications client helper'''
    def get_notification_lists(self):
        """
        Returns an array of json objects for compliance security profile update.
        """
        # fetch all endpoints
        endpointlist= self.get(f"/notification-destinations", version='2.0').get('results', [])
        return endpointlist  

    def get_notification(self, id):
        """
        Returns an array of json objects for compliance security profile update.
        """
        # fetch all endpoints
        endpointlist= self.get(f"/notification-destinations/{id}", version='2.0').get('satelements', [])
        return endpointlist  