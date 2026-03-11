'''DBSql Module'''
from core.dbclient import SatDBClient

class DBSQLClient(SatDBClient):
    '''dbsql client helper'''
    def get_sql_warehouse_list(self):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehouselist = self.get(f"/sql/warehouses", version='2.0').get('warehouses', [])
        return sqlwarehouselist

    #for backwards compatibility
    def get_sql_warehouse_listv2(self):
        return self.get_sql_warehouse_list()

    def get_sql_warehouse_info(self, warehouse_id):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehouselist = self.get(f"/sql/warehouses/{warehouse_id}", version='2.0').get('satelements', [])
        return sqlwarehouselist

    def get_query_history(self, include_metrics=False):
        """
        Returns an array of history objects
        """
        json_params = {}
        json_params.update({'include_metrics':include_metrics})

        queryhistorylist = self.get(f"/sql/history/queries", json_params=json_params, version='2.0').get('res', [])

        return queryhistorylist
