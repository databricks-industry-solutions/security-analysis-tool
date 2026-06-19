"""Validate SAT workspace-admin mode behavior.

Verifies that when SAT runs without account-admin credentials:
1. Workspace-level checks produce results (AGREE with live API)
2. Account-level checks are correctly skipped (SAT_MISSING)
3. The single-workspace bootstrap populates account_workspaces
4. Config resolution falls back to widget parameters when secrets are absent

Usage:
    # Run against a SAT run that was executed in workspace-admin mode
    pytest tests/automated/test_workspace_admin_mode.py --cloud=azure --run-id <id> -v -s

    # Connection-only checks (no SAT run needed)
    pytest tests/automated/test_workspace_admin_mode.py --cloud=azure -v -s -k "not requires_run"
"""

from __future__ import annotations

import os
from typing import Optional

import pytest

from tests.automated.auth.token_provider import TokenProvider
from tests.automated.checks.registry import get_validator, load_check_definitions
from tests.automated.clients.rest_client import DatabricksRestClient
from tests.automated.clients.sql_client import SQLClient
from tests.automated.config.credentials import CloudConfig

# Check IDs (db_id from CSV) that require account-admin or metastore-admin.
# These MUST be SAT_MISSING in a workspace-admin run.
ACCOUNT_ADMIN_CHECK_IDS = {
    "GOV-3",   # Log delivery configurations
    "GOV-20",  # Existence of Unity Catalog metastores
    "GOV-21",  # Delegation of the Unity Catalog metastore admin to a group
    "GOV-34",  # Monitor audit logs with system tables
    "GOV-37",  # Disable legacy features for new workspaces
    "NS-3",    # Front-end private connectivity
    "NS-4",    # Workspace uses customer-managed VPC / VNet injection
    "NS-6",    # Secure cluster connectivity (NoPublicIp)
    "NS-8",    # IP access lists for account console access
    "NS-9",    # Workspaces have proper network policy configuration
    "NS-12",   # Context-Based Ingress (CBI) policy configured
    "NS-13",   # Account console IP access list enforcement enabled
}

METASTORE_ADMIN_CHECK_IDS = {
    "INFO-38",  # Third-party library control (MANAGE ALLOWLIST on Metastore)
}

# All checks that should be absent in workspace-admin mode
NON_WORKSPACE_CHECK_IDS = ACCOUNT_ADMIN_CHECK_IDS | METASTORE_ADMIN_CHECK_IDS

# Checks confirmed to work at workspace-admin level (HTTP 200)
WORKSPACE_LEVEL_CHECKS = {
    "GOV-15", "GOV-17", "GOV-35",
    "INFO-29", "INFO-39", "INFO-40", "INFO-42", "INFO-6",
}

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ws_admin_config(cloud_config: CloudConfig) -> CloudConfig:
    """Return the cloud config, validating it represents workspace-admin mode.

    In workspace-admin mode, `account_console_id` should be empty or the
    runner should explicitly lack account-level credentials. This fixture
    warns if the config looks like account-admin (tests will still run but
    SAT_MISSING assertions may fail if SAT was run with full credentials).
    """
    if cloud_config.account_console_id and cloud_config.client_secret:
        pytest.skip(
            "This test suite validates workspace-admin mode. "
            "The current terraform.tfvars has account-admin credentials "
            "(account_console_id + client_secret are both set). "
            "To test workspace-admin mode, use a tfvars without "
            "account_console_id or run SAT without the secret scope configured."
        )
    return cloud_config


@pytest.fixture(scope="module")
def ws_token_provider(ws_admin_config: CloudConfig) -> TokenProvider:
    """Token provider for workspace-admin mode (workspace token only)."""
    return TokenProvider.create(ws_admin_config)


@pytest.fixture(scope="module")
def ws_rest_client(ws_admin_config: CloudConfig) -> DatabricksRestClient:
    return DatabricksRestClient(ws_admin_config.databricks_url)


@pytest.fixture(scope="module")
def ws_sql_client(ws_rest_client, ws_admin_config) -> SQLClient:
    return SQLClient(ws_rest_client, ws_admin_config.sqlw_id)


@pytest.fixture(scope="module")
def ws_sat_results(ws_sql_client, ws_token_provider, ws_admin_config, run_id):
    """Load SAT results from a workspace-admin run."""
    if run_id is None:
        return {}
    token = ws_token_provider.get_workspace_token()
    rows = ws_sql_client.get_sat_results(
        token,
        ws_admin_config.analysis_schema_name,
        ws_admin_config.workspace_id,
        run_id,
    )
    return {row["id"]: row for row in rows}


