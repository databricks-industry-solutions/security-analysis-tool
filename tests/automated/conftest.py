"""Pytest configuration and shared fixtures for SAT automated tests."""

from __future__ import annotations

import os

import pytest

from tests.automated.auth.token_provider import TokenProvider
from tests.automated.checks.registry import load_check_definitions
from tests.automated.clients.rest_client import DatabricksRestClient
from tests.automated.clients.sql_client import SQLClient
from tests.automated.config.credentials import CloudConfig, load_cloud_config

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def pytest_addoption(parser):
    parser.addoption(
        "--cloud",
        action="store",
        default="aws",
        help="Cloud to test: aws|azure|gcp",
    )
    parser.addoption(
        "--run-id",
        action="store",
        type=int,
        default=None,
        help="SAT run_id to validate against (required for check tests)",
    )
    parser.addoption(
        "--check-id",
        action="store",
        default=None,
        help="Specific check_id to validate (e.g., DP-2)",
    )


@pytest.fixture(scope="session")
def cloud(request) -> str:
    return request.config.getoption("--cloud")


@pytest.fixture(scope="session")
def run_id(request) -> int | None:
    return request.config.getoption("--run-id")


@pytest.fixture(scope="session")
def check_definitions():
    csv_path = os.path.join(REPO_ROOT, "configs", "security_best_practices.csv")
    return load_check_definitions(csv_path)


@pytest.fixture(scope="session")
def cloud_config(cloud) -> CloudConfig:
    return load_cloud_config(cloud, REPO_ROOT)


@pytest.fixture(scope="session")
def token_provider(cloud_config) -> TokenProvider:
    return TokenProvider.create(cloud_config)


@pytest.fixture(scope="session")
def rest_client(cloud_config) -> DatabricksRestClient:
    return DatabricksRestClient(cloud_config.databricks_url)


@pytest.fixture(scope="session")
def account_rest_client(cloud_config) -> DatabricksRestClient:
    return DatabricksRestClient(cloud_config.accounts_url)


@pytest.fixture(scope="session")
def sql_client(rest_client, cloud_config) -> SQLClient:
    return SQLClient(rest_client, cloud_config.sqlw_id)


@pytest.fixture(scope="session")
def sat_results(sql_client, token_provider, cloud_config, run_id):
    """Load SAT results for the specified run_id, keyed by check db_id."""
    if run_id is None:
        return {}
    token = token_provider.get_workspace_token()
    rows = sql_client.get_sat_results(
        token, cloud_config.analysis_schema_name, cloud_config.workspace_id, run_id
    )
    return {str(row["id"]): row for row in rows}
