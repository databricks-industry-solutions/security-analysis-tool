'''DBSql Module'''
from core.dbclient import SatDBClient
import json

class DBSQLClient(SatDBClient):
    '''dbsql client helper'''

    def get_sqlendpoint_list(self):
        """
        Returns an array of json objects for jobruns.
        """
        # fetch all jobsruns
        endpoints_list = self.get("/sql/endpoints", version='2.0').get('endpoints', [])
        return endpoints_list
    
    def get_alerts_list(self):
        """
        Returns an array of json objects for alerts.
        """

        alertslist = self.get("/preview/sql/alerts", version='2.0').get('elements', [])
        return alertslist
    
    def get_sql_warehouse_list(self):
        """
        Returns an array of json objects for sql warehouse.
        """
    
        sqlwarehouselist = self.get("/preview/sql/data_sources", version='2.0').get('elements', [])
        return sqlwarehouselist    

    def get_sql_warehouse_listv2(self):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehousejson = self.get("/sql/warehouses", version='2.0')
        sqlwarehouselist = []
        sqlwarehouselist.append(json.loads(json.dumps(sqlwarehousejson)))
        return sqlwarehouselist    
    

    def get_sql_workspace_config(self):
        """
        Returns an array of json objects for sql warehouse config.
        """
        sqlworkspaceconfig = self.get("/sql/config/warehouses", version='2.0')
        sqlconfiglist = []
        sqlconfiglist.append(json.loads(json.dumps(sqlworkspaceconfig)))
        return sqlconfiglist   
    