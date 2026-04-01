"""Validators for informational security checks.

These checks are primarily observational — some always return score=0.
Reference: notebooks/Includes/workspace_analysis.py (checks 89, 90, 101)
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


@register("89")
class Check89_SecureModelServingEndpoints(BaseValidator):
    """NS-7: Model serving endpoints should be protected by IP access lists or private link."""

    CHECK_ID = "NS-7"
    CHECK_NAME = "Secure model serving endpoints"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        # Check if workspace has IP access list or private link protection
        has_ip_access_list = False
        has_private_link = False

        try:
            ip_resp = self.rest.get(
                "/ip-access-lists", token=token, version="2.0"
            )
            ip_lists = ip_resp.get("ip_access_lists", [])
            has_ip_access_list = any(l.get("enabled") for l in ip_lists)
        except Exception:
            pass

        # If workspace has IP access list or private link, endpoints are protected
        if has_ip_access_list or has_private_link:
            return 0, {"protected": True}

        # Check if there are model serving endpoints (unprotected)
        try:
            endpoints = self.rest.get_all_pages(
                "/serving-endpoints", token, list_key="endpoints", version="2.0"
            )
            if endpoints:
                return 1, {
                    "endpoint_count": len(endpoints),
                    "endpoints": [
                        {"name": e.get("name"), "type": e.get("endpoint_type")}
                        for e in endpoints[:10]
                    ],
                }
        except Exception:
            pass

        return 0, {"note": "No model serving endpoints or protected"}


@register("90")
class Check90_ExternalModelEndpoints(BaseValidator):
    """INFO-29: External model serving endpoints (LLM providers)."""

    CHECK_ID = "INFO-29"
    CHECK_NAME = "External model serving endpoints"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            endpoints = self.rest.get_all_pages(
                "/serving-endpoints", token, list_key="endpoints", version="2.0"
            )
            external = [
                e for e in endpoints if e.get("endpoint_type") == "EXTERNAL_MODEL"
            ]
            if external:
                return 0, {"external_model_count": len(external)}
            return 1, {"external_model_count": 0}
        except Exception:
            return 1, {"note": "Serving endpoints API not available"}


@register("101")
class Check101_VectorSearchEndpoints(BaseValidator):
    """DP-14: Vector search endpoints exist (secure embeddings storage)."""

    CHECK_ID = "DP-14"
    CHECK_NAME = "Vector search endpoints"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/vector-search/endpoints", token=token, version="2.0"
            )
            endpoints = resp.get("endpoints", [])
            if endpoints:
                return 0, {
                    "endpoint_count": len(endpoints),
                    "endpoints": [e.get("name") for e in endpoints[:10]],
                }
            return 1, {"endpoint_count": 0}
        except Exception:
            return 1, {"note": "Vector search API not available"}
