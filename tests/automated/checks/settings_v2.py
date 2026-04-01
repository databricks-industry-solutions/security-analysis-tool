"""Validators for Settings v2 API checks.

Each setting uses its OWN top-level key in the response (documented in CLAUDE.md).
Exception: sql_results_download uniquely uses 'boolean_val'.
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


class SettingsV2Validator(BaseValidator):
    """Base class for Settings v2 API checks."""

    SETTING_TYPE: str = ""

    def _get_setting(self) -> dict:
        token = self.token_provider.get_workspace_token()
        return self.rest.get(
            f"/settings/types/{self.SETTING_TYPE}/names/default",
            token=token,
        )


@register("106")
class Check106_RestrictWorkspaceAdmins(SettingsV2Validator):
    CHECK_ID = "GOV-35"
    CHECK_NAME = "Restrict workspace admins"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_TYPE = "restrict_workspace_admins"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        status = resp.get("restrict_workspace_admins", {}).get("status")
        # ALLOW_ALL = fail (admins unrestricted), anything else = pass
        score = 1 if status == "ALLOW_ALL" else 0
        return score, {"status": status}


@register("107")
class Check107_AutomaticClusterUpdate(SettingsV2Validator):
    CHECK_ID = "GOV-36"
    CHECK_NAME = "Automatic cluster update"
    CLOUDS = ["aws", "azure"]
    SETTING_TYPE = "automatic_cluster_update"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        enabled = resp.get("automatic_cluster_update_workspace", {}).get("enabled")
        score = 0 if enabled is True else 1
        return score, {"enabled": enabled}


@register("108")
class Check108_ComplianceSecurityProfileWS(SettingsV2Validator):
    CHECK_ID = "INFO-39"
    CHECK_NAME = "Compliance security profile (workspace)"
    CLOUDS = ["aws", "azure"]
    SETTING_TYPE = "shield_csp_enablement_ws_db"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        is_enabled = resp.get("compliance_security_profile_workspace", {}).get(
            "is_enabled"
        )
        score = 0 if is_enabled is True else 1
        return score, {"is_enabled": is_enabled}


@register("109")
class Check109_EnhancedSecurityMonitoringWS(SettingsV2Validator):
    CHECK_ID = "INFO-40"
    CHECK_NAME = "Enhanced security monitoring (workspace)"
    CLOUDS = ["aws", "azure"]
    SETTING_TYPE = "shield_esm_enablement_ws_db"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        is_enabled = resp.get("enhanced_security_monitoring_workspace", {}).get(
            "is_enabled"
        )
        score = 0 if is_enabled is True else 1
        return score, {"is_enabled": is_enabled}


@register("114")
class Check114_DisableLegacyDbfs(SettingsV2Validator):
    CHECK_ID = "DP-10"
    CHECK_NAME = "Disable legacy DBFS"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_TYPE = "disable_legacy_dbfs"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        value = resp.get("disable_legacy_dbfs", {}).get("value")
        score = 0 if value is True else 1
        return score, {"value": value}


@register("115")
class Check115_SqlResultsDownload(SettingsV2Validator):
    CHECK_ID = "DP-11"
    CHECK_NAME = "SQL results download disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_TYPE = "sql_results_download"

    def evaluate_from_api(self) -> tuple[int, dict]:
        resp = self._get_setting()
        # EXCEPTION: sql_results_download uses 'boolean_val' as its top-level key,
        # not its own name. boolean_val.value = False means downloads DISABLED = pass.
        value = resp.get("boolean_val", {}).get("value")
        score = 0 if value is False else 1
        return score, {"boolean_val_value": value}
