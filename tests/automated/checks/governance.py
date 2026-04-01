"""Validators for governance security checks.

Reference: notebooks/Includes/workspace_analysis.py
Covers: DBFS checks, init scripts, libraries, log delivery, jobs, cluster policies
"""

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


@register("15")
class Check15_ManagedTablesInDBFS(BaseValidator):
    """GOV-10: Managed tables in DBFS root (/user/hive/warehouse)."""

    CHECK_ID = "GOV-10"
    CHECK_NAME = "Managed tables in DBFS root"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/dbfs/list",
                token=token,
                params={"path": "/user/hive/warehouse"},
                version="2.0",
            )
            files = resp.get("files", [])
            if files:
                return 1, {
                    "paths": [f.get("path") for f in files[:20]],
                    "count": len(files),
                }
            return 0, {"count": 0}
        except Exception:
            # DBFS may not be accessible
            return 0, {"note": "DBFS not accessible or path does not exist"}


@register("16")
class Check16_DBFSMounts(BaseValidator):
    """GOV-11: DBFS mounts exist."""

    CHECK_ID = "GOV-11"
    CHECK_NAME = "DBFS mounts"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/dbfs/list",
                token=token,
                params={"path": "/mnt"},
                version="2.0",
            )
            files = resp.get("files", [])
            if files:
                return 1, {
                    "mounts": [f.get("path") for f in files[:20]],
                    "count": len(files),
                }
            return 0, {"count": 0}
        except Exception:
            return 0, {"note": "DBFS /mnt not accessible"}


@register("24")
class Check24_GlobalLibraries(BaseValidator):
    """INFO-3: Global libraries installed on clusters."""

    CHECK_ID = "INFO-3"
    CHECK_NAME = "Global libraries"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        # Get all clusters and check for global libraries
        clusters = self.rest.get_all_pages(
            "/clusters/list", token, list_key="clusters", version="2.1"
        )
        violations = []
        for c in clusters:
            cid = c.get("cluster_id")
            try:
                libs_resp = self.rest.get(
                    "/libraries/cluster-status",
                    token=token,
                    params={"cluster_id": cid},
                    version="2.0",
                )
                for lib_status in libs_resp.get("library_statuses", []):
                    if lib_status.get("is_library_for_all_clusters"):
                        violations.append({"cluster_id": cid})
                        break
            except Exception:
                continue

        score = 1 if violations else 0
        return score, {"clusters_with_global_libs": violations}


@register("26")
class Check26_GlobalInitScripts(BaseValidator):
    """INFO-5: Global init scripts exist."""

    CHECK_ID = "INFO-5"
    CHECK_NAME = "Global init scripts"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        resp = self.rest.get(
            "/global-init-scripts", token=token, version="2.0"
        )
        scripts = resp.get("scripts", [])
        if scripts:
            return 1, {
                "scripts": [
                    {"name": s.get("name"), "enabled": s.get("enabled")}
                    for s in scripts
                ]
            }
        return 0, {"script_count": 0}


@register("64")
class Check64_InitScriptsOnDBFS(BaseValidator):
    """GOV-25: Init scripts stored in DBFS."""

    CHECK_ID = "GOV-25"
    CHECK_NAME = "Init scripts in DBFS"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        try:
            resp = self.rest.get(
                "/dbfs/list",
                token=token,
                params={"path": "/databricks/scripts"},
                version="2.0",
            )
            files = resp.get("files", [])
            if files:
                return 1, {
                    "scripts": [
                        {"path": f.get("path"), "is_dir": f.get("is_dir")}
                        for f in files[:20]
                    ]
                }
            return 0, {"count": 0}
        except Exception:
            return 0, {"note": "DBFS scripts path not accessible"}


@register("8")
class Check8_LogDelivery(BaseValidator):
    """GOV-3: Audit log delivery configurations."""

    CHECK_ID = "GOV-3"
    CHECK_NAME = "Log delivery configurations"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_account_token()
        acct_id = self.config.account_console_id
        acct_client = self.account_rest or self.rest
        try:
            resp = acct_client.get(
                f"/accounts/{acct_id}/log-delivery", token=token
            )
            configs = resp.get("log_delivery_configurations", [])
            enabled_audit = [
                c
                for c in configs
                if c.get("log_type") == "AUDIT_LOGS"
                and c.get("status") == "ENABLED"
            ]
            if enabled_audit:
                return 0, {"enabled_audit_configs": len(enabled_audit)}
            return 1, {"enabled_audit_configs": 0}
        except Exception as e:
            return 1, {"error": str(e)}


@register("117")
class Check117_JobsRunAsServicePrincipal(BaseValidator):
    """GOV-42: Jobs should run as service principal, not user."""

    CHECK_ID = "GOV-42"
    CHECK_NAME = "Jobs run as service principal"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        jobs = self.rest.get_all_pages(
            "/jobs/list", token, list_key="jobs", version="2.1"
        )
        # Jobs where run_as_user_name contains '@' are running as a user
        violations = []
        for j in jobs:
            run_as = j.get("run_as_user_name", "")
            if "@" in run_as:
                violations.append(
                    {
                        "job_id": j.get("job_id"),
                        "job_name": j.get("settings", {}).get("name"),
                        "run_as_user_name": run_as,
                    }
                )
        score = 1 if violations else 0
        return score, {
            "jobs_running_as_user": violations[:50],
            "total_violations": len(violations),
        }


@register("123")
class Check123_JobsNotGrantingCanManage(BaseValidator):
    """GOV-45: Jobs not granting CAN_MANAGE to non-admin principals."""

    CHECK_ID = "GOV-45"
    CHECK_NAME = "Jobs CAN_MANAGE restricted"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        jobs = self.rest.get_all_pages(
            "/jobs/list", token, list_key="jobs", version="2.1"
        )
        violations = []
        for j in jobs:
            job_id = j.get("job_id")
            creator = j.get("creator_user_name", "")
            try:
                perms = self.rest.get(
                    f"/permissions/jobs/{job_id}", token=token, version="2.0"
                )
                for acl in perms.get("access_control_list", []):
                    for perm in acl.get("all_permissions", []):
                        if perm.get("permission_level") != "CAN_MANAGE":
                            continue
                        group = acl.get("group_name", "")
                        user = acl.get("user_name", "")
                        sp = acl.get("service_principal_name", "")
                        # Skip admins group and job creator
                        if group == "admins":
                            continue
                        if user and user == creator:
                            continue
                        principal = group or user or sp
                        if principal:
                            violations.append(
                                {
                                    "job_id": job_id,
                                    "job_name": j.get("settings", {}).get("name"),
                                    "principal": principal,
                                }
                            )
            except Exception:
                continue

        score = 1 if violations else 0
        return score, {
            "violations": violations[:50],
            "total": len(violations),
        }
