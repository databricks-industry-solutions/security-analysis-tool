"""Query SAT output tables via the SQL Statements API."""

from __future__ import annotations

import time
from typing import Optional

from tests.automated.clients.rest_client import DatabricksRestClient


class SQLClient:
    """Execute SQL queries against a Databricks SQL warehouse."""

    def __init__(self, rest_client: DatabricksRestClient, warehouse_id: str):
        self.client = rest_client
        self.warehouse_id = warehouse_id

    def execute_query(
        self, token: str, sql: str, max_wait_seconds: int = 120
    ) -> list[dict]:
        """Execute SQL and return rows as list of dicts."""
        resp = self.client.post(
            "/sql/statements",
            token=token,
            json_body={
                "warehouse_id": self.warehouse_id,
                "statement": sql,
                "wait_timeout": "30s",
            },
        )
        status = resp.get("status", {}).get("state")
        statement_id = resp.get("statement_id")

        elapsed = 0
        while status in ("PENDING", "RUNNING") and elapsed < max_wait_seconds:
            time.sleep(2)
            elapsed += 2
            resp = self.client.get(
                f"/sql/statements/{statement_id}", token=token
            )
            status = resp.get("status", {}).get("state")

        if status != "SUCCEEDED":
            error = resp.get("status", {}).get("error", {})
            raise RuntimeError(f"SQL query failed ({status}): {error}")

        manifest = resp.get("manifest", {})
        columns = [
            col["name"] for col in manifest.get("schema", {}).get("columns", [])
        ]
        data_array = resp.get("result", {}).get("data_array", [])
        return [dict(zip(columns, row)) for row in data_array]

    def get_available_runs(self, token: str, schema: str) -> list[dict]:
        """List available SAT run IDs with timestamps."""
        sql = f"""
            SELECT runID, check_time
            FROM {schema}.run_number_table
            ORDER BY runID DESC
            LIMIT 20
        """
        return self.execute_query(token, sql)

    def get_workspaces(self, token: str, schema: str) -> list[dict]:
        """Get all analysis-enabled workspaces from SAT's account_workspaces table."""
        sql = f"""
            SELECT workspace_id, workspace_name, deployment_url, analysis_enabled
            FROM {schema}.account_workspaces
            WHERE analysis_enabled = true
            ORDER BY workspace_id
        """
        return self.execute_query(token, sql)

    def get_sat_results(
        self,
        token: str,
        schema: str,
        workspace_id: str,
        run_id: int,
        check_id: Optional[str] = None,
    ) -> list[dict]:
        """Get SAT results for a specific run_id and workspace."""
        check_filter = f"AND sc.id = '{check_id}'" if check_id else ""
        sql = f"""
            SELECT sc.id, sc.score, sc.additional_details, sc.check_time
            FROM {schema}.security_checks sc
            WHERE sc.workspaceid = '{workspace_id}'
              AND sc.run_id = {run_id}
              {check_filter}
            ORDER BY sc.id
        """
        return self.execute_query(token, sql)
