"""Validators for cluster-based security checks.

Uses: GET /api/2.1/clusters/list
Reference: notebooks/Includes/workspace_analysis.py
"""

import time

from tests.automated.checks.base_validator import BaseValidator
from tests.automated.checks.registry import register


def _get_interactive_clusters(validator: BaseValidator) -> list[dict]:
    """Fetch clusters filtered to UI/API source (interactive clusters)."""
    token = validator.token_provider.get_workspace_token()
    clusters = validator.rest.get_all_pages(
        "/clusters/list", token, list_key="clusters", version="2.1"
    )
    return [
        c for c in clusters if c.get("cluster_source") in ("UI", "API")
    ]


@register("2")
class Check2_DiskEncryption(BaseValidator):
    """DP-2: Check if enable_local_disk_encryption is false for any cluster."""

    CHECK_ID = "DP-2"
    CHECK_NAME = "Cluster instance disk encryption"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        clusters = _get_interactive_clusters(self)
        violations = [
            {"cluster_id": c["cluster_id"], "cluster_name": c.get("cluster_name")}
            for c in clusters
            if not c.get("enable_local_disk_encryption", True)
        ]
        score = 1 if violations else 0
        return score, {"unencrypted_clusters": violations}


@register("9")
class Check9_LongRunningClusters(BaseValidator):
    """GOV-4: Clusters running longer than evaluation_value days."""

    CHECK_ID = "GOV-4"
    CHECK_NAME = "Long-running clusters"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        clusters = _get_interactive_clusters(self)
        now_ms = int(time.time() * 1000)
        # Default from CSV evaluation_value; will be overridden by check_def
        threshold_days = 24
        violations = []
        for c in clusters:
            if c.get("state") != "RUNNING":
                continue
            last_restart = max(
                c.get("start_time", 0), c.get("last_restarted_time", 0)
            )
            if last_restart > 0:
                days_running = (now_ms - last_restart) / (1000 * 86400)
                if days_running > threshold_days:
                    violations.append(
                        {
                            "cluster_id": c["cluster_id"],
                            "cluster_name": c.get("cluster_name"),
                            "days_running": round(days_running, 1),
                        }
                    )
        score = 1 if violations else 0
        return score, {"long_running_clusters": violations}


@register("10")
class Check10_DeprecatedRuntimes(BaseValidator):
    """GOV-5: Clusters using deprecated Databricks runtime versions."""

    CHECK_ID = "GOV-5"
    CHECK_NAME = "Deprecated runtime versions"
    CLOUDS = ["aws", "azure", "gcp"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        token = self.token_provider.get_workspace_token()
        # Get valid runtime versions
        versions_resp = self.rest.get(
            "/clusters/spark-versions", token=token, version="2.0"
        )
        valid_keys = {v["key"] for v in versions_resp.get("versions", [])}
        # Get clusters
        clusters = _get_interactive_clusters(self)
        violations = [
            {
                "cluster_id": c["cluster_id"],
                "cluster_name": c.get("cluster_name"),
                "spark_version": c.get("spark_version"),
            }
            for c in clusters
            if c.get("spark_version") and c["spark_version"] not in valid_keys
        ]
        score = 1 if violations else 0
        return score, {"deprecated_clusters": violations}


@register("17")
class Check17_UCEnabledClusters(BaseValidator):
    """GOV-12: Clusters not using Unity Catalog data_security_mode."""

    CHECK_ID = "GOV-12"
    CHECK_NAME = "Unity Catalog enabled clusters"
    CLOUDS = ["aws", "azure"]

    def evaluate_from_api(self) -> tuple[int, dict]:
        clusters = _get_interactive_clusters(self)
        violations = [
            {
                "cluster_id": c["cluster_id"],
                "cluster_name": c.get("cluster_name"),
                "data_security_mode": c.get("data_security_mode"),
            }
            for c in clusters
            if c.get("data_security_mode") not in ("USER_ISOLATION", "SINGLE_USER")
        ]
        score = 1 if violations else 0
        return score, {"non_uc_clusters": violations}
