"""Run all SAT check validators against AWS workspace."""

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
from tests.automated.checks.registry import (
    VALIDATOR_MAP,
    get_validator,
    load_check_definitions,
)
from tests.automated.reporting.markdown_report import generate_report

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CLOUD = "aws"


def _get_applicable_check_ids(check_defs: dict) -> list[str]:
    """Return check db_ids that are enabled, applicable to AWS, and have a validator."""
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
    """Run all validators and collect results."""
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


class TestSATChecksAWS:
    def test_all_checks_agree(self, all_results, run_id):
        """All validated checks should agree with API ground truth."""
        disagreements = [r for r in all_results if r.agreement == "DISAGREE"]
        if disagreements:
            msg = f"{len(disagreements)} checks disagree with API:\n"
            for r in disagreements:
                msg += (
                    f"  {r.check_id} ({r.check_name}): "
                    f"API={r.api_score}, SAT={r.sat_score}\n"
                )
            pytest.fail(msg)

    def test_no_missing_sat_results(self, all_results, run_id):
        """All checks should have corresponding SAT output."""
        if run_id is None:
            pytest.skip("No --run-id specified")
        missing = [r for r in all_results if r.agreement == "SAT_MISSING"]
        if missing:
            msg = f"{len(missing)} checks missing from SAT output:\n"
            for r in missing:
                msg += f"  {r.check_id}: {r.check_name}\n"
            pytest.fail(msg)

    def test_generate_report(self, all_results, run_id):
        """Generate the validation report."""
        rid = run_id or 0
        output_path = os.path.join(
            REPO_ROOT, "tests", "automated", "reports", f"aws_run{rid}_report.md"
        )
        report = generate_report(all_results, CLOUD, rid, output_path)
        print(f"\nReport written to: {output_path}")
        assert os.path.exists(output_path)
