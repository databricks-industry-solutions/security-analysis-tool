"""REST API client for Databricks APIs supporting AWS, Azure, and GCP cloud providers.

This module provides the ``SatDBClient`` class, which wraps Databricks REST API
calls with automatic OAuth token management, pagination handling, and response
normalization across all three supported cloud platforms.
"""

import json
import logging
import re
import time
from enum import IntEnum

import msal
import requests
import urllib3

from core import parser as pars
from core.logging_utils import LoggingUtils

urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)

LOGGR: logging.Logger = LoggingUtils.get_logger()


def mask_data(data, unmasked_length=4, mask_char="*") -> str:
    """Mask all but the last ``unmasked_length`` characters of a string.

    Args:
        data: The string to mask.
        unmasked_length: Number of trailing characters to leave visible.
        mask_char: Character used for the masked portion.

    Returns:
        The masked string, or the original string if its length is less than
        or equal to ``unmasked_length``.
    """
    length = len(data)
    if length <= unmasked_length:
        return data
    else:
        masked_part = mask_char * (length - unmasked_length)
        unmasked_part = data[-unmasked_length:]
        return masked_part + unmasked_part


class PatternType(IntEnum):
    """Classification of Databricks API response structures.

    Used by :meth:`SatDBClient.getNumLists` to determine how to
    normalize a given JSON response into a consistent internal format.
    """

    PATTERN_1 = 1  # dict with 1 list of dicts
    PATTERN_2 = 2  # Dict with multiple lists of dicts
    PATTERN_3 = 3  # dict with 1 or more dicts
    PATTERN_4 = 4  # list with dicts


