'''DBSql Module'''
from core.dbclient import SatDBClient
import json

class DBSQLClient(SatDBClient):
    '''dbsql client helper'''
    def get_alerts_list(self):
        """
        Returns an array of json objects for alerts.
        """
        alertslist = self.get(f"/preview/sql/alerts", version='2.0').get("elements",[])
        return alertslist

    def get_alert(self, alert_id):
        """
        Returns an array of json objects for alerts.
        """
        alertsjson = self.get(f"/preview/sql/alerts/{alert_id}", version='2.0')
        alertjsonlist = []
        alertjsonlist.append(json.loads(json.dumps(alertsjson)))
        return alertjsonlist      

    def get_dashboards_list(self, page_size, page, order, q):
        """
        Returns an array of json objects for dashboards.
        order=name | created_at
        """
        strquery=''
        if page_size:
            strquery=f'page_size={page_size}&'
        if page:
            strquery=f'{strquery}page={page}&'
        if order:
            strquery=f'{strquery}order={order}&'
        if q:
            strquery=f'{strquery}q={q}'

        strurl = f"/preview/sql/dashboards?{strquery}"            
        dashboardslist = self.get(f"{strurl}", version='2.0').get('results', [])

        return dashboardslist

    def get_dashboard(self, dashboard_id):
        """
        Returns json for dashboard.
        """
        dashjson = self.get(f"/preview/sql/dashboards/{dashboard_id}", version='2.0')
        dashjsonlist = []
        dashjsonlist.append(json.loads(json.dumps(dashjson)))
        return dashjsonlist           

    def get_sql_warehouse_permissions(self, warehouse_id):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehousejson = self.get(f"/permissions/warehouses/{warehouse_id}", version='2.0')
        sqlwjsonlist = []
        sqlwjsonlist.append(json.loads(json.dumps(sqlwarehousejson)))
        return sqlwjsonlist  

    def get_sql_warehouse_permission_level(self, warehouse_id):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehouselist = self.get(f"/permissions/warehouses/{warehouse_id}/permissionLevels", version='2.0').get('permission_levels', [])
        return sqlwarehouselist   
    
    def get_sql_warehouse_configuration(self):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehousejson = self.get(f"/sql/config/warehouses", version='2.0')
        sqlwjsonlist = []
        sqlwjsonlist.append(json.loads(json.dumps(sqlwarehousejson)))
        return sqlwjsonlist  

    def get_sql_warehouse_listv2(self):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehouselist = self.get(f"/sql/warehouses", version='2.0').get('warehouses', [])
        return sqlwarehouselist   
    
    def get_sql_warehouse(self, warehouseid):
        """
        Returns an array of json objects for sql warehouse.
        """
        sqlwarehousejson = self.get(f"/sql/warehouses/{warehouseid}", version='2.0')
        sqlwjsonlist = []
        sqlwjsonlist.append(json.loads(json.dumps(sqlwarehousejson)))
        return sqlwjsonlist    
    

    def get_sql_acl(self, objectType, objectId):
        """
        Returns acl for object.
        objectType = alerts | dashboards | data_sources | queries
        """
        sqlacljson = self.get(f"/preview/sql/permissions/{objectType}/{objectId}", version='2.0')
        sqlwjsonlist = []
        sqlwjsonlist.append(json.loads(json.dumps(sqlacljson)))
        return sqlwjsonlist    
    
    def get_queries_list(self, page_size, page, order, q):
        """
        Returns an array of json objects for dashboards.
        """
        strquery=''
        if page_size:
            strquery=f'page_size={page_size}&'
        if page:
            strquery=f'{strquery}page={page}&'
        if order:
            strquery=f'{strquery}order={order}&'
        if q:
            strquery=f'{strquery}q={q}'

        strurl = f"/preview/sql/queries?{strquery}"            
        querieslist = self.get(f"{strurl}", version='2.0').get('results', [])

        return querieslist


    def get_querydefinition(self, query_id):
        """
        Returns query definition
        """
        sqlqueryjson = self.get(f"/preview/sql/queries/{query_id}", version='2.0')
        sqlquerylist = []
        sqlquerylist.append(json.loads(json.dumps(sqlqueryjson)))
        return sqlquerylist   

    def get_query_history(self, filter_by, max_results, page_token, include_metrics):
        """
        Returns an array of history objects
        """
        strquery=''
        if filter_by:
            strquery=f'filter_by={filter_by}&'
        if max_results:
            strquery=f'{strquery}max_results={max_results}&'
        if page_token:
            strquery=f'{strquery}page_token={page_token}&'
        if include_metrics:
            strquery=f'{strquery}include_metrics={include_metrics}'

        strurl = f"/sql/history/queries?{strquery}"            
        queryhistorylist = self.get(f"{strurl}", version='2.0').get('res', [])

        return queryhistorylist

