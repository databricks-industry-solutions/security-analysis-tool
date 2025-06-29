''' Lakeview Rooms module'''
import time
from core.dbclient import SatDBClient

class LakeviewClient(SatDBClient):
    '''lakeview rooms helper'''


    def get_dashboards_list(self):
        ''' List dashboards '''
        dashboard = self.get(f'/lakeview/dashboards').get('dashboards', "")
        return dashboard

    def get_dashboard(self, dashboard_id):
        ''' List lakeview room details '''

        dashboard = self.get(f'/lakeview/dashboards/{dashboard_id}').get('satelements', [])
        return dashboard
    

    def get_dashboards_schedules(self, dashboard_id):
        ''' List dashboards '''
        dashboard = self.get(f'/lakeview/dashboards/{dashboard_id}/schedules').get('schedules', [])
        return dashboard
    

    def get_dashboards_schedule(self, dashboard_id, schedule_id):
        ''' List dashboards '''
        dashboard = self.get(f'/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}').get('satelements', [])
        return dashboard
        

    def get_dashboards_schedules_subscriptions(self, dashboard_id, schedule_id):
        ''' List dashboards '''
        dashboard = self.get(f'/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}/subscriptions').get('subscriptions', [])
        return dashboard
    

    def get_dashboards_schedules_subscriptions(self, dashboard_id, schedule_id, subscription_id):
        ''' List dashboards '''
        dashboard = self.get(f'/lakeview/dashboards/{dashboard_id}/schedules/{schedule_id}/subscriptions/{subscription_id}').get('satelements', [])
        return dashboard



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