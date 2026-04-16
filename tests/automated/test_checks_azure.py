"""Run all SAT check validators against Azure workspace."""

from __future__ import annotations

import os

import pytest

# Import all validator modules to trigger registration
import tests.automated.checks.workspace_settings_v1  # noqa: F401
import tests.automated.checks.settings_v2  # noqa: F401
import tests.automated.checks.clusters  # noqa: F401
import tests.automated.checks.tokens  # noqa: F401
import tests.automated.checks.unity_catalog  # noqa: F401
import tests.automated.checks.network  # noqa: F401
import tests.automated.checks.identity  # noqa: F401
import tests.automated.checks.governance  # noqa: F401
import tests.automated.checks.informational  # noqa: F401

from tests.automated.checks.base_validator import ValidationResult
from tests.automated.checks.registry import get_validator, load_check_definitions
from tests.automated.reporting.markdown_report import generate_report

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CLOUD = "azure"


def _get_applicable_check_ids(check_defs: dict) -> list[str]:
    applicable = []
    for db_id, defn in check_defs.items():
        if not defn.enabled or CLOUD not in defn.clouds:
            continue
        if get_validator(db_id) is None:
            continue
        applicable.append(db_id)
    return sorted(applicable, key=int)


@pytest.fixture(scope="module")
def all_results(
    cloud_config,
    token_provider,
    rest_client,
    account_rest_client,
    sat_results,
    check_definitions,
    run_id,
):
    results: list[ValidationResult] = []
    for db_id in _get_applicable_check_ids(check_definitions):
        validator_cls = get_validator(db_id)
        defn = check_definitions[db_id]
        validator = validator_cls(
            cloud_config, token_provider, rest_client, account_rest_client
        )
        validator.CHECK_ID = defn.check_id
        validator.CHECK_NAME = defn.check
        validator.CLOUDS = defn.clouds
        sat_result = sat_results.get(db_id)
        result = validator.validate(sat_result)
        result.category = defn.category
        result.severity = defn.severity
        results.append(result)
    return results


class TestSATChecksAzure:
    def test_all_checks_agree(self, all_results, run_id):
        disagreements = [r for r in all_results if r.agreement == "DISAGREE"]
        if disagreements:
            msg = f"{len(disagreements)} checks disagree with API:\n"
            for r in disagreements:
                msg += f"  {r.check_id}: API={r.api_score}, SAT={r.sat_score}\n"
            pytest.fail(msg)

    def test_generate_report(self, all_results, run_id):
        rid = run_id or 0
        output_path = os.path.join(
            REPO_ROOT, "tests", "automated", "reports", f"azure_run{rid}_report.md"
        )
        generate_report(all_results, CLOUD, rid, output_path)
        assert os.path.exists(output_path)
