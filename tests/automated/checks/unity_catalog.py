"""Validators for Unity Catalog security checks.

Reference: notebooks/Includes/workspace_analysis.py (checks 53-59, 62, 78, 104, 105)
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


@register("53")
class Check53_UCMetastoreAssignment(BaseValidator):
    """GOV-16: Workspace has a Unity Catalog metastore assigned."""

    CHECK_ID = "GOV-16"
    CHECK_NAME = "UC metastore assignment"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/unity-catalog/metastore_summary", token=token, version="2.1"
            )
            metastore_id = resp.get("metastore_id")
            if metastore_id:
                return 0, {"metastore_id": metastore_id}
            return 1, {"error": "No metastore_id in response"}
        except Exception:
            return 1, {"error": "No metastore assigned"}


@register("54")
class Check54_DeltaSharingTokenLifetime(BaseValidator):
    """GOV-17: Delta Sharing recipient token lifetime > 90 days."""

    CHECK_ID = "GOV-17"
    CHECK_NAME = "Delta Sharing token lifetime"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/unity-catalog/metastore_summary", token=token, version="2.1"
            )
        except Exception:
            return 0, {"note": "No metastore"}

        sharing_scope = resp.get("delta_sharing_scope")
        token_lifetime = resp.get(
            "delta_sharing_recipient_token_lifetime_in_seconds", 0
        )
        threshold_seconds = 90 * 86400  # 90 days in seconds

        if sharing_scope == "INTERNAL_AND_EXTERNAL" and token_lifetime > threshold_seconds:
            return 1, {
                "delta_sharing_scope": sharing_scope,
                "token_lifetime_seconds": token_lifetime,
            }
        return 0, {
            "delta_sharing_scope": sharing_scope,
            "token_lifetime_seconds": token_lifetime,
        }


@register("55")
class Check55_DeltaSharingIPAccessList(BaseValidator):
    """GOV-18: Delta Sharing recipients without IP access lists."""

    CHECK_ID = "GOV-18"
    CHECK_NAME = "Delta Sharing IP access lists"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            recipients = self.rest.get_all_pages(
                "/unity-catalog/recipients",
                token=token,
                list_key="recipients",
                version="2.1",
            )
        except Exception:
            return 0, {"note": "No recipients or API not available"}

        violations = [
            {"name": r.get("name"), "owner": r.get("owner")}
            for r in recipients
            if r.get("authentication_type") == "TOKEN"
            and r.get("ip_access_list") is None
        ]
        score = 1 if violations else 0
        return score, {"recipients_without_ip_list": violations}


@register("56")
class Check56_DeltaSharingTokenExpiration(BaseValidator):
    """GOV-19: Delta Sharing tokens without expiration."""

    CHECK_ID = "GOV-19"
    CHECK_NAME = "Delta Sharing token expiration"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            recipients = self.rest.get_all_pages(
                "/unity-catalog/recipients",
                token=token,
                list_key="recipients",
                version="2.1",
            )
        except Exception:
            return 0, {"note": "No recipients or API not available"}

        violations = []
        for r in recipients:
            if r.get("authentication_type") != "TOKEN":
                continue
            for t in r.get("tokens", []):
                if t.get("expiration_time") is None:
                    violations.append(
                        {"recipient": r.get("name"), "token_id": t.get("id")}
                    )
        score = 1 if violations else 0
        return score, {"tokens_without_expiration": violations}


@register("57")
class Check57_UCMetastoreExists(BaseValidator):
    """GOV-20: Existence of Unity Catalog metastores."""

    CHECK_ID = "GOV-20"
    CHECK_NAME = "UC metastore exists"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/unity-catalog/metastores", token=token, version="2.1"
            )
            metastores = resp.get("metastores", [])
            if metastores:
                return 0, {
                    "metastore_count": len(metastores),
                    "names": [m.get("name") for m in metastores[:5]],
                }
            return 1, {"error": "No metastores found"}
        except Exception:
            return 1, {"error": "Metastore API not available"}


@register("58")
class Check58_MetastoreAdminDelegation(BaseValidator):
    """GOV-21: Metastore admin should be delegated (not creator or 'System user')."""

    CHECK_ID = "GOV-21"
    CHECK_NAME = "Metastore admin delegation"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/unity-catalog/metastore_summary", token=token, version="2.1"
            )
        except Exception:
            return 0, {"note": "No metastore"}

        owner = resp.get("owner", "")
        created_by = resp.get("created_by", "")
        # Fail if owner == creator, owner is 'System user', or owner is a user email
        if owner == created_by or owner == "System user" or "@" in owner:
            return 1, {"owner": owner, "created_by": created_by}
        return 0, {"owner": owner, "created_by": created_by}


@register("59")
class Check59_MetastoreStorageCredentials(BaseValidator):
    """GOV-22: Direct use of UC metastore storage credentials."""

    CHECK_ID = "GOV-22"
    CHECK_NAME = "Metastore storage credentials"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            creds = self.rest.get_all_pages(
                "/unity-catalog/storage-credentials",
                token=token,
                list_key="storage_credentials",
                version="2.1",
            )
        except Exception:
            return 0, {"note": "No storage credentials or API not available"}

        # Any storage credentials existing = informational fail
        if creds:
            return 1, {
                "credential_count": len(creds),
                "names": [c.get("name") for c in creds[:5]],
            }
        return 0, {"credential_count": 0}


@register("62")
class Check62_DeltaSharingPermissions(BaseValidator):
    """INFO-18: Users with Delta Sharing CREATE_RECIPIENT/CREATE_SHARE permissions."""

    CHECK_ID = "INFO-18"
    CHECK_NAME = "Delta Sharing permissions"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        # This is an informational check — always score=0
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/unity-catalog/effective-permissions/metastore",
                token=token,
                version="2.1",
            )
            # Just report what we find — this is informational
            return 0, {"permissions": resp}
        except Exception:
            return 0, {"note": "Metastore permissions API not available"}


@register("78")
class Check78_ModelsInUC(BaseValidator):
    """GOV-28: ML models registered in Unity Catalog."""

    CHECK_ID = "GOV-28"
    CHECK_NAME = "Models in Unity Catalog"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            models = self.rest.get_all_pages(
                "/unity-catalog/models",
                token=token,
                list_key="registered_models",
                version="2.1",
            )
        except Exception:
            models = []

        if models:
            return 0, {"model_count": len(models)}
        return 1, {"model_count": 0}


@register("104")
class Check104_ThirdPartyLibraryControl(BaseValidator):
    """INFO-38: Artifact allowlists configured for third-party libraries."""

    CHECK_ID = "INFO-38"
    CHECK_NAME = "Third-party library control"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        has_allowlist = False
        for artifact_type in ["LIBRARY_JAR", "LIBRARY_MAVEN"]:
            try:
                resp = self.rest.get(
                    f"/unity-catalog/artifact-allowlists/{artifact_type}",
                    token=token,
                    version="2.1",
                )
                artifacts = resp.get("artifact_matchers", [])
                if artifacts:
                    has_allowlist = True
                    break
            except Exception:
                continue

        score = 0 if has_allowlist else 1
        return score, {"has_allowlist": has_allowlist}


@register("105")
class Check105_SystemSchemas(BaseValidator):
    """GOV-34: Monitor audit logs with system tables (access schema enabled)."""

    CHECK_ID = "GOV-34"
    CHECK_NAME = "System tables access schema"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            # Get metastore ID first
            ms = self.rest.get(
                "/unity-catalog/metastore_summary", token=token, version="2.1"
            )
            metastore_id = ms.get("metastore_id")
            if not metastore_id:
                return 1, {"error": "No metastore assigned"}

            resp = self.rest.get(
                f"/unity-catalog/metastores/{metastore_id}/systemschemas",
                token=token,
                version="2.1",
            )
            schemas = resp.get("schemas", [])
            for s in schemas:
                if s.get("schema") == "access" and s.get("state") in (
                    "ENABLE_COMPLETED",
                    "MANAGED",
                ):
                    return 0, {"access_schema_state": s.get("state")}
            return 1, {"schemas": schemas}
        except Exception as e:
            return 1, {"error": str(e)}
