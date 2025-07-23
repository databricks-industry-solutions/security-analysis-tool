''' clusters module'''
import time,json
from core.dbclient import SatDBClient


class QualityMonitors(SatDBClient):
    '''Quality Monitors helper'''

    def get_monitors(self, table_name=''):
        """
        Get quality monitors
        """
        qualitymonitorlst = self.get(f"/unity-catalog/tables/{table_name}/monitor", version='2.1').get('satelements', [])
        return qualitymonitorlst                      
 