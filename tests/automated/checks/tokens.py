"""Validators for token/PAT-related security checks.

Reference: notebooks/Includes/workspace_analysis.py (checks 7, 21, 41, 118)
"""

import time

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register
from tests.automated.clients.rest_client import FeatureDisabledError


def _get_tokens(validator: BaseValidator) -> list[dict]:
    """Fetch all PAT tokens for the workspace.

    Raises FeatureDisabledError if tokens are disabled on the workspace.
    """
    token = validator.token_provider.get_workspace_token()
    resp = validator.rest.get("/token/list", token=token, version="2.0")
    return resp.get("token_infos", [])


@register("1")
class Check1_SecretsManagement(BaseValidator):
    """DP-1: Check if there are any secrets configured in the workspace."""

    CHECK_ID = "DP-1"
    CHECK_NAME = "Secrets management"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        resp = self.rest.get("/secrets/scopes/list", token=token, version="2.0")
        scopes = resp.get("scopes", [])
        # evaluation_value = 1 from CSV; pass if count > evaluation_value
        total_secrets = len(scopes)
        score = 0 if total_secrets > 1 else 1
        return score, {"scope_count": total_secrets}


@register("21")
class Check21_PATNoLifetimeLimit(BaseValidator):
    """IA-4: PAT tokens with no lifetime (expiration) limit or > 90 days."""

    CHECK_ID = "IA-4"
    CHECK_NAME = "PAT tokens with no lifetime limit"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        try:
            tokens = _get_tokens(self)
        except FeatureDisabledError:
            return 0, {"note": "Tokens disabled on workspace — no violations possible"}
        now_ms = int(time.time() * 1000)
        threshold_days = 90  # default evaluation_value from CSV
        violations = []
        for t in tokens:
            expiry = t.get("expiry_time", 0)
            if expiry == -1:
                violations.append(
                    {"token_id": t.get("token_id"), "reason": "never_expires"}
                )
            elif expiry > 0:
                days_until = (expiry - now_ms) / (1000 * 86400)
                if days_until > threshold_days:
                    violations.append(
                        {
                            "token_id": t.get("token_id"),
                            "days_until_expiry": round(days_until, 1),
                        }
                    )
        score = 1 if violations else 0
        return score, {"tokens_without_limit": violations}


@register("7")
class Check7_PATAboutToExpire(BaseValidator):
    """GOV-2: PAT tokens about to expire (within evaluation_value days)."""

    CHECK_ID = "GOV-2"
    CHECK_NAME = "PAT tokens about to expire"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        try:
            tokens = _get_tokens(self)
        except FeatureDisabledError:
            return 0, {"note": "Tokens disabled on workspace — no violations possible"}
        now_ms = int(time.time() * 1000)
        threshold_days = 1  # evaluation_value from CSV
        expiring = []
        for t in tokens:
            expiry = t.get("expiry_time", 0)
            if expiry > 0 and expiry != -1:
                days_until = (expiry - now_ms) / (1000 * 86400)
                if days_until <= threshold_days:
                    expiring.append(
                        {
                            "token_id": t.get("token_id"),
                            "days_until_expiry": round(days_until, 1),
                        }
                    )
        score = 1 if expiring else 0
        return score, {"expiring_tokens": expiring}


@register("41")
class Check41_TokenExceedsMaxLifetime(BaseValidator):
    """IA-6: Active tokens whose lifetime exceeds the workspace max."""

    CHECK_ID = "IA-6"
    CHECK_NAME = "Tokens exceeding max lifetime"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        # First, check if maxTokenLifetimeDays is set
        ws_conf = self.rest.get(
            "/preview/workspace-conf",
            token=token,
            params={"keys": "maxTokenLifetimeDays"},
        )
        max_days_str = ws_conf.get("maxTokenLifetimeDays")
        if (
            max_days_str is None
            or max_days_str == "null"
            or max_days_str == "false"
            or int(max_days_str) <= 0
        ):
            # No max lifetime set — cannot have violations
            return 0, {"max_lifetime_days": "not_set"}

        max_days = int(max_days_str)
        now_ms = int(time.time() * 1000)
        try:
            tokens = _get_tokens(self)
        except FeatureDisabledError:
            return 0, {"note": "Tokens disabled on workspace — no violations possible"}
        violations = []
        for t in tokens:
            expiry = t.get("expiry_time", 0)
            if expiry == -1:
                violations.append(
                    {"token_id": t.get("token_id"), "reason": "never_expires"}
                )
            elif expiry > 0:
                days_until = (expiry - now_ms) / (1000 * 86400)
                if days_until > max_days:
                    violations.append(
                        {
                            "token_id": t.get("token_id"),
                            "days_until_expiry": round(days_until, 1),
                        }
                    )
        score = 1 if violations else 0
        return score, {"max_lifetime_days": max_days, "violations": violations}


@register("118")
class Check118_PATRestrictedToAdmins(BaseValidator):
    """IA-8: PAT token creation restricted to admins only."""

    CHECK_ID = "IA-8"
    CHECK_NAME = "PAT token creation restricted to admins"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/permissions/authorization/tokens", token=token, version="2.0"
            )
        except Exception:
            # If API returns 404 or error, token permissions may not be configured
            return 0, {"note": "Token permissions API not available"}

        acls = resp.get("access_control_list", [])
        # Check if the 'users' group appears — means any user can create PATs
        for acl in acls:
            group = acl.get("group_name", "")
            if group == "users":
                return 1, {"users_group_has_token_access": True}
        return 0, {"users_group_has_token_access": False}