class SatDBClient:
    """REST API wrapper for Databricks workspace and account-level APIs.

    Handles OAuth-based authentication for AWS, Azure, and GCP cloud providers,
    automatic pagination, response normalization, and remote command execution
    via the Databricks execution-context API.

    Args:
        inp_configs: Raw configuration dictionary (or JSON string) containing
            connection parameters such as ``url``, ``account_id``,
            ``client_id``, ``client_secret``, and cloud-specific fields.
    """

    # set of http error codes to throw an exception if hit. Handles client and auth errors
    http_error_codes = [401, 403]

    def __init__(self, inp_configs):
        self._inp_configs = inp_configs
        configs = pars.parse_input_jsonargs(inp_configs)
        self._configs = configs
        self._workspace_id = configs["workspace_id"]
        self._raw_url = configs["url"].strip()
        self._url = self._raw_url
        self._account_id = configs["account_id"].strip()
        self._cloud_type = self.parse_cloud_type()
        self._verbosity = LoggingUtils.get_log_level(configs["verbosity"])
        LoggingUtils.set_logger_level(self._verbosity)
        self._cluster_id = configs["clusterid"].strip()
        self._token = ""
        # self._raw_token = '' #for gcp this was populated in bootstrap notebook. Not anymore.
        # mastercreds not used anymore
        self._proxies = configs.get("proxies", {})
        # self._use_sp_auth = True #always use sp auth by default
        self._maxpages = configs["maxpages"]  # max pages to fetch in paginated calls
        self._timebetweencalls = configs[
            "timebetweencalls"
        ]  # seconds to wait between paginated calls
        # common for all clouds
        # AWS and GCP pass in secret generated in accounts console
        # Azure pass in secret generated in azure portal
        self._client_id = configs["client_id"].strip()
        self._client_secret = configs["client_secret"].strip()
        # take care of gov cloud domains
        domain = pars.get_domain(self._raw_url)
        if "aws" in self._cloud_type:
            self._ACCTURL = f"https://accounts.cloud.databricks.{domain}"
        if "gcp" in self._cloud_type:
            self._ACCTURL = f"https://accounts.gcp.databricks.{domain}"
        # Azure msmgmt urls need these
        if "azure" in self._cloud_type:
            self._ACCTURL = f"https://accounts.azuredatabricks.{domain}"
            self._MGMTURL = "https://management.azure.com"
            self._subscription_id = configs["subscription_id"].strip()
            self._tenant_id = configs["tenant_id"].strip().strip()

    def _update_token_master(self, endpoint=None):
        """Refresh the OAuth token for account-level API calls.

        Sets ``self._token`` to an ``Authorization: Bearer`` header and points
        ``self._url`` to the appropriate accounts endpoint for the current
        cloud provider.

        Args:
            endpoint: Optional endpoint path. Used on Azure to determine
                whether the token should target Azure Management or Databricks
                Accounts.
        """
        LOGGR.info("in _update_token_master")
        # self._url=self._raw_url
        if self._cloud_type == "gcp":
            self._url = self._ACCTURL
            LOGGR.debug(
                f"GCP self._url {self._url} {self._client_id} {mask_data(self._client_secret, 3)}"
            )
            oauth = self.getGCPTokenwithOAuth(
                True, self._client_id, self._client_secret
            )
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
            # LOGGR.info(f'GCP self._token {oauth}')
        elif self._cloud_type == "azure":
            # azure is only oauth to accounts/msmgmt
            self._url = self._ACCTURL
            oauth = self.getAzureToken(
                True, endpoint, self._client_id, self._client_secret
            )
            if endpoint is None or "?api-version=" in endpoint:
                self._url = self._MGMTURL
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
        elif self._cloud_type == "aws":  # AWS
            self._url = self._ACCTURL  # url for accounts api
            oauth = self.getAWSTokenwithOAuth(
                True, self._client_id, self._client_secret
            )
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
        LOGGR.info("Master Account Token Updated!")

    def _update_token(self, endpoint=None):
        """Refresh the OAuth token for workspace-level API calls.

        Sets ``self._token`` to an ``Authorization: Bearer`` header and resets
        ``self._url`` to the workspace URL.

        Args:
            endpoint: Optional endpoint path. Used on Azure to determine
                the correct token scope.
        """
        # only use the sp auth workflow
        # self._url=self._raw_url #accounts api uses a different url
        LOGGR.info("in _update_token")
        self._url = self._raw_url
        if self._cloud_type == "aws":
            oauth = self.getAWSTokenwithOAuth(
                False, self._client_id, self._client_secret
            )
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
        elif self._cloud_type == "azure":
            oauth = self.getAzureToken(
                False, endpoint, self._client_id, self._client_secret
            )
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
        elif self._cloud_type == "gcp":
            oauth = self.getGCPTokenwithOAuth(
                False, self._client_id, self._client_secret
            )
            self._token = {
                "Authorization": f"Bearer {oauth}",
                "User-Agent": "databricks-sat/0.1.0",
            }
        LOGGR.info(f"Token Updated!")

    def get_temporary_oauth_token(self):
        """Return a short-lived OAuth access token string for external use.

        Returns:
            The bearer token string, or ``None`` if token acquisition failed.
        """
        self._update_token()
        if self._token is None:
            return None
        temptok = self._token.get("Authorization", "").split(" ")
        if len(temptok) > 1:
            return temptok[1]
        else:
            return None

    def test_connection(self, master_acct=False):
        """Verify connectivity by making a lightweight API call.

        Args:
            master_acct: If ``True``, test the account-level API connection;
                otherwise test the workspace-level connection.

        Returns:
            ``True`` if the connection succeeds.

        Raises:
            Exception: If the HTTP response status is not 200.
        """
        if master_acct:  # master acct may use a different credential
            if self._cloud_type == "azure":
                self._update_token_master(endpoint="workspaces?api-version=2018-04-01")
                results = requests.get(
                    f"{self._url}/subscriptions/{self._subscription_id}/providers/Microsoft.Databricks/workspaces?api-version=2018-04-01",
                    headers=self._token,
                    timeout=60,
                    proxies=self._proxies,
                )
            else:
                self._update_token_master()
                results = requests.get(
                    f"{self._url}/api/2.0/accounts/{self._account_id}/workspaces",
                    headers=self._token,
                    timeout=60,
                    proxies=self._proxies,
                )
        else:
            self._update_token()
            results = requests.get(
                f"{self._url}/api/2.0/clusters/spark-versions",
                headers=self._token,
                timeout=60,
                proxies=self._proxies,
            )

        http_status_code = results.status_code
        if http_status_code != 200:
            LOGGR.info(
                "Error. Either the credentials have expired or the \
                    credentials don't have proper permissions. Re-verify secrets"
            )
            LOGGR.info(results.reason)
            LOGGR.info(results.text)
            raise Exception(f"Test connection failed {results.reason}")
        return True

    @staticmethod
    def debugminijson(jsonelem, title=""):
        """Log the first 1250 characters of a JSON element at DEBUG level.

        Args:
            jsonelem: JSON-serializable object to log.
            title: Optional label prepended to the log message.
        """
        debugs = json.dumps(jsonelem, indent=1, sort_keys=True)
        LOGGR.debug(f"{title}-=-=-{debugs[:1250]}-=-=-{type(jsonelem)}")

    @staticmethod
    def getNumLists(resp) -> PatternType:
        """Classify the structure of a Databricks API JSON response.

        Inspects the top-level keys of ``resp`` to determine which
        :class:`PatternType` it matches so that downstream code can
        extract the payload consistently.

        Args:
            resp: Parsed JSON response (``dict`` or ``list``).

        Returns:
            The matching :class:`PatternType`.
        """
        numlists = 0
        numdicts = 0

        if isinstance(resp, list):  # some like in accounts return a list as outer
            LOGGR.debug("\t\t\tPattern4")
            return PatternType.PATTERN_4

        bfoundschemas = False
        for ielem in resp:
            # ignore schema list as in scim.groups or scim.users
            if ielem == "schemas":
                bfoundschemas = True
            if isinstance(resp[ielem], list):
                numlists += 1
            if isinstance(resp[ielem], dict):
                numdicts += 1

        # somethings like uc.get_systemschemas return only schemas this is valid dont touch these.
        if bfoundschemas and numlists > 1:
            numlists -= 1
            resp.pop("schemas")  # remove schemas from solution to make it a PATTERN_1

        LOGGR.debug(f"\t\t\t$numlists={numlists} $numdict={numdicts}")

        if numlists == 1 and numdicts == 0:
            LOGGR.debug("\t\t\tPattern1")
            return PatternType.PATTERN_1
        if numlists > 1 and numdicts == 0:
            LOGGR.debug("\t\t\tPattern2")
            return PatternType.PATTERN_2
        LOGGR.debug("\t\t\tPattern3")
        return PatternType.PATTERN_3

    @staticmethod
    def getRespArray(resp):
        """Extract the element name and data list from a classified response.

        Args:
            resp: Parsed JSON response (``dict`` or ``list``).

        Returns:
            A ``(element_name, data_list)`` tuple.  ``element_name`` is the
            original dict key holding the list, or ``"satelements"`` when the
            response does not follow the standard pattern.
        """

        arrdict = []
        # dont think this should ever happen. As it is handled in get_paginated
        if not resp:
            emptydict = {}
            arrdict.append(emptydict)
            return "satelements", arrdict
        patterntype = SatDBClient.getNumLists(resp)

        # SatDBClient.debugminijson(resp, "getRespArray")
        if (
            patterntype == PatternType.PATTERN_1
        ):  # one list and within list we have a dict
            for ielem in resp:
                if isinstance(resp[ielem], list):
                    LOGGR.debug(
                        f"\t\tgetRespArray-{len(resp[ielem])}"
                    )  # getRespArray-20-type-<class 'dict'>
                    if len(resp[ielem]) > 0:
                        LOGGR.debug(f"\t\tgetRespArray-type-{type(resp[ielem][0])}")
                    return ielem, resp[ielem]

        if patterntype == PatternType.PATTERN_2 or patterntype == PatternType.PATTERN_3:
            arrdict.append(resp)
            return "satelements", arrdict
        if patterntype == PatternType.PATTERN_4:
            return "satelements", resp  # return the list as is

    @staticmethod
    def flatten(nestarr):
        """Flatten a list of paginated response tuples into a single result.

        Args:
            nestarr: List of ``(dict, http_status_code)`` tuples as yielded by
                :meth:`get_paginated`.

        Returns:
            A ``(element_name, flat_list, http_status_code)`` tuple combining
            all pages into one list.
        """
        flatarr = []
        flatelem = ""
        flathttpstatuscode = 200
        # SatDBClient.debugminijson(nestarr, "flattennestarr")
        LOGGR.debug(
            f"\t\t*flatten1-{len(nestarr)}-type-{type(nestarr)}"
        )  # flatten1-10-type-<class 'list'>
        if len(nestarr) > 0:
            LOGGR.debug(
                f"\t\t*flatten2-{len(nestarr[0])}-type-{type(nestarr[0])}"
            )  # flatten2-2-type-<class 'tuple'>
        for tup_elem in nestarr:
            for dictkey in tup_elem[0]:
                if flatelem and flatelem != dictkey:
                    LOGGR.debug(f"\t\t*different keys detected {flatelem}-{dictkey}")
                flatelem = dictkey
                flathttpstatuscode = tup_elem[1]
                LOGGR.debug(
                    f"\t\t*flatten3-{len(tup_elem[0][dictkey])}-type-{type(tup_elem[0][dictkey])}"
                )  # flatten3-20-type-<class 'list'>
                flatarr.append(tup_elem[0][dictkey])  # append lists
        flatarr_1 = [fl0 for xs in flatarr for fl0 in xs]  # flatten list of lists.

        LOGGR.debug(f"\t\t*flatten4-{len(flatarr_1)}-type-{type(flatarr_1)}")
        if len(flatarr_1) > 0:
            LOGGR.debug(
                f"type-{type(flatarr_1[0])}"
            )  # flatten4-200-type-<class 'list'>-type-<class 'dict'>
        return flatelem, flatarr_1, flathttpstatuscode

    def get_paginated(
        self,
        endpoint,
        reqtype="get",
        json_params=None,
        files_json=None,
        is_paginated=False,
    ):
        """Issue one or more HTTP requests, following ``next_page_token`` pagination.

        Yields one ``(dict, http_status_code)`` tuple per page.  Each dict maps
        the element name to its data list (see :meth:`getRespArray`).

        Args:
            endpoint: Fully-qualified URL to call.
            reqtype: HTTP method — ``"get"``, ``"post"``, ``"put"``, or ``"patch"``.
            json_params: Query parameters (GET) or JSON body (POST/PUT/PATCH).
            files_json: Optional multipart file payload (POST only).
            is_paginated: If ``True``, follow ``next_page_token`` across pages.

        Yields:
            ``(response_dict, http_status_code)`` per page.

        Raises:
            Exception: On HTTP 401/403 or an API-level error response.
        """
        NUM_PAGES = 10  # throttle as needed
        resultsArray = []
        elementName = ""
        for i in range(self._maxpages):
            LOGGR.debug(f"{endpoint}---{json_params}")
            if "get" in reqtype:
                raw_results = requests.get(
                    endpoint,
                    headers=self._token,
                    params=json_params,
                    timeout=60,
                    proxies=self._proxies,
                )
                time.sleep(
                    self._timebetweencalls
                )  # throttle otherwise gives a too many requests error
            elif "post" in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")
                if files_json:
                    raw_results = requests.post(
                        endpoint,
                        headers=self._token,
                        data=json_params,
                        files=files_json,
                        timeout=60,
                        proxies=self._proxies,
                    )
                else:
                    raw_results = requests.post(
                        endpoint,
                        headers=self._token,
                        json=json_params,
                        timeout=60,
                        proxies=self._proxies,
                    )
            elif "put" in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")
                raw_results = requests.put(
                    endpoint,
                    headers=self._token,
                    json=json_params,
                    timeout=60,
                    proxies=self._proxies,
                )
            elif "patch" in reqtype:
                if json_params is None:
                    LOGGR.info("Must have a payload in json_args param.")
                raw_results = requests.patch(
                    endpoint,
                    headers=self._token,
                    json=json_params,
                    timeout=60,
                    proxies=self._proxies,
                )

            http_status_code = raw_results.status_code
            if http_status_code in SatDBClient.http_error_codes:
                errtext = ""
                errmesg = ""
                errtext = raw_results.text if raw_results.text else ""
                errmesg = raw_results.reason if raw_results.reason else ""

                LOGGR.debug(
                    f"Error: request1 failed with code {http_status_code}\n{errtext}\n{errmesg}"
                )
                raise Exception(
                    f"Error: request failed with code {http_status_code}--{errtext}--{errmesg}"
                )
            results = raw_results.json()

            # check if resp is error message. Added Aug 3.
            if "error_code" in results and "message" in results:
                errtext = ""
                errmesg = ""
                errtext = raw_results.text if raw_results.text else ""
                errmesg = raw_results.reason if raw_results.reason else ""
                LOGGR.debug(
                    f"Error: request2 failed with code {http_status_code}\n{errtext}\n{errmesg}"
                )
                raise Exception(
                    f"Error: request failed with code {http_status_code}--{errtext}--{errmesg}"
                )

            if not results:
                LOGGR.debug("\t\tEmpty result. Breaking out of loop.")
                break

            # with GCP an empty result with only prev_page_token is returned.
            if len(results) == 1 and "prev_page_token" in results:
                LOGGR.debug(
                    "\t\tEmpty result with prev_page_token. Breaking out of loop."
                )
                break

            # do not keep this on. only for debug testing
            # LOGGR.debug('pag - start -------------')
            # LOGGR.debug(json.dumps(results, indent=4, sort_keys=True)) #for debug
            # SatDBClient.debugminijson(results, "get_paginated1") #for debug
            # LOGGR.debug('pag - end -------------')

            elementName, resultsArray = SatDBClient.getRespArray(results)
            retdict = {elementName: resultsArray}
            yield (retdict, http_status_code)

            # for debug.
            # LOGGR.debug(f'\t\tyielding-{retdict}')

            if http_status_code < 200 or http_status_code > 299:
                break

            if not is_paginated:  # not paginated
                break

            if (
                "next_page_token" not in results or not results["next_page_token"]
            ):  # first condition should not happen. But assume end.
                # LOGGR.debug(f'\t\t{json.dumps(results, indent=4, sort_keys=True)}')
                break

            if json_params is None:
                json_params = {}
            page_token = results["next_page_token"]
            json_params.update({"page_token": page_token})

    @staticmethod
    def ispaginatedCall(endpoint):
        """Check whether an endpoint uses token-based pagination.

        Args:
            endpoint: The fully-qualified API URL.

        Returns:
            ``True`` if the endpoint matches a known paginated API pattern.
        """
        paginatedurls = [
            "/api/2.0/accounts/.+/federationPolicies",
            "/api/2.0/accounts/.+/network-connectivity-configs",
            "/api/2.0/accounts/.+/network-connectivity-configs/.+/private-endpoint-rules",
            "/api/2.0/accounts/.+/servicePrincipals/.+/credentials/secrets",
            "/api/2.0/accounts/.+/oauth2/custom-app-integrations",
            "/api/2.0/accounts/.+/oauth2/published-app-integrations",
            "/api/2.0/apps",
            "/api/2.0/apps/.+/deployments",
            "/api/2.0/clean-rooms",
            "/api/2.0/clean-rooms/.+/runs",
            "/api/2.0/fs/directories/.+",
            "/api/2.0/lakeview/dashboards",
            "/api/2.0/lakeview/dashboards/.+/schedules",
            "/api/2.0/lakeview/dashboards/.+/schedules/.+/subscriptions",
            "/api/2.0/marketplace-exchange/exchanges-for-listing",
            "/api/2.0/marketplace-exchange/filters",
            "/api/2.0/marketplace-exchange/listings-for-exchange",
            "/api/2.0/marketplace-provider/providers"
            "/api/2.0/marketplace-provider/files",
            "/api/2.0/marketplace-provider/listings",
            "/api/2.0/marketplace-provider/personalization-requests",
            "/api/2.0/mlflow/artifacts/list",
            "/api/2.0/mlflow/experiments/list",
            "/api/2.0/mlflow/registered-models/list",
            "/api/2.0/mlflow/registry-webhooks/list",
            "/api/2.0/mlflow/runs/search",
            "/api/2.0/pipelines",
            "/api/2.0/pipelines/.+/events",
            "/api/2.0/pipelines/.+/updates",
            "/api/2.0/policies/clusters/list-compliance",
            "/api/2.0/policies/jobs/list-compliance",
            "/api/2.0/policy-families",
            "/api/2.0/repos",
            "/api/2.0/sql/history/queries",
            "/api/2.0/sql/queries",
            "/api/2.0/vector-search/endpoints",
            "/api/2.0/vector-search/indexes",
            "/api/2.0/vector-search/indexes/.+/query",  # not used
            "/api/2.0/vector-search/indexes/.+/query-next-page",  # not used
            "/api/2.1/accounts/.+/budget-policies",
            "/api/2.1/clusters/events",
            "/api/2.1/clusters/list",
            "/api/2.1/marketplace-consumer/installations",
            "/api/2.1/marketplace-consumer/listings",
            "/api/2.1/marketplace-consumer/listings/.+/content",
            "/api/2.1/marketplace-consumer/listings/.+/fulfillments",
            "/api/2.1/marketplace-consumer/listings/.+/installations",
            "/api/2.1/marketplace-consumer/personalization-requests",
            "/api/2.1/marketplace-consumer/providers",
            "/api/2.1/unity-catalog/bindings/.+/.+",
            "/api/2.1/unity-catalog/catalogs",
            "/api/2.1/unity-catalog/connections",
            "/api/2.1/unity-catalog/credentials"
            "/api/2.1/unity-catalog/external-locations",
            "/api/2.1/unity-catalog/functions",
            "/api/2.1/unity-catalog/metastores/.+/systemschemas",  # not used
            "/api/2.1/unity-catalog/models",
            "/api/2.1/unity-catalog/models/.+/versions",
            "/api/2.1/unity-catalog/providers",
            "/api/2.1/unity-catalog/recipients",
            "/api/2.1/unity-catalog/recipients/.+/share-permissions",
            "/api/2.1/unity-catalog/schemas",
            "/api/2.1/unity-catalog/tables",
            "/api/2.1/unity-catalog/volumes",
            "/api/2.2/jobs/get",
            "/api/2.2/jobs/list",
            "/api/2.2/jobs/runs/get",
            "/api/2.2/jobs/runs/list",
        ]
        for url in paginatedurls:
            if re.search(url, endpoint, flags=re.IGNORECASE) is not None:
                LOGGR.debug("Paginated call...")
                return True
        return False

    """
    http_req => get_paginated and flatten
    get_paginated => getRespArray
    getRespArray => getNumLists
    """

    def http_req(
        self,
        http_type,
        endpoint,
        json_params,
        version="2.0",
        files_json=None,
        master_acct=False,
    ):
        """Execute an HTTP request with automatic pagination and response flattening.

        This is the central dispatcher used by :meth:`get`, :meth:`post`,
        :meth:`put`, and :meth:`patch`.

        Args:
            http_type: HTTP method string (``"get"``, ``"post"``, ``"put"``,
                ``"patch"``).
            endpoint: API path (without the base URL or ``/api/<version>`` prefix).
            json_params: Query parameters or JSON body payload.
            version: Databricks API version string (default ``"2.0"``).
            files_json: Optional multipart file payload for POST requests.
            master_acct: If ``True``, authenticate against the account-level API.

        Returns:
            A dict with the response element name as key, its data as a list,
            and an ``"http_status_code"`` entry.
        """
        # Azure has two different account api strategies. one goes direct to azure management and
        # the other one goes to databricks.
        LOGGR.debug(f"endpoint -> {endpoint}")
        if master_acct:
            self._update_token_master(endpoint)
        else:
            self._update_token(endpoint)

        if (
            self._cloud_type == "azure" and master_acct and "?api-version=" in endpoint
        ):  # Azure accounts API format is different
            endpoint = (
                endpoint[1:] if endpoint.startswith("/") else endpoint
            )  # remove leading /
            full_endpoint = f"{self._url}/{endpoint}"
        else:  # all databricks apis
            full_endpoint = f"{self._url}/api/{version}{endpoint}"

        LOGGR.debug(f"http type endpoint -> {http_type}: {full_endpoint}")
        is_paginated = SatDBClient.ispaginatedCall(full_endpoint)
        respageslst = list(
            self.get_paginated(
                full_endpoint, http_type, json_params, files_json, is_paginated
            )
        )

        if respageslst is None or not respageslst:
            LOGGR.debug("get1-empty response")
            return {
                "satelements": [],
                "http_status_code": 200,
            }  # return empty list if no results
        LOGGR.debug(
            f"get1-{len(respageslst)}-type-{type(respageslst)}-type-{type(respageslst[0])}"
        )  # get1-10-type-<class 'list'>-type-<class 'tuple'>

        if len(respageslst) > 0:
            LOGGR.debug(f"get1-type-{type(respageslst[0])}")
        for i in respageslst:
            LOGGR.debug(f"get2-{len(i)}-type-{type(i)}")  # get2-2-type-<class 'tuple'>
            if len(i) > 0:
                LOGGR.debug(f"get2-{len(i[0])}-{type(i[0])}")
        reselement, resflattenpages, http_status_code = SatDBClient.flatten(respageslst)
        LOGGR.debug(f"get3-{len(resflattenpages)}")  # get3-200
        # --------remove for non debug (start)------------
        # SatDBClient.debugminijson(resflattenpages, "l1resflattenpages")
        # print(f"l2-{len(resflattenpages[0])}-type-{type(resflattenpages[0])}")
        # SatDBClient.debugminijson(resflattenpages[0], "l2resflattenpages")
        # -------remove for non debug (end)------------
        results = {reselement: resflattenpages, "http_status_code": http_status_code}
        return results

    def get(self, endpoint, json_params=None, version="2.0", master_acct=False):
        """Send a GET request to the Databricks API."""
        return self.http_req("get", endpoint, json_params, version, None, master_acct)

    def post(
        self, endpoint, json_params, version="2.0", files_json=None, master_acct=False
    ):
        """Send a POST request to the Databricks API."""
        return self.http_req(
            "post", endpoint, json_params, version, files_json, master_acct
        )

    def put(self, endpoint, json_params, version="2.0", master_acct=False):
        """Send a PUT request to the Databricks API."""
        return self.http_req("put", endpoint, json_params, version, None, master_acct)

    def patch(self, endpoint, json_params, version="2.0", master_acct=False):
        """Send a PATCH request to the Databricks API."""
        return self.http_req("patch", endpoint, json_params, version, None, master_acct)

    def get_execution_context(self):
        """Create a remote Python execution context on the configured cluster.

        Returns:
            The execution context ID string.

        Raises:
            Exception: If the cluster is not running or context creation fails.
        """
        self._update_token()
        LOGGR.debug("Creating remote Spark Session")

        cid = self._cluster_id
        # time.sleep(5)
        ec_payload = {"language": "python", "clusterId": cid}
        ec_var = self.post(
            "/contexts/create", json_params=ec_payload, version="1.2"
        ).get("satelements", [])
        ec_id = None
        ec_id = ec_var[0].get("id", None)
        if ec_id is None:
            LOGGR.info("Get execution context failed...")
            LOGGR.info(ec_var)
            raise Exception("Remote session error. Cluster may not be started.")
        return ec_id

    def submit_command(self, ec_id, cmd):
        """Submit a Python command to a remote execution context and wait for results.

        Args:
            ec_id: Execution context ID returned by :meth:`get_execution_context`.
            cmd: Python source code string to execute.

        Returns:
            The ``results`` dict from the command status response.

        Raises:
            Exception: If the command finishes with an error result.
        """
        self._update_token()
        cid = self._cluster_id
        # This launches spark commands and print the results. We can pull out the text results from the API
        command_payload = {
            "language": "python",
            "contextId": ec_id,
            "clusterId": cid,
            "command": cmd,
        }
        command = self.post(
            "/commands/execute", json_params=command_payload, version="1.2"
        ).get("satelements", [])
        com_id = command[0].get("id", None)
        if com_id is None:
            LOGGR.error(command)
        # print('command_id : ' + com_id)
        result_payload = {"clusterId": cid, "contextId": ec_id, "commandId": com_id}

        resp = self.get(
            "/commands/status", json_params=result_payload, version="1.2"
        ).get("satelements", [])
        resp = resp[0]
        is_running = self.get_key(resp, "status")

        # loop through the status api to check for the 'running' state call and sleep 1 second
        while (is_running == "Running") or (is_running == "Queued"):
            resp = self.get(
                "/commands/status", json_params=result_payload, version="1.2"
            ).get("satelements", [])
            resp = resp[0]
            is_running = self.get_key(resp, "status")
            time.sleep(1)
        _ = self.get_key(resp, "status")
        end_results = self.get_key(resp, "results")
        if end_results.get("resultType", None) == "error":
            LOGGR.error(end_results.get("summary", None))
            raise Exception("Error in Submit Command")
        return end_results

    @staticmethod
    def get_key(http_resp, key_name):
        """Retrieve a required key from an HTTP JSON response.

        Args:
            http_resp: Parsed JSON response dict.
            key_name: Key to look up.

        Returns:
            The value associated with ``key_name``.

        Raises:
            ValueError: If the key is not present in ``http_resp``.
        """
        value = http_resp.get(key_name, None)
        if value is None:
            raise ValueError("Unable to find key " + key_name)
        return value

    def whoami(self):
        """
        get current user userName from SCIM API
        :return: username string
        """
        user_name = self.get("/preview/scim/v2/Me").get("userName")
        return user_name

    def get_url(self):
        """Return the current base URL (may be workspace or account URL)."""
        return self._url

    def get_latest_spark_version(self):
        """Return the latest Scala-based Spark runtime version from the workspace."""
        versions = self.get("/clusters/spark-versions")["versions"]
        v_sorted = sorted(versions, key=lambda i: i["key"], reverse=True)
        for vsparkver in v_sorted:
            img_type = vsparkver["key"].split("-")[1][0:5]
            if img_type == "scala":
                return vsparkver

    def get_cloud_type(self):
        """Return the detected cloud provider (``"aws"``, ``"azure"``, or ``"gcp"``)."""
        return self._cloud_type

    def parse_cloud_type(self):
        """Infer the cloud provider from the workspace URL domain."""
        cloudtype = ""
        if "azuredatabricks.net" in self._raw_url:
            cloudtype = "azure"
        if "cloud.databricks" in self._raw_url:
            cloudtype = "aws"
        if "gcp.databricks" in self._raw_url:
            cloudtype = "gcp"
        return cloudtype

    def getAzureToken(self, baccount, endpoint, client_id, client_secret):
        """Route to the correct MSAL token scope for Azure.

        Determines whether the request targets Azure Management APIs or
        Databricks APIs and delegates to :meth:`getAzureTokenWithMSAL`.

        Args:
            baccount: ``True`` for account-level calls.
            endpoint: API endpoint path (used to detect ``?api-version=``).
            client_id: Azure AD application (client) ID.
            client_secret: Azure AD client secret.

        Returns:
            An OAuth access token string, or ``None`` on failure.
        """
        LOGGR.debug(f"getAzureToken {endpoint} {baccount}")
        databrickstype = True
        # microsoft apis have the api-version string
        if endpoint is not None and "?api-version=" in endpoint:
            databrickstype = False
        if endpoint is None:
            databrickstype = True
        if not databrickstype and baccount:  # master and to microsoft
            oauthtok = self.getAzureTokenWithMSAL("msmgmt")
            LOGGR.debug(f"msmgmt1 {mask_data(oauthtok, 4)}")
            return oauthtok  # account dbtype
        elif databrickstype and baccount:  # master but databricks
            oauthtok = self.getAzureTokenWithMSAL("dbmgmt")
            LOGGR.debug(f"dbmgmt1 {mask_data(oauthtok, 4)}")
            return oauthtok  # account dbtype
        elif databrickstype and not baccount:  # not master has to be databricks
            oauthtok = self.getAzureTokenWithMSAL("dbmgmt")
            LOGGR.debug(f"dbmgmt1 {mask_data(oauthtok, 4)}")
            return oauthtok  # account dbtype
        else:
            LOGGR.debug(
                f"This condition should never happen getAzureToken {endpoint} {baccount}"
            )
            return None, None  # account dbtype

    def getAzureTokenWithMSAL(self, scopeType):
        """Acquire an Azure AD token using the MSAL confidential client flow.

        Tries the MSAL token cache first; falls back to a fresh
        client-credentials grant when no cached token is available.

        Args:
            scopeType: ``"msmgmt"`` for Azure Management scope or
                ``"dbmgmt"`` for the Databricks REST API scope.

        Returns:
            An OAuth access token string.

        Raises:
            Exception: If token acquisition fails.
        """
        try:
            if self._cloud_type != "azure":
                raise Exception("works only for Azure")
            scopes = []
            if "msmgmt" in scopeType.lower():
                scopes = [f"{self._MGMTURL}/.default"]  # ms scope
            else:
                scopes = [
                    "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"
                ]  # databricks scope

            app = msal.ConfidentialClientApplication(
                client_id=self._client_id,
                client_credential=self._client_secret,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",  # might need to change for govcloud
            )

            # The pattern to acquire a token looks like this.
            token = None
            # Firstly, looks up a token from cache
            token = app.acquire_token_silent(scopes=scopes, account=None)

            if not token:
                token = app.acquire_token_for_client(scopes=scopes)

            if token.get("access_token") is None:
                LOGGR.debug("no token")
                raise Exception("No token")
            else:
                return token.get("access_token")

        except Exception as error:
            print(f"Exception {error}")
            print(str(error))

    def getAWSTokenwithOAuth(self, baccount, client_id, client_secret):
        """Acquire an OAuth token for AWS Databricks via the OIDC endpoint.

        Args:
            baccount: ``True`` to authenticate against the accounts API;
                ``False`` for the workspace API.
            client_id: Service principal client ID.
            client_secret: Service principal client secret.

        Returns:
            An OAuth access token string, or ``None`` on failure.
        """
        response = None
        user_pass = (client_id, client_secret)
        oidc_token = {"User-Agent": "databricks-sat/0.1.0"}
        json_params = {"grant_type": "client_credentials", "scope": "all-apis"}

        if baccount:
            full_endpoint = f"{self._ACCTURL}/oidc/accounts/{self._account_id}/v1/token"  # url for accounts api
        else:  # workspace
            full_endpoint = f"{self._raw_url}/oidc/v1/token"

        response = requests.post(
            full_endpoint,
            headers=oidc_token,
            auth=user_pass,
            data=json_params,
            timeout=60,
            proxies=self._proxies,
        )

        if response is not None and response.status_code == 200:
            return response.json()["access_token"]
        # LOGGR.debug(json.dumps(response.json()))
        return None

    def getGCPTokenwithOAuth(self, baccount, client_id, client_secret):
        """Acquire an OAuth token for GCP Databricks via the OIDC endpoint.

        Args:
            baccount: ``True`` to authenticate against the accounts API;
                ``False`` for the workspace API.
            client_id: Service principal client ID.
            client_secret: Service principal client secret.

        Returns:
            An OAuth access token string, or ``None`` on failure.
        """
        response = None
        user_pass = (client_id, client_secret)
        oidc_token = {"User-Agent": "databricks-sat/0.1.0"}
        json_params = {"grant_type": "client_credentials", "scope": "all-apis"}

        if baccount is True:
            full_endpoint = f"{self._ACCTURL}/oidc/accounts/{self._account_id}/v1/token"  # url for accounts api
        else:  # workspace
            full_endpoint = f"{self._raw_url}/oidc/v1/token"

        LOGGR.debug(f"getGCPTokenwithOAuth {full_endpoint} {json_params} {oidc_token}")
        response = requests.post(
            full_endpoint,
            headers=oidc_token,
            auth=user_pass,
            data=json_params,
            timeout=60,
            proxies=self._proxies,
        )

        if response is not None and response.status_code == 200:
            return response.json()["access_token"]
        # LOGGR.debug(json.dumps(response.json()))
        return None


