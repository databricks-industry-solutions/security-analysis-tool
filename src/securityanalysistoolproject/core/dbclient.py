'''dbclient'''
import json
import base64
import time
import urllib3
import requests
from core.logging_utils import LoggingUtils
from core import parser as pars
import msal

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
            self._use_sp_auth = configs['use_sp_auth'].strip()
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
        else:    
            user_pass = base64.b64encode(f"{self._master_name}:{self._master_password}".encode("ascii")).decode("ascii")
            self._url = "https://accounts.cloud.databricks.com" #url for accounts api
            self._token = {
                "Authorization" : f"Basic {user_pass}",
                "User-Agent": "databricks-sat/0.1.0"
            }
            if (self._use_sp_auth): # Service Principal authentication flow
                oauth = self.getAWSTokenwithOAuth(True, self._client_id, self._client_secret)
                self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0"
                } 

    def _update_token(self):
        '''update token in http header'''
        self._url=self._raw_url #accounts api uses a different url
        if self._use_mastercreds is False:
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
                
                if self._use_sp_auth: # Service Principal authentication flow
                    oauth = self.getAWSTokenwithOAuth(False, self._client_id, self._client_secret)
                    self._token = {
                    "Authorization": f"Bearer {oauth}",
                    "User-Agent": "databricks-sat/0.1.0"
                    } 
        return None
   
    
    def test_connection(self, master_acct=False):
        '''test connection to workspace and master account'''
        if master_acct: #master acct may use a different credential
            self._update_token_master()
            if (self._cloud_type == 'azure'):
                results = requests.get(f'{self._url}/subscriptions/{self._subscription_id}/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01',
                            headers=self._token, timeout=60)
            else:    
                results = requests.get(f'{self._url}/api/2.0/accounts/{self._account_id}/workspaces',
                            headers=self._token, timeout=60)
        else:
            self._update_token()
            results = requests.get(f'{self._url}/api/2.0/clusters/spark-versions',
                headers=self._token, timeout=60)
        http_status_code = results.status_code
        if http_status_code != 200:
            LOGGR.info("Error. Either the credentials have expired or the \
                    credentials don't have proper permissions. Re-verify secrets")
            LOGGR.info(results.reason)
            LOGGR.info(results.text)
            raise Exception(f'Test connection failed {results.reason}')
        return True



    def get(self, endpoint, json_params=None, version='2.0', master_acct=False):
        '''http get helper'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()

        while True:
            if self._cloud_type == 'azure' and master_acct: #Azure accounts API format is different
                full_endpoint = f"{self._url}/{endpoint}"
            else:
                full_endpoint = f"{self._url}/api/{version}{endpoint}"
            
            LOGGR.debug(f"Get: {full_endpoint}")

            if json_params:
                raw_results = requests.get(full_endpoint, headers=self._token, params=json_params, timeout=60)
            else:
                raw_results = requests.get(full_endpoint, headers=self._token, timeout=60)

            http_status_code = raw_results.status_code
            if http_status_code in SatDBClient.http_error_codes:
                raise Exception(f"Error: GET request failed with code {http_status_code}\n{raw_results.text}")
            results = raw_results.json()
            LOGGR.debug(json.dumps(results, indent=4, sort_keys=True))

            if isinstance(results, list):
                results = {'elements': results}
            results['http_status_code'] = http_status_code
            return results

    def http_req(self, http_type, endpoint, json_params, version='2.0', files_json=None, master_acct=False):
        '''helpers for http post put patch'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()
        if version:
            ver = version
        while True:
            full_endpoint = f"{self._url}/api/{ver}{endpoint}"
            LOGGR.debug(f"http type endpoint -> {http_type}: {full_endpoint}")
            if json_params:
                if http_type == 'post':
                    if files_json:
                        raw_results = requests.post(full_endpoint, headers=self._token,
                                                    data=json_params, files=files_json, timeout=60)
                    else:
                        raw_results = requests.post(full_endpoint, headers=self._token,
                                                    json=json_params, timeout=60)
                if http_type == 'put':
                    raw_results = requests.put(full_endpoint, headers=self._token,
                                               json=json_params, timeout=60)
                if http_type == 'patch':
                    raw_results = requests.patch(full_endpoint, headers=self._token,
                                                 json=json_params, timeout=60)
            else:
                LOGGR.info("Must have a payload in json_args param.")
                return {}


            http_status_code = raw_results.status_code
            if http_status_code in SatDBClient.http_error_codes:
                raise Exception(f"Error: {http_type} request failed with code {http_status_code}\n{raw_results.text}")
            results = raw_results.json()

            LOGGR.debug(json.dumps(results, indent=4, sort_keys=True))
            # if results are empty, let's return the return status
            if results:
                results['http_status_code'] = raw_results.status_code
                return results
            else:
                return {'http_status_code': raw_results.status_code}

    def post(self, endpoint, json_params, version='2.0', files_json=None, master_acct=False):
        '''post'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()
        return self.http_req('post', endpoint, json_params, version, files_json)

    def put(self, endpoint, json_params, version='2.0', master_acct=False):
        '''put'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()
        return self.http_req('put', endpoint, json_params, version)

    def patch(self, endpoint, json_params, version='2.0', master_acct=False):
        '''patch'''
        if master_acct:
            self._update_token_master()
        else:
            self._update_token()
        return self.http_req('patch', endpoint, json_params, version)


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
        if baccount is True:
            response = requests.post(
                f'{self._url}/oidc/accounts/{self._account_id}/v1/token',
                auth=(client_id, client_secret),
                data = {
                    "grant_type": "client_credentials",
                    "scope": "all-apis"
                }
            )
        else: #workspace
            response = requests.post(
            f'{self._url}/oidc/v1/token',
            auth=(client_id, client_secret),
            data = {
                "grant_type": "client_credentials",
                "scope": "all-apis"
            }
        )
        if response is not None and response.status_code == 200:
            return response.json()['access_token']
        if response is not None and response.status_code == 200:
            return response.json()['access_token']
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

