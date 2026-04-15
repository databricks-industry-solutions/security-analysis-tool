"""Connection tests to verify credentials and API access.

Usage:
    pytest tests/automated/test_connection.py --cloud=aws -v -s
"""

from __future__ import annotations

import pytest


class TestConnection:
    def test_workspace_token(self, token_provider):
        """Verify workspace OAuth token acquisition."""
        token = token_provider.get_workspace_token()
        assert token, "Failed to acquire workspace token"
        assert len(token) > 10
        print(f"Workspace token acquired ({len(token)} chars)")

    def test_account_token(self, token_provider):
        """Verify account-level OAuth token acquisition."""
        token = token_provider.get_account_token()
        assert token, "Failed to acquire account token"
        assert len(token) > 10
        print(f"Account token acquired ({len(token)} chars)")

    def test_workspace_api(self, rest_client, token_provider):
        """Verify workspace API connectivity."""
        token = token_provider.get_workspace_token()
        resp = rest_client.get(
            "/clusters/spark-versions", token=token, version="2.0"
        )
        versions = resp.get("versions", [])
        assert versions, "No spark versions returned"
        print(f"Workspace API OK: {len(versions)} runtime versions available")

    def test_sql_warehouse(self, sql_client, token_provider, cloud_config):
        """Verify SQL warehouse connectivity and SAT schema access."""
        token = token_provider.get_workspace_token()
        schema = cloud_config.analysis_schema_name
        rows = sql_client.execute_query(
            token,
            f"SELECT count(*) as cnt FROM {schema}.security_checks",
        )
        count = int(rows[0]["cnt"]) if rows else 0
        assert count > 0, f"No rows in {schema}.security_checks"
        print(f"SQL warehouse OK: {count} rows in security_checks")

    def test_list_runs(self, sql_client, token_provider, cloud_config):
        """List available SAT run IDs."""
        token = token_provider.get_workspace_token()
        schema = cloud_config.analysis_schema_name
        runs = sql_client.get_available_runs(token, schema)
        assert runs, "No SAT runs found"
        print(f"\nAvailable SAT runs:")
        for r in runs[:10]:
            print(f"  run_id={r['runID']}, check_time={r['check_time']}")