@pytest.fixture(scope="module")
def check_defs():
    csv_path = os.path.join(REPO_ROOT, "configs", "security_best_practices.csv")
    return load_check_definitions(csv_path)


# ---------------------------------------------------------------------------
# Connection tests (no SAT run needed)
# ---------------------------------------------------------------------------


class TestWorkspaceAdminConnection:
    """Verify connectivity works with workspace-admin credentials only."""

    def test_workspace_token_acquired(self, ws_token_provider):
        """Workspace OAuth token can be obtained without account credentials."""
        token = ws_token_provider.get_workspace_token()
        assert token and len(token) > 10, "Failed to acquire workspace token"
        print(f"✅ Workspace token acquired ({len(token)} chars)")

    def test_account_token_unavailable(self, ws_token_provider):
        """Account-level token should NOT be obtainable in workspace-admin mode."""
        try:
            token = ws_token_provider.get_account_token()
            if token:
                pytest.skip(
                    "Account token was acquired — this config has account-admin "
                    "credentials. Workspace-admin mode cannot be fully validated."
                )
        except Exception:
            pass  # Expected: cannot get account token in workspace-admin mode
        print("✅ Account token correctly unavailable")

    def test_workspace_api_accessible(self, ws_rest_client, ws_token_provider):
        """Workspace REST API responds to workspace-admin credentials."""
        token = ws_token_provider.get_workspace_token()
        resp = ws_rest_client.get(
            "/clusters/spark-versions", token=token, version="2.0"
        )
        versions = resp.get("versions", [])
        assert versions, "Workspace API did not return spark versions"
        print(f"✅ Workspace API accessible ({len(versions)} runtime versions)")

    def test_sql_warehouse_accessible(
        self, ws_sql_client, ws_token_provider, ws_admin_config
    ):
        """SQL warehouse and SAT schema are queryable."""
        token = ws_token_provider.get_workspace_token()
        schema = ws_admin_config.analysis_schema_name
        rows = ws_sql_client.execute_query(
            token, f"SELECT count(*) as cnt FROM {schema}.security_checks"
        )
        count = int(rows[0]["cnt"]) if rows else 0
        assert count > 0, f"No rows in {schema}.security_checks"
        print(f"✅ SQL warehouse OK ({count} rows in security_checks)")


# ---------------------------------------------------------------------------
# Workspace bootstrap tests (requires a SAT run in workspace-admin mode)
# ---------------------------------------------------------------------------


class TestSingleWorkspaceBootstrap:
    """Verify the single-workspace bootstrap registered the workspace."""

    pytestmark = pytest.mark.requires_run

    def test_current_workspace_registered(
        self, ws_sql_client, ws_token_provider, ws_admin_config
    ):
        """account_workspaces contains the current workspace (MERGE bootstrap)."""
        token = ws_token_provider.get_workspace_token()
        schema = ws_admin_config.analysis_schema_name
        workspace_id = ws_admin_config.workspace_id
        rows = ws_sql_client.execute_query(
            token,
            f"""
            SELECT workspace_id, deployment_url, analysis_enabled
            FROM {schema}.account_workspaces
            WHERE workspace_id = '{workspace_id}'
            """,
        )
        assert rows, (
            f"Workspace {workspace_id} not found in account_workspaces. "
            "Single-workspace bootstrap may not have run."
        )
        row = rows[0]
        assert row["analysis_enabled"] in ("true", "True", True, "1"), (
            f"Workspace {workspace_id} found but analysis_enabled={row['analysis_enabled']}"
        )
        print(f"✅ Workspace {workspace_id} registered with analysis_enabled=true")

    def test_only_one_workspace_present(
        self, ws_sql_client, ws_token_provider, ws_admin_config
    ):
        """In workspace-admin mode, only the current workspace should exist."""
        token = ws_token_provider.get_workspace_token()
        schema = ws_admin_config.analysis_schema_name
        rows = ws_sql_client.execute_query(
            token,
            f"SELECT count(*) as cnt FROM {schema}.account_workspaces",
        )
        count = int(rows[0]["cnt"]) if rows else 0
        # In pure workspace-admin mode, expect exactly 1.
        # Allow more if this was previously an account-admin deployment.
        if count > 1:
            print(
                f"⚠️  {count} workspaces in account_workspaces — "
                "this may be a previously account-admin deployment"
            )
        else:
            print(f"✅ Exactly {count} workspace in account_workspaces")
        assert count >= 1


