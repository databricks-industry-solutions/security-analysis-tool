'''dbclient'''
import json
import base64
import time
import urllib3
import requests
from core.logging_utils import LoggingUtils
from core import parser as pars
import msal
import re

urllib3.disable_warnings(category = urllib3.exceptions.InsecureRequestWarning)

LOGGR=None

if LOGGR is None:
    LOGGR = LoggingUtils.get_logger()


class SatDBClient:
    """
    Rest API Wrapper for Databricks APIs
    """
    # set of http error codes to throw an exception if hit. Handles client and auth errors
    http_error_codes = [401, 403]

    def __init__(self, inp_configs):
        self._inp_configs = inp_configs
        configs = pars.parse_input_jsonargs(inp_configs)
        self._configs=configs
        self._workspace_id = configs['workspace_id']
        self._raw_url = configs['url'].strip()
        self._url=self._raw_url
        self._account_id = configs['account_id'].strip()
        self._cloud_type = self.parse_cloud_type()
        self._verbosity = LoggingUtils.get_log_level(configs['verbosity'])
        LoggingUtils.set_logger_level(self._verbosity)
        self._cluster_id=configs['clusterid'].strip()
        self._token = ''
        self._raw_token = configs['token'].strip()
        if isinstance(configs['use_mastercreds'], str):
            self._use_mastercreds = pars.str2bool(configs['use_mastercreds'])
        else:
            self._use_mastercreds = configs['use_mastercreds']
        self._proxies = configs.get('proxies', {})

        #Azure
        if 'azure' in self._cloud_type:
            self._subscription_id = configs['subscription_id'].strip()
            self._client_id = configs['client_id'].strip()
            self._client_secret = configs['client_secret'].strip()
            self._tenant_id = configs['tenant_id'].strip()
        elif 'gcp' in self._cloud_type: #gcp
            self._master_name = configs['mastername'].strip()
            self._master_password = configs['masterpwd'].strip()
        elif 'aws' in self._cloud_type: #aws
            self._master_name = configs['mastername'].strip()
            self._master_password = configs['masterpwd'].strip()
            self._use_sp_auth = pars.str2bool(configs['use_sp_auth'])
            self._client_id = configs['client_id'].strip()
            self._client_secret = configs['client_secret'].strip()   


    def _update_token_master(self):
        '''update token master in http header'''
        LOGGR.info("in _update_token_master")
        if(self._cloud_type == 'gcp'):
            self._url = "https://accounts.gcp.databricks.com"  #url for gcp accounts api
            self._token = {
                "Authorization": f"Bearer {self._master_name}",
                "X-Databricks-GCP-SA-Access-Token": f"{self._master_password}",
                "User-Agent": "databricks-sat/0.1.0"
            }
            LOGGR.info(f'GCP self._token {self._token}')
        elif(self._cloud_type == 'azure'):
            self._url = "https://management.azure.com"
            self._master_password = self.getAzureTokenWithMSAL('msmgmt')
            self._token = {
                "Authorization": f"Bearer {self._master_password}",
                "User-Agent": "databricks-sat/0.1.0"
            }
        else:     #AWS
            self._url = "https://accounts.cloud.databricks.com" #url for accounts api
            if (self._use_sp_auth): # Service Principal authentication flow
                oauth = self.getAWSTokenwithOAuth(True, self._client_id, self._client_secret)
                self._token = {
                    "Authorization": f"Bearer {oauth}",
                    "User-Agent": "databricks-sat/0.1.0"
                } 
            else:
                LOGGR.info('OAuth flow for master')
                user_pass = base64.b64encode(f"{self._master_name}:{self._master_password}".encode("ascii")).decode("ascii")
                self._token = {
                    "Authorization" : f"Basic {user_pass}",
                    "User-Agent": "databricks-sat/0.1.0"
                }

    def _update_token(self):
        '''update token in http header'''
        self._url=self._raw_url #accounts api uses a different url
        if self._cloud_type == 'aws' and self._use_sp_auth is True:# AWS Service Principal authentication flow
            LOGGR.info("OAuth flow for workspace")
            oauth = self.getAWSTokenwithOAuth(False, self._client_id, self._client_secret)
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0"
            } 
        elif self._use_mastercreds is False:
            self._token = {
                "Authorization": f"Bearer {self._raw_token}",
                "User-Agent": "databricks-sat/0.1.0"
            }
        else: # use master creds for workspaces also
            if(self._cloud_type == 'gcp'):
                self._token = {
                "Authorization": f"Bearer {self._raw_token}",
                "User-Agent": "databricks-sat/0.1.0"
                }   
                LOGGR.info(f'In GCP  self._url {self._url}')
            elif (self._cloud_type == 'azure'):
                self._raw_token = self.getAzureTokenWithMSAL('dbmgmt')

                self._token = {
                "Authorization": f"Bearer {self._raw_token}",
                "User-Agent": "databricks-sat/0.1.0"
                }      
            else:    
                user_pass = base64.b64encode(f"{self._master_name}:{self._master_password}".encode("ascii")).decode("ascii")
                self._token = {
                    "Authorization" : f"Basic {user_pass}",
                    "User-Agent": "databricks-sat/0.1.0"
                }
        return None
    
    def get_temporary_oauth_token(self):
        self._update_token()
        if self._token is None:
            return None
        temptok = self._token.get("Authorization","").split(' ')
        if(len(temptok) > 1):
            return (temptok[1])
        else:
            return None

    
    def test_connection(self, master_acct=False):
        '''test connection to workspace and master account'''
        if master_acct: #master acct may use a different credential
            self._update_token_master()
            if (self._cloud_type == 'azure'):
                results = requests.get(f'{self._url}/subscriptions/{self._subscription_id}/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01',
                            headers=self._token, timeout=60, proxies=self._proxies)
            else:    
                results = requests.get(f'{self._url}/api/2.0/accounts/{self._account_id}/workspaces',
                            headers=self._token, timeout=60, proxies=self._proxies)
        else:
            self._update_token()
            results = requests.get(f'{self._url}/api/2.0/clusters/spark-versions',
                headers=self._token, timeout=60, proxies=self._proxies)
        http_status_code = results.status_code
        if http_status_code != 200:
            LOGGR.info("Error. Either the credentials have expired or the \
                    credentials don't have proper permissions. Re-verify secrets")
            LOGGR.info(results.reason)
            LOGGR.info(results.text)
            raise Exception(f'Test connection failed {results.reason}')
        return True


    @staticmethod
    def debugminijson(jsonelem, title=''):
        '''debugging function to print limited json'''
        debugs=json.dumps(jsonelem, indent=1, sort_keys=True)
        LOGGR.debug(f"{title}-=-=-{debugs[:1250]}-=-=-{type(jsonelem)}") 

    @staticmethod
    def getNumLists(resp):
        '''We expect one list in the response. If not, return the whole response'''
        numlists=0
        numdicts=0
        #check if error message
        if 'error_code' in resp and 'message' in resp:
            LOGGR.debug(f"\t\t\t$error_code={resp['error_code']} {resp['message']}")
            return numlists, numdicts
        if isinstance(resp, list): # some like in accounts return a list as outer
            return numlists, numdicts
        for ielem in resp:
            if isinstance(resp[ielem], list):
                numlists+=1
            if isinstance(resp[ielem], dict):
                numdicts+=1
        LOGGR.debug(f"\t\t\t$numlists={numlists}") #getNumLists-20-type-<class 'dict'>
        return numlists, numdicts       

    @staticmethod
    def getRespArray(resp):
        '''if the response contains one list we are in the majority situation. 
        If not, return the whole response wrapped in a list'''
        arrdict=[]
        numlists, numdicts=SatDBClient.getNumLists(resp)
        if numlists == 1 and numdicts == 0: #one list and no dict
            for ielem in resp:
                if isinstance(resp[ielem], list):
                    LOGGR.debug(f"\t\t%getRespArray-{len(resp[ielem])}-type-{type(resp[ielem][0])}") #getRespArray-20-type-<class 'dict'>
                    return ielem, resp[ielem]
        else:    #add the whole resp if there is more than one dict and one list or no lists
            if not resp:
                resp={}
            arrdict.append(resp)
        return 'satelements', arrdict
  
    # tuple with dict {elem:[..]}, http_status_code
    def flatten(nestarr):
        flatarr=[]
        flatelem=''
        flathttpstatuscode=200
        LOGGR.debug(f"\t\t*flatten1-{len(nestarr)}-type-{type(nestarr)}") #flatten1-10-type-<class 'list'>
        LOGGR.debug(f"\t\t*flatten2-{len(nestarr[0])}-type-{type(nestarr[0])}") #flatten2-2-type-<class 'tuple'>
        for tup_elem in nestarr:
            for dictkey in tup_elem[0]:
                if flatelem and flatelem != dictkey:
                    LOGGR.debug(f"\t\t*different keys detected {flatelem}-{dictkey}")
                flatelem=dictkey
                flathttpstatuscode=tup_elem[1]
                LOGGR.debug(f"\t\t*flatten3-{len(tup_elem[0][dictkey])}-type-{type(tup_elem[0][dictkey])}") #flatten3-20-type-<class 'list'>
                flatarr.append(tup_elem[0][dictkey]) #append lists
        flatarr_1 = [fl0 for xs in flatarr for fl0 in xs] #flatten list of lists.
        LOGGR.debug(f"\t\t*flatten4-{len(flatarr_1)}-type-{type(flatarr_1)}-type-{type(flatarr_1[0])}") #flatten4-200-type-<class 'list'>-type-<class 'dict'>
        return flatelem, flatarr_1, flathttpstatuscode
    
    #return dictionary of elem and list of values
    def get_paginated(self, endpoint, reqtype="get", json_params=None, files_json=None, is_paginated=False):
        NUM_PAGES=10 #throttle as needed
        resultsArray=[]
        elementName=''
        for i in range(NUM_PAGES):
            LOGGR.debug(f"{endpoint}---{json_params}")
            if 'get' in reqtype:
                raw_results = requests.get(endpoint, headers=self._token, params=json_params, timeout=60, proxies=self._proxies)
            elif 'post' in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")
                if files_json:
                    raw_results = requests.post(endpoint, headers=self._token,
                                                data=json_params, files=files_json, timeout=60, proxies=self._proxies)
                else:
                    raw_results = requests.post(endpoint, headers=self._token,
                                                json=json_params, timeout=60, proxies=self._proxies)
            elif 'put' in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")                
                raw_results = requests.put(endpoint, headers=self._token,
                                        json=json_params, timeout=60, proxies=self._proxies)                    
            elif 'patch' in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")                
                raw_results = requests.patch(endpoint, headers=self._token,
                                json=json_params, timeout=60, proxies=self._proxies)   

            http_status_code = raw_results.status_code
            if http_status_code in SatDBClient.http_error_codes:
                raise Exception(f"Error: request failed with code {http_status_code}\n{raw_results.text}")
            results = raw_results.json()
            #LOGGR.debug('-------------')
            #LOGGR.debug(json.dumps(results, indent=4, sort_keys=True)) #for debug
            elementName, resultsArray=SatDBClient.getRespArray(results)
            retdict={elementName:resultsArray}
            yield (retdict, http_status_code)
            
            
            LOGGR.debug(f'\t\tyielding-{retdict}')
            
            if http_status_code < 200 or http_status_code > 299:
                break
            
            if not is_paginated: #not paginated
                break
            
            if 'next_page_token' not in results or not results['next_page_token']: #first condition should not happen. But assume end.
                #LOGGR.debug(f'\t\t{json.dumps(results, indent=4, sort_keys=True)}')
                break

            if json_params is None:
                json_params = {}
            page_token=results['next_page_token']
            json_params.update({'page_token':page_token})

   

    @staticmethod
    def ispaginatedCall(endpoint):
        paginatedurls = [
            '/api/2.0/accounts/.+/federationPolicies',
            '/api/2.0/accounts/.+/network-connectivity-configs',
            '/api/2.0/accounts/.+/network-connectivity-configs/.+/private-endpoint-rules',
            '/api/2.0/accounts/.+/servicePrincipals/.+/credentials/secrets',
            '/api/2.0/accounts/.+/oauth2/custom-app-integrations',
            '/api/2.0/accounts/.+/oauth2/published-app-integrations',
            '/api/2.0/apps',
            '/api/2.0/apps/.+/deployments',
            '/api/2.0/clean-rooms',
            '/api/2.0/clean-rooms/.+/runs',
            '/api/2.0/fs/directories/.+',
            '/api/2.0/lakeview/dashboards',
            '/api/2.0/lakeview/dashboards/.+/schedules',
            '/api/2.0/lakeview/dashboards/.+/schedules/.+/subscriptions',
            '/api/2.0/marketplace-exchange/exchanges-for-listing',
            '/api/2.0/marketplace-exchange/filters',
            '/api/2.0/marketplace-exchange/listings-for-exchange',
            '/api/2.0/marketplace-provider/providers'
            '/api/2.0/marketplace-provider/files',
            '/api/2.0/marketplace-provider/listings',
            '/api/2.0/marketplace-provider/personalization-requests',
            '/api/2.0/mlflow/artifacts/list',
            '/api/2.0/mlflow/experiments/list',
            '/api/2.0/mlflow/registered-models/list',
            '/api/2.0/mlflow/registry-webhooks/list',
            '/api/2.0/mlflow/runs/search',
            '/api/2.0/pipelines',
            '/api/2.0/pipelines/.+/events',
            '/api/2.0/pipelines/.+/updates',
            '/api/2.0/policies/clusters/list-compliance',
            '/api/2.0/policies/jobs/list-compliance',
            '/api/2.0/policy-families',
            '/api/2.0/repos',
            '/api/2.0/sql/history/queries',
            '/api/2.0/sql/queries',
            '/api/2.0/vector-search/endpoints',
            '/api/2.0/vector-search/indexes',
            '/api/2.0/vector-search/indexes/.+/query', #not used
            '/api/2.0/vector-search/indexes/.+/query-next-page', #not used
            '/api/2.1/accounts/.+/budget-policies',
            '/api/2.1/clusters/events',
            '/api/2.1/clusters/list',
            '/api/2.1/marketplace-consumer/installations',
            '/api/2.1/marketplace-consumer/listings',
            '/api/2.1/marketplace-consumer/listings/.+/content',
            '/api/2.1/marketplace-consumer/listings/.+/fulfillments',
            '/api/2.1/marketplace-consumer/listings/.+/installations',
            '/api/2.1/marketplace-consumer/personalization-requests',
            '/api/2.1/marketplace-consumer/providers',
            '/api/2.1/unity-catalog/bindings/.+/.+',
            '/api/2.1/unity-catalog/catalogs',
            '/api/2.1/unity-catalog/connections',
            '/api/2.1/unity-catalog/credentials'
            '/api/2.1/unity-catalog/external-locations',
            '/api/2.1/unity-catalog/functions',
            '/api/2.1/unity-catalog/metastores/.+/systemschemas',#not used
            '/api/2.1/unity-catalog/models',
            '/api/2.1/unity-catalog/models/.+/versions',
            '/api/2.1/unity-catalog/providers',
            '/api/2.1/unity-catalog/recipients',
            '/api/2.1/unity-catalog/recipients/.+/share-permissions',
            '/api/2.1/unity-catalog/schemas',
            '/api/2.1/unity-catalog/tables',
            '/api/2.1/unity-catalog/volumes',
            '/api/2.2/jobs/get',
            '/api/2.2/jobs/list',
            '/api/2.2/jobs/runs/get',
            '/api/2.2/jobs/runs/list'
            ]
        for url in paginatedurls:
            if re.search(url, endpoint, flags=re.IGNORECASE) is not None:
                LOGGR.debug("Paginated call...")
                return True
        return False



    def http_req(self, http_type, endpoint, json_params, version='2.0', files_json=None, master_acct=False):
        '''helpers for http post put patch'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()

        if self._cloud_type == 'azure' and master_acct: #Azure accounts API format is different
            full_endpoint = f"{self._url}/{endpoint}"
        else:
            full_endpoint = f"{self._url}/api/{version}{endpoint}"

        LOGGR.debug(f"http type endpoint -> {http_type}: {full_endpoint}")
        is_paginated = True if SatDBClient.ispaginatedCall(full_endpoint)== True else False
        respageslst = list(self.get_paginated(full_endpoint, http_type, json_params, files_json, is_paginated))
        LOGGR.debug(f"get1-{len(respageslst)}-type-{type(respageslst)}-type-{type(respageslst[0])}") #get1-10-type-<class 'list'>-type-<class 'tuple'>
        for i in respageslst:
            LOGGR.debug(f"get2-{len(i)}-type-{type(i)}-{len(i[0])}-{type(i[0])}") #get2-2-type-<class 'tuple'>
        reselement, resflattenpages, http_status_code = SatDBClient.flatten(respageslst)
        LOGGR.debug(f"get3-{len(resflattenpages)}") #get3-200
        #SatDBClient.debugminijson(resflattenpages, "l1resflattenpages")
        #print(f"l2-{len(resflattenpages[0])}-type-{type(resflattenpages[0])}")
        #SatDBClient.debugminijson(resflattenpages[0], "l2resflattenpages")
        results = {reselement:resflattenpages, 'http_status_code': http_status_code}
        return results

    def get(self, endpoint, json_params=None, version='2.0', master_acct=False):
        '''get'''
        return self.http_req('get', endpoint, json_params, version, None, master_acct)        

    def post(self, endpoint, json_params, version='2.0', files_json=None, master_acct=False):
        '''post'''
        return self.http_req('post', endpoint, json_params, version, files_json, master_acct)

    def put(self, endpoint, json_params, version='2.0', master_acct=False):
        '''put'''
        return self.http_req('put', endpoint, json_params, version, None, master_acct)

    def patch(self, endpoint, json_params, version='2.0', master_acct=False):
        '''patch'''
        return self.http_req('patch', endpoint, json_params, version, None, master_acct)


    def get_execution_context(self):
        '''execute with context'''
        self._update_token()
        LOGGR.debug("Creating remote Spark Session")

        cid=self._cluster_id
        #time.sleep(5)
        ec_payload = {"language": "python",
                    "clusterId": cid}
        ec_var = self.post('/contexts/create', json_params=ec_payload, version="1.2")
        # Grab the execution context ID
        ec_id = ec_var.get('id', None)
        if ec_id is None:
            LOGGR.info('Remote session error. Cluster may not be started')
            LOGGR.info(ec_var)
            raise Exception("Remote session error. Cluster may not be started.")
        return ec_id


    def submit_command(self, ec_id, cmd):
        '''submit a command '''
        self._update_token()
        cid=self._cluster_id
        # This launches spark commands and print the results. We can pull out the text results from the API
        command_payload = {'language': 'python',
                        'contextId': ec_id,
                        'clusterId': cid,
                        'command': cmd}
        command = self.post('/commands/execute',
                            json_params=command_payload,
                            version="1.2")

        com_id = command.get('id', None)
        if com_id is None:
            LOGGR.error(command)
        # print('command_id : ' + com_id)
        result_payload = {'clusterId': cid, 'contextId': ec_id, 'commandId': com_id}

        resp = self.get('/commands/status', json_params=result_payload, version="1.2")
        is_running = self.get_key(resp, 'status')

        # loop through the status api to check for the 'running' state call and sleep 1 second
        while (is_running == "Running") or (is_running == 'Queued'):
            resp = self.get('/commands/status', json_params=result_payload, version="1.2")
            is_running = self.get_key(resp, 'status')
            time.sleep(1)
        _ = self.get_key(resp, 'status')
        end_results = self.get_key(resp, 'results')
        if end_results.get('resultType', None) == 'error':
            LOGGR.error(end_results.get('summary', None))
        return end_results


    @staticmethod
    def get_key(http_resp, key_name):
        '''get key from json of response'''
        value = http_resp.get(key_name, None)
        if value is None:
            raise ValueError('Unable to find key ' + key_name)
        return value

    def whoami(self):
        """
        get current user userName from SCIM API
        :return: username string
        """
        user_name = self.get('/preview/scim/v2/Me').get('userName')
        return user_name


    def get_url(self):
        '''getter - url'''
        return self._url

    def get_latest_spark_version(self):
        '''get the latest spark version. used for connection test'''
        versions = self.get('/clusters/spark-versions')['versions']
        v_sorted = sorted(versions, key=lambda i: i['key'], reverse=True)
        for vsparkver in v_sorted:
            img_type = vsparkver['key'].split('-')[1][0:5]
            if img_type == 'scala':
                return vsparkver


    def get_cloud_type(self):
        '''return cloud type'''
        return self._cloud_type

    def parse_cloud_type(self):
        '''parse cloud type'''
        cloudtype=''
        if 'azuredatabricks.net' in self._raw_url:
            cloudtype='azure'
        if 'cloud.databricks' in self._raw_url:
            cloudtype='aws'
        if 'gcp.databricks' in self._raw_url:
            cloudtype='gcp'
        return cloudtype

    def getAzureTokenWithMSAL(self, scopeType):
        """
        validate client id and secret from microsoft and google
        for scopes https://learn.microsoft.com/en-us/azure/databricks/dev-tools/api/latest/aad/app-aad-token#get-azure-ad-tokens-by-using-a-web-browser-and-curl
        microsoft scope for management api 'https://management.azure.com/.default'
        databricks scope for rest api '2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'
        """
        try:
            if self._cloud_type != 'azure':
                raise Exception('works only for Azure')
            scopes=[]
            if 'msmgmt' in scopeType.lower():
                scopes = ['https://management.azure.com/.default'] #ms scope 
            else:
                scopes = ['2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default'] #databricks scope

            app = msal.ConfidentialClientApplication(
                client_id=self._client_id,
                client_credential=self._client_secret,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            )

            # The pattern to acquire a token looks like this.
            token = None
            # Firstly, looks up a token from cache
            token = app.acquire_token_silent(scopes=scopes, account=None)

            if not token:
                token = app.acquire_token_for_client(scopes=scopes)
            
            if token.get("access_token") is None:
                print(['no token'])
            else:
                return(token.get("access_token"))
                print(token.get("access_token"))


        except Exception as error:
            print(f"Exception {error}")
            print(str(error))


    def getAWSTokenwithOAuth(self, baccount, client_id, client_secret):
        '''generates OAuth token for Service Principal authentication flow'''
        '''baccount if generating for account. False for workspace'''
        response = None
        user_pass = (self._client_id,self._client_secret)
        oidc_token = {
            "User-Agent": "databricks-sat/0.1.0"
        }
        json_params = {
            "grant_type": "client_credentials",
            "scope": "all-apis"
        }
              
        if baccount is True:
            full_endpoint = f"https://accounts.cloud.databricks.com/oidc/accounts/{self._account_id}/v1/token" #url for accounts api  
        else: #workspace
            full_endpoint = f'{self._raw_url}/oidc/v1/token'

        response = requests.post(full_endpoint, headers=oidc_token,
                                    auth=user_pass, data=json_params, timeout=60, proxies=self._proxies)  

        if response is not None and response.status_code == 200:
            return response.json()['access_token']
        LOGGR.debug(json.dumps(response.json()))
        return None


    # @staticmethod
    # def listdir(f_path):
    #     ls = os.listdir(f_path)
    #     for x in ls:
    #         # remove hidden directories / files from function
    #         if x.startswith('.'):
    #             continue
    #         yield x

    # @staticmethod
    # def walk(f_path):
    #     for my_root, my_subdir, my_files in os.walk(f_path):
    #         # filter out files starting with a '.'
    #         filtered_files = list(filter(lambda x: not x.startswith('.'), my_files))
    #         yield my_root, my_subdir, filtered_files
    # @staticmethod
    # def delete_dir_if_empty(local_dir):
    #     if len(os.listdir(local_dir)) == 0:
    #         os.rmdir(local_dir)


    # @staticmethod
    # def my_map(F, items):
    #     ''''''
    #     to_return = []
    #     for elem in items:
    #         to_return.append(F(elem))
    #     return to_return

    # def get(self, endpoint, json_params=None, version='2.0', master_acct=False):
    #     '''http get helper'''
    #     if master_acct:
    #         self._update_token_master()
    #     else:
    #         self._update_token()


    #     while True:
    #         if self._cloud_type == 'azure' and master_acct: #Azure accounts API format is different
    #             full_endpoint = f"{self._url}/{endpoint}"
    #         else:
    #             full_endpoint = f"{self._url}/api/{version}{endpoint}"
            
    #         LOGGR.debug(f"Get: {full_endpoint}")

    #         if SatDBClient.ispaginatedCall(full_endpoint):
    #             respageslst = list(self.get_paginated(full_endpoint, json_params))
    #             LOGGR.debug(f"get1-{len(respageslst)}-type-{type(respageslst)}-type-{type(respageslst[0])}") #get1-10-type-<class 'list'>-type-<class 'tuple'>
    #             for i in respageslst:
    #                 LOGGR.debug(f"get2-{len(i)}-type-{type(i)}-{len(i[0])}-{type(i[0])}") #get2-2-type-<class 'tuple'>
    #             reselement, resflattenpages = SatDBClient.flatten(respageslst)
    #             LOGGR.debug(f"get3-{len(resflattenpages)}") #get3-200
    #             #SatDBClient.debugminijson(resflattenpages, "l1resflattenpages")
    #             #print(f"l2-{len(resflattenpages[0])}-type-{type(resflattenpages[0])}")
    #             #SatDBClient.debugminijson(resflattenpages[0], "l2resflattenpages")
    #             results = {reselement:resflattenpages}

    #         else:    
    #             if json_params:
    #                 raw_results = requests.get(full_endpoint, headers=self._token, params=json_params, timeout=60, proxies=self._proxies)
    #             else:
    #                 raw_results = requests.get(full_endpoint, headers=self._token, timeout=60, proxies=self._proxies)

    #             http_status_code = raw_results.status_code
    #             if http_status_code in SatDBClient.http_error_codes:
    #                 raise Exception(f"Error: GET request failed with code {http_status_code}\n{raw_results.text}")
    #             results = raw_results.json()
    #             LOGGR.debug(json.dumps(results, indent=4, sort_keys=True))
    #             if isinstance(results, list):
    #                 results = {'elements': results}
    #             results['http_status_code'] = http_status_code
    #         return results