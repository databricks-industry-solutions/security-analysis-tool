'''Egress connectivity test module'''
import requests
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils

LOGGR = LoggingUtils.get_logger()

EGRESS_TEST_DESTINATIONS = [
    {"name": "google", "url": "https://www.google.com"},
    {"name": "ifconfig", "url": "https://ifconfig.me"},
]

class EgressTestClient(SatDBClient):
    '''Tests egress connectivity from compute to external destinations'''

    def get_egress_test_results(self):
        results = []
        for dest in EGRESS_TEST_DESTINATIONS:
            result = {
                "destination_name": dest["name"],
                "destination_url": dest["url"],
                "reachable": False,
                "status_code": None,
                "error": None,
            }
            try:
                response = requests.head(
                    dest["url"],
                    timeout=10,
                    proxies=self._proxies,
                    allow_redirects=True,
                )
                result["status_code"] = response.status_code
                result["reachable"] = response.status_code < 400
            except requests.exceptions.Timeout:
                result["error"] = "TIMEOUT"
            except requests.exceptions.ConnectionError as e:
                result["error"] = f"CONNECTION_ERROR: {str(e)[:200]}"
            except Exception as e:
                result["error"] = f"ERROR: {str(e)[:200]}"
            results.append(result)
        return results