# ----------------------------------------------------
# notes
# ----------------------------------------------------
# pattern 1 - Dict with 1 list of dicts.
# {
#   "apps": [
#     {
#       "client_id": "string",
#       ...
#   ],
#   "next_page_token": "string"
# }

# pattern 2 Dict with multiple lists of dicts
# {
#   "active": true,
#   "applicationId": "97ab27fa-30e2-43e3-92a3-160e80f4c0d5",
#   "displayName": "etl-service",
#   "entitlements": [
#     {
#       "$ref": "string",
#       "display": "string",
#       "primary": true,
#       "type": "string",
#       "value": "string"
#     }
#   ],
#   "externalId": "string",
#   "groups": [
#     {
#       "$ref": "string",
#       "display": "string",
#       "primary": true,
#       "type": "string",
#       "value": "string"
#     }
#   ],
#   "id": "string",
#   "roles": [
#     {
#       "$ref": "string",
#       "display": "string",
#       "primary": true,
#       "type": "string",
#       "value": "string"
#     }
#   ],
#   "schemas": [
#     "urn:ietf:params:scim:schemas:core:2.0:ServicePrincipal"
#   ]
# }

# pattern 3 dict with one dict
# {
#   "log_delivery_configuration": {
#     "account_id": "449e7a5c-69d3-4b8a-aaaf-5c9b713ebc65",
#     ...
#     "delivery_start_time": "string",
#     "log_delivery_status": {
#       "last_attempt_time": "string",
#       "last_successful_attempt_time": "string",
#       "message": "string",
#       "status": "CREATED"
#     },
#     "log_type": "BILLABLE_USAGE",
#     ....
#     "workspace_ids_filter": [
#       0
#     ]
#   }
# }

# pattern 3.1 dict with multiple dicts.
# {
#   "account_id": "449e7a5c-69d3-4b8a-aaaf-5c9b713ebc65",
#   "aws_region": "string",
#   "creation_time": 0,
#   "credentials_id": "c7814269-df58-4ca3-85e9-f6672ef43d77",
#   "custom_tags": {
#     "property1": "string",
#     "property2": "string"
#   },
#   "custom_attribs": {
#     "property1": "string",
#     "property2": "string"
#   },
#   "deployment_name": "string",
#   ....
#   "workspace_status_message": "Workspace resources are being set up."
# }

# pattern 4 List with 1 or more dicts
# [
#   {
#     "account_id": "449e7a5c-69d3-4b8a-aaaf-5c9b713ebc65",
#     "aws_region": "string",
#     "creation_time": 0,
#     "credentials_id": "c7814269-df58-4ca3-85e9-f6672ef43d77",
#     "custom_tags": {
#       "property1": "string",
#       "property2": "string"
#     },
#     "deployment_name": "string",
#      ...
#   }
# ]
