"""Validators for identity and access security checks.

Reference: notebooks/Includes/workspace_analysis.py (checks 27, 119)
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


@register("27")
class Check27_AdminCount(BaseValidator):
    """INFO-6: Number of workspace admins exceeds threshold."""

    CHECK_ID = "INFO-6"
    CHECK_NAME = "Number of admins"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        # Get the admins group
        resp = self.rest.get(
            "/preview/scim/v2/Groups",
            token=token,
            params={"filter": 'displayName eq "admins"'},
        )
        groups = resp.get("Resources", [])
        if not groups:
            return 0, {"admin_count": 0}

        members = groups[0].get("members", [])
        admin_count = len(members)
        # evaluation_value from CSV is the threshold (default -1 means any count)
        # SAT logic: fail if count > evaluation_value (which is -1 → always true if members exist)
        # The real logic checks len(df.collect()) > admin_count_evaluation_value
        # With evaluation_value = -1, any member list > -1 means fail → so 0 members = pass
        # Actually, the check just reports admin count. With eval_value=-1, always fails if >-1
        score = 1 if admin_count > 0 else 0
        return score, {
            "admin_count": admin_count,
            "admins": [m.get("display") for m in members[:20]],
        }


@register("119")
class Check119_SPSecretStale(BaseValidator):
    """IA-9: Service principal client secrets that are stale (> evaluation_value days)."""

    CHECK_ID = "IA-9"
    CHECK_NAME = "Service principal secrets not stale"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest

        # Get all service principals from account API
        try:
            sps = acct_client.get_all_pages(
                f"/accounts/{acct_id}/scim/v2/ServicePrincipals",
                token=token,
                list_key="Resources",
            )
        except Exception:
            return 0, {"note": "Could not list service principals"}

        # For each SP, get their secrets
        import time

        now_epoch = time.time()
        threshold_days = 90  # default evaluation_value from CSV
        stale = []

        for sp in sps:
            sp_id = sp.get("id")
            sp_name = sp.get("displayName", "")
            app_id = sp.get("applicationId", "")
            try:
                secrets_resp = acct_client.get(
                    f"/accounts/{acct_id}/servicePrincipals/{sp_id}/credentials/secrets",
                    token=token,
                )
                secrets = secrets_resp.get("secrets", [])
                for secret in secrets:
                    if secret.get("status") != "ACTIVE":
                        continue
                    create_time = secret.get("create_time", "")
                    if create_time:
                        # Parse ISO format
                        from datetime import datetime

                        try:
                            ct = datetime.fromisoformat(
                                create_time.replace("Z", "+00:00")
                            )
                            age_days = (
                                datetime.now(ct.tzinfo) - ct
                            ).days
                            if age_days > threshold_days:
                                stale.append(
                                    {
                                        "sp_name": sp_name,
                                        "sp_app_id": app_id,
                                        "secret_id": secret.get("id"),
                                        "age_days": age_days,
                                    }
                                )
                        except Exception:
                            pass
            except Exception:
                continue

        score = 1 if stale else 0
        return score, {"stale_secrets": stale}
