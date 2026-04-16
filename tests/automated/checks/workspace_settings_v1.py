"""Validators for workspace-conf (legacy v1) settings checks.

All checks use: GET /api/2.0/preview/workspace-conf?keys={name}
Pass conditions are derived directly from notebooks/Includes/workspace_settings.py.
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


class WorkspaceSettingV1Validator(BaseValidator):
    """Base class for workspace-conf setting checks."""

    SETTING_NAME: str = ""
    # How to interpret the API value:
    #   "none_or_true_is_pass"  -> None or 'true' = pass (score=0)
    #   "none_or_true_is_fail"  -> None or 'true' = fail (score=1)
    #   "true_is_pass"          -> 'true' = pass, anything else = fail
    #   "false_is_pass"         -> 'false' = pass, anything else = fail
    #   "nonzero_is_pass"       -> int(value) > 0 = pass
    PASS_CONDITION: str = "true_is_pass"

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        resp = self.rest.get(
            "/preview/workspace-conf",
            token=token,
            params={"keys": self.SETTING_NAME},
        )
        value = resp.get(self.SETTING_NAME)
        details = {"setting": self.SETTING_NAME, "value": value}

        if self.PASS_CONDITION == "none_or_true_is_pass":
            score = 0 if (value is None or value == "true") else 1
        elif self.PASS_CONDITION == "none_or_true_is_fail":
            score = 1 if (value is None or value == "true") else 0
        elif self.PASS_CONDITION == "true_is_pass":
            score = 0 if value == "true" else 1
        elif self.PASS_CONDITION == "false_is_pass":
            score = 0 if value == "false" else 1
        elif self.PASS_CONDITION == "nonzero_is_pass":
            score = (
                0
                if (value is not None and value != "null" and int(value) > 0)
                else 1
            )
        else:
            score = 0 if value == "true" else 1

        return score, details


# --- Registered checks ---
# Each maps to a check in workspace_settings.py with identical pass/fail logic.


@register("29")
class Check29_EnableJobViewAcls(WorkspaceSettingV1Validator):
    CHECK_ID = "INFO-8"
    CHECK_NAME = "Job view ACLs"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableJobViewAcls"
    PASS_CONDITION = "none_or_true_is_pass"


@register("30")
class Check30_EnforceClusterViewAcls(WorkspaceSettingV1Validator):
    CHECK_ID = "INFO-9"
    CHECK_NAME = "Cluster view ACLs"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enforceClusterViewAcls"
    PASS_CONDITION = "none_or_true_is_pass"


@register("31")
class Check31_EnforceWorkspaceViewAcls(WorkspaceSettingV1Validator):
    CHECK_ID = "INFO-10"
    CHECK_NAME = "Workspace view ACLs"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enforceWorkspaceViewAcls"
    PASS_CONDITION = "none_or_true_is_pass"


@register("32")
class Check32_EnableProjectTypeInWorkspace(WorkspaceSettingV1Validator):
    CHECK_ID = "INFO-11"
    CHECK_NAME = "Git repos support"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableProjectTypeInWorkspace"
    PASS_CONDITION = "none_or_true_is_pass"


@register("5")
class Check5_EnableResultsDownloading(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-5"
    CHECK_NAME = "Downloading results is disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableResultsDownloading"
    PASS_CONDITION = "none_or_true_is_fail"  # true/None = downloading enabled = FAIL


@register("38")
class Check38_MaxTokenLifetimeDays(WorkspaceSettingV1Validator):
    CHECK_ID = "IA-5"
    CHECK_NAME = "Maximum lifetime of new tokens"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "maxTokenLifetimeDays"
    PASS_CONDITION = "nonzero_is_pass"


@register("43")
class Check43_EnableEnforceImdsV2(WorkspaceSettingV1Validator):
    CHECK_ID = "GOV-14"
    CHECK_NAME = "Enforce AWS IMDSv2"
    CLOUDS = ["aws"]
    SETTING_NAME = "enableEnforceImdsV2"
    PASS_CONDITION = "true_is_pass"


@register("44")
class Check44_EnableExportNotebook(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-6"
    CHECK_NAME = "Notebook export disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableExportNotebook"
    PASS_CONDITION = "none_or_true_is_fail"  # true/None = export enabled = FAIL


@register("45")
class Check45_EnableNotebookTableClipboard(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-7"
    CHECK_NAME = "Notebook table clipboard disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableNotebookTableClipboard"
    PASS_CONDITION = "none_or_true_is_fail"  # true/None = clipboard enabled = FAIL


@register("49")
class Check49_StoreNotebookResults(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-8"
    CHECK_NAME = "Notebook results in customer account"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "storeInteractiveNotebookResultsInCustomerAccount"
    PASS_CONDITION = "true_is_pass"


@register("50")
class Check50_EnableVerboseAuditLogs(WorkspaceSettingV1Validator):
    CHECK_ID = "GOV-15"
    CHECK_NAME = "Verbose audit logs"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableVerboseAuditLogs"
    PASS_CONDITION = "true_is_pass"


@register("51")
class Check51_EnableFileStoreEndpoint(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-9"
    CHECK_NAME = "FileStore endpoint disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableFileStoreEndpoint"
    PASS_CONDITION = "false_is_pass"


@register("113")
class Check113_EnableProjectsAllowList(WorkspaceSettingV1Validator):
    CHECK_ID = "INFO-42"
    CHECK_NAME = "Git repository allowlist configured"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableProjectsAllowList"
    PASS_CONDITION = "true_is_pass"


@register("116")
class Check116_EnableDbfsFileBrowser(WorkspaceSettingV1Validator):
    CHECK_ID = "DP-13"
    CHECK_NAME = "DBFS file browser disabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableDbfsFileBrowser"
    PASS_CONDITION = "false_is_pass"


@register("121")
class Check121_EnableIpAccessLists(WorkspaceSettingV1Validator):
    CHECK_ID = "NS-11"
    CHECK_NAME = "IP access list enforcement enabled"
    CLOUDS = ["aws", "azure", "gcp"]
    SETTING_NAME = "enableIpAccessLists"
    PASS_CONDITION = "true_is_pass"
