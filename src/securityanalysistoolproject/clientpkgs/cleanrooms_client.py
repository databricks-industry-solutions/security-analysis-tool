''' Clean Rooms module'''
import time
from core.dbclient import SatDBClient

class CleanRoomsClient(SatDBClient):
    '''clean rooms helper'''

    def list_clean_rooms(self):
        ''' List clean rooms '''
        clean_list = self.get(f'/clean-rooms').get('clean_rooms', [])
        return clean_list
    
    def get_clean_room_info(self, clean_room_name):
        ''' Get clean room info '''
        clean_room_info = self.get(f'/clean-rooms/{clean_room_name}').get('satelements', [])
        return clean_room_info


    def list_clean_room_task_runs(self, clean_room_name):
        ''' List clean room task runs'''
        clean_list = self.get(f'/clean-rooms/{clean_room_name}/runs').get('runs', [])
        return clean_list

