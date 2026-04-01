"""Run a single SAT check validator for targeted debugging.

Usage:
    pytest tests/automated/test_single_check.py --check-id=DP-2 --cloud=aws --run-id=42 -v -s
"""

from __future__ import annotations

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

from tests.automated.checks.registry import get_validator


class TestSingleCheck:
    def test_single_check(
        self,
        request,
        check_definitions,
        cloud_config,
        token_provider,
        rest_client,
        account_rest_client,
        sat_results,
        run_id,
    ):
        check_id_arg = request.config.getoption("--check-id")
        if check_id_arg is None:
            pytest.skip("No --check-id specified")

        # Find db_id by check_id
        db_id = None
        for did, defn in check_definitions.items():
            if defn.check_id == check_id_arg:
                db_id = did
                break
        assert db_id, f"Check '{check_id_arg}' not found in security_best_practices.csv"

        validator_cls = get_validator(db_id)
        assert (
            validator_cls
        ), f"No validator registered for {check_id_arg} (db_id={db_id})"

        defn = check_definitions[db_id]
        validator = validator_cls(
            cloud_config, token_provider, rest_client, account_rest_client
        )
        validator.CHECK_ID = defn.check_id
        validator.CHECK_NAME = defn.check
        validator.CLOUDS = defn.clouds

        sat_result = sat_results.get(db_id)
        result = validator.validate(sat_result)

        # Print detailed output
        print(f"\n{'='*60}")
        print(f"Check: {result.check_id} - {result.check_name}")
        print(f"Cloud: {result.cloud}")
        print(f"{'='*60}")
        print(f"API Score:  {result.api_score} ({'PASS' if result.api_score == 0 else 'FAIL'})")
        print(f"API Details: {result.api_details}")
        if result.api_error:
            print(f"API Error:  {result.api_error}")
        print(f"SAT Score:  {result.sat_score} ({'PASS' if result.sat_score == 0 else 'FAIL' if result.sat_score else 'N/A'})")
        print(f"SAT Details: {result.sat_details}")
        if result.sat_error:
            print(f"SAT Error:  {result.sat_error}")
        print(f"Verdict:    {result.agreement}")
        print(f"{'='*60}")

        if result.agreement == "DISAGREE":
            pytest.fail(
                f"Check {result.check_id} DISAGREES: "
                f"API={result.api_score}, SAT={result.sat_score}"
            )
