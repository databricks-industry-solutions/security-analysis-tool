'''DBSql Module'''
from core.dbclient import SatDBClient
import json

class DBSQLClient(SatDBClient):
    '''dbsql client helper'''
    def get_alerts_list(self):
        """
        Returns an array of json objects for alerts.
        """
        alertslist = self.get(f"/sql/alerts", version='2.0').get("results",[])
        return alertslist

    def get_alert(self, alert_id):
        """
        Returns an array of json objects for alerts.
        """
        alertslist = self.get(f"/sql/alerts/{alert_id}", version='2.0').get("satelements", [])
        return alertslist

    #deprecated. implemented in the permissions_client.py
    def get_sql_acl(self, objectType, objectId):
        """
        Returns acl for object.
        objectType = alerts | dashboards | data_sources | queries
        """
        sqlwjsonlist = self.get(f"/preview/sql/permissions/{objectType}/{objectId}", version='2.0').get('access_control_list', [])
        return sqlwjsonlist    
    
    def get_queries_list(self, filter_ids=None):
        """
        Returns an array of json objects for queries
        """         
        querieslist = self.get(f"/sql/queries", version='2.0').get('results', [])

        return querieslist        

    def get_query(self, query_id):
        """
        Returns query definition
        """
        sqlquerylist = self.get(f"/sql/queries/{query_id}", version='2.0').get('satelements', [])
        return sqlquerylist   
    
    def get_sql_warehouse_configuration(self):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehouselist = self.get(f"/sql/config/warehouses", version='2.0').get('satelements', [])
        return sqlwarehouselist  

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

    # def get_dashboards_list(self, page_size, page, order, q):
    #     """
    #     Returns an array of json objects for dashboards.
    #     order=name | created_at
    #     """
    #     strquery=''
    #     if page_size:
    #         strquery=f'page_size={page_size}&'
    #     if page:
    #         strquery=f'{strquery}page={page}&'
    #     if order:
    #         strquery=f'{strquery}order={order}&'
    #     if q:
    #         strquery=f'{strquery}q={q}'

    #     strurl = f"/preview/sql/dashboards?{strquery}"            
    #     dashboardslist = self.get(f"{strurl}", version='2.0').get('results', [])

    #     return dashboardslist

    # def get_dashboard(self, dashboard_id):
    #     """
    #     Returns json for dashboard.
    #     """
    #     dashjson = self.get(f"/preview/sql/dashboards/{dashboard_id}", version='2.0')
    #     dashjsonlist = []
    #     dashjsonlist.append(json.loads(json.dumps(dashjson)))
    #     return dashjsonlist           


    #permissions are implemented in the permissions_client.py
    # def get_sql_warehouse_permissions(self, warehouse_id):
    #     """
    #     Returns an array of json objects for sql warehouse.
    #     """
    #     sqlwarehousejsonlist = self.get(f"/permissions/warehouses/{warehouse_id}", version='2.0').get('satelements', [])
    #     # sqlwjsonlist = []
    #     # sqlwjsonlist.append(json.loads(json.dumps(sqlwarehousejson)))
    #     return sqlwarehousejsonlist  

    # def get_sql_warehouse_permission_level(self, warehouse_id):
    #     """
    #     Returns an array of json objects for sql warehouse.
    #     """
    #     sqlwarehouselist = self.get(f"/permissions/warehouses/{warehouse_id}/permissionLevels", version='2.0').get('permission_levels', [])
    #     return sqlwarehouselist   
    

    
    # def get_sql_warehouse(self, warehouseid):
    #     """
    #     Returns an array of json objects for sql warehouse.
    #     """
    #     sqlwarehousejson = self.get(f"/sql/warehouses/{warehouseid}", version='2.0')
    #     sqlwjsonlist = []
    #     sqlwjsonlist.append(json.loads(json.dumps(sqlwarehousejson)))
    #     return sqlwjsonlist    
    


    



    # def get_queries_list(self, page_size, page, order, q):
    #     """
    #     Returns an array of json objects for dashboards.
    #     """
    #     strquery=''
    #     if page_size:
    #         strquery=f'page_size={page_size}&'
    #     if page:
    #         strquery=f'{strquery}page={page}&'
    #     if order:
    #         strquery=f'{strquery}order={order}&'
    #     if q:
    #         strquery=f'{strquery}q={q}'

    #     strurl = f"/preview/sql/queries?{strquery}"            
    #     querieslist = self.get(f"{strurl}", version='2.0').get('results', [])

    #     return querieslist






