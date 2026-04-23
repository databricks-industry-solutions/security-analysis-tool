'''Egress connectivity test module'''
import requests
from core.dbclient import SatDBClient
from core.logging_utils import LoggingUtils

LOGGR = LoggingUtils.get_logger()

EGRESS_TEST_DESTINATIONS = [
    {"name": "google", "url": "https://www.google.com"},
    {"name": "ifconfig", "url": "https://ifconfig.me"},
    {"name": "cloudflare", "url": "https://www.cloudflare.com"},
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
                # GET with stream=True: opens the connection, reads response headers,
                # does not download the body. Any HTTP response proves the destination
                # was reached — TCP connect, TLS handshake, and HTTP exchange all
                # completed. True egress blocking surfaces as Timeout / ConnectionError
                # in the except branches below, not as an application-level status code.
                # HEAD is avoided because some sites (e.g. ifconfig.me) return 405 to
                # HEAD while happily serving GET, which would misread as "blocked".
                response = requests.get(
                    dest["url"],
                    timeout=10,
                    proxies=self._proxies,
                    allow_redirects=True,
                    stream=True,
                )
                result["status_code"] = response.status_code
                result["reachable"] = True
                response.close()
            except requests.exceptions.Timeout:
                result["error"] = "TIMEOUT"
            except requests.exceptions.ConnectionError as e:
                result["error"] = f"CONNECTION_ERROR: {str(e)[:200]}"
            except Exception as e:
                result["error"] = f"ERROR: {str(e)[:200]}"
            results.append(result)
        return results