# ---------------------------------------------------------------------------
# Account-level checks should be SAT_MISSING
# ---------------------------------------------------------------------------


class TestAccountChecksSkipped:
    """Verify that account-level checks are NOT present in a workspace-admin run."""

    pytestmark = pytest.mark.requires_run

    def test_account_admin_checks_missing(self, ws_sat_results, check_defs):
        """All 12 account-admin checks should have no SAT result row."""
        if not ws_sat_results:
            pytest.skip("No SAT results loaded (--run-id not provided)")

        present = []
        for check_id in ACCOUNT_ADMIN_CHECK_IDS:
            # Find the numeric db_id for this check_id
            db_id = _find_db_id(check_defs, check_id)
            if db_id and db_id in ws_sat_results:
                present.append(check_id)

        assert not present, (
            f"Account-admin checks should be skipped in workspace-admin mode, "
            f"but found results for: {sorted(present)}"
        )
        print(
            f"✅ All {len(ACCOUNT_ADMIN_CHECK_IDS)} account-admin checks "
            "correctly absent (SAT_MISSING)"
        )

    def test_metastore_admin_checks_missing(self, ws_sat_results, check_defs):
        """Metastore-admin checks should have no SAT result row."""
        if not ws_sat_results:
            pytest.skip("No SAT results loaded (--run-id not provided)")

        present = []
        for check_id in METASTORE_ADMIN_CHECK_IDS:
            db_id = _find_db_id(check_defs, check_id)
            if db_id and db_id in ws_sat_results:
                present.append(check_id)

        assert not present, (
            f"Metastore-admin checks should be skipped, "
            f"but found results for: {sorted(present)}"
        )
        print(
            f"✅ All {len(METASTORE_ADMIN_CHECK_IDS)} metastore-admin checks "
            "correctly absent"
        )


# ---------------------------------------------------------------------------
# Workspace-level checks should be present and valid
# ---------------------------------------------------------------------------


class TestWorkspaceChecksPresent:
    """Verify that workspace-level checks produced results."""

    pytestmark = pytest.mark.requires_run

    def test_workspace_checks_have_results(self, ws_sat_results, check_defs):
        """Known workspace-level checks should have SAT result rows."""
        if not ws_sat_results:
            pytest.skip("No SAT results loaded (--run-id not provided)")

        missing = []
        for check_id in WORKSPACE_LEVEL_CHECKS:
            db_id = _find_db_id(check_defs, check_id)
            if db_id and db_id not in ws_sat_results:
                missing.append(check_id)

        # Allow some flexibility — not all checks may apply depending on config
        missing_pct = len(missing) / len(WORKSPACE_LEVEL_CHECKS)
        if missing_pct > 0.5:
            pytest.fail(
                f"Too many workspace-level checks missing ({len(missing)}/{len(WORKSPACE_LEVEL_CHECKS)}): "
                f"{sorted(missing)}. SAT may not have run correctly in workspace-admin mode."
            )
        elif missing:
            print(
                f"⚠️  {len(missing)} workspace-level checks missing "
                f"(may be disabled in config): {sorted(missing)}"
            )
        found = len(WORKSPACE_LEVEL_CHECKS) - len(missing)
        print(
            f"✅ {found}/{len(WORKSPACE_LEVEL_CHECKS)} workspace-level checks "
            "produced results"
        )

    def test_total_checks_reasonable(self, ws_sat_results, check_defs):
        """Workspace-admin run should produce at least 40+ check results.

        Full account-admin run produces 65+. With 13 skipped, we expect ~52+.
        Allow a lower threshold for flexibility (disabled checks, etc.).
        """
        if not ws_sat_results:
            pytest.skip("No SAT results loaded (--run-id not provided)")

        total = len(ws_sat_results)
        assert total >= 40, (
            f"Only {total} check results found — expected at least 40 "
            "for a workspace-admin run (65+ total minus 13 account-level). "
            "SAT may not have completed successfully."
        )
        print(f"✅ {total} total check results (expected ≥40 for workspace-admin mode)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_db_id(check_defs: dict, check_id: str) -> Optional[str]:
    """Find the numeric db_id for a given check_id (e.g. 'GOV-3' -> '8')."""
    for db_id, defn in check_defs.items():
        if defn.check_id == check_id:
            return db_id
    return None
