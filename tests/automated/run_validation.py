#!/usr/bin/env python3
"""CLI entry point for SAT validation framework.

Usage:
    # List available SAT runs
    python -m tests.automated.run_validation --cloud aws --list-runs

    # Run all checks against a specific SAT run
    python -m tests.automated.run_validation --cloud aws --run-id 42

    # Run a single check
    python -m tests.automated.run_validation --cloud aws --run-id 42 --check-id DP-2

    # Run without SAT comparison (API-only)
    python -m tests.automated.run_validation --cloud aws --api-only
"""

from __future__ import annotations

import argparse
import os
import sys

# Add repo root to path
REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, REPO_ROOT)

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

from tests.automated.auth.token_provider import TokenProvider
from tests.automated.checks.base_validator import ValidationResult
from tests.automated.checks.registry import (
    VALIDATOR_MAP,
    get_validator,
    load_check_definitions,
)
from tests.automated.clients.rest_client import DatabricksRestClient
from tests.automated.clients.sql_client import SQLClient
from tests.automated.config.credentials import load_cloud_config
from tests.automated.reporting.markdown_report import generate_report


def list_runs(args):
    config = load_cloud_config(args.cloud, REPO_ROOT)
    tp = TokenProvider.create(config)
    rest = DatabricksRestClient(config.databricks_url)
    sql = SQLClient(rest, config.sqlw_id)
    token = tp.get_workspace_token()
    runs = sql.get_available_runs(token, config.analysis_schema_name)
    print(f"\nAvailable SAT runs for {args.cloud.upper()} ({config.databricks_url}):")
    print(f"{'Run ID':>10}  {'Check Time'}")
    print(f"{'-'*10}  {'-'*25}")
    for r in runs:
        print(f"{r['runID']:>10}  {r['check_time']}")


def run_validation(args):
    config = load_cloud_config(args.cloud, REPO_ROOT)
    tp = TokenProvider.create(config)
    rest = DatabricksRestClient(config.databricks_url)
    acct_rest = DatabricksRestClient(config.accounts_url)
    sql = SQLClient(rest, config.sqlw_id)
    check_defs = load_check_definitions(
        os.path.join(REPO_ROOT, "configs", "security_best_practices.csv")
    )

    # Load SAT results if run_id specified
    sat_results_map: dict[str, dict] = {}
    if args.run_id and not args.api_only:
        token = tp.get_workspace_token()
        rows = sql.get_sat_results(
            token, config.analysis_schema_name, config.workspace_id, args.run_id
        )
        sat_results_map = {str(row["id"]): row for row in rows}
        print(f"Loaded {len(sat_results_map)} SAT results for run_id={args.run_id}")

    # Determine which checks to run
    applicable: list[str] = []
    for db_id, defn in check_defs.items():
        if not defn.enabled or args.cloud not in defn.clouds:
            continue
        if get_validator(db_id) is None:
            continue
        if args.check_id:
            if defn.check_id != args.check_id:
                continue
        applicable.append(db_id)

    applicable.sort(key=int)
    print(f"Running {len(applicable)} check validators...")

    # Execute validators
    results: list[ValidationResult] = []
    for i, db_id in enumerate(applicable, 1):
        defn = check_defs[db_id]
        validator_cls = get_validator(db_id)
        validator = validator_cls(config, tp, rest, acct_rest)
        validator.CHECK_ID = defn.check_id
        validator.CHECK_NAME = defn.check
        validator.CLOUDS = defn.clouds

        sat_result = sat_results_map.get(db_id)
        result = validator.validate(sat_result if not args.api_only else None)
        result.category = defn.category
        result.severity = defn.severity
        results.append(result)

        status = "PASS" if result.api_score == 0 else "FAIL"
        if result.api_error:
            status = "ERR"
        verdict = result.agreement if not args.api_only else status
        print(f"  [{i}/{len(applicable)}] {defn.check_id:10s} {status:4s}  {verdict:12s}  {defn.check[:50]}")

    # Generate report
    rid = args.run_id or 0
    output_path = os.path.join(
        REPO_ROOT, "tests", "automated", "reports",
        f"{args.cloud}_run{rid}_report.md",
    )
    generate_report(results, args.cloud, rid, output_path)

    # Summary
    agree = sum(1 for r in results if r.agreement == "AGREE")
    disagree = sum(1 for r in results if r.agreement == "DISAGREE")
    errors = sum(1 for r in results if r.agreement == "API_ERROR")
    missing = sum(1 for r in results if r.agreement == "SAT_MISSING")

    print(f"\n{'='*50}")
    print(f"AGREE: {agree} | DISAGREE: {disagree} | API_ERROR: {errors} | SAT_MISSING: {missing}")
    print(f"Report: {output_path}")
    print(f"{'='*50}")

    if disagree > 0:
        print(f"\nDiscrepancies found in {disagree} checks:")
        for r in results:
            if r.agreement == "DISAGREE":
                print(f"  {r.check_id}: API={r.api_score}, SAT={r.sat_score} — {r.check_name}")


def main():
    parser = argparse.ArgumentParser(
        description="SAT Automated Validation Framework"
    )
    parser.add_argument(
        "--cloud",
        choices=["aws", "azure", "gcp"],
        default="aws",
        help="Cloud to test (default: aws)",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="SAT run_id to validate against",
    )
    parser.add_argument(
        "--check-id",
        help="Specific check_id to validate (e.g., DP-2)",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="List available SAT run IDs and exit",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Run API checks only without SAT comparison",
    )

    args = parser.parse_args()

    if args.list_runs:
        list_runs(args)
        return

    if not args.run_id and not args.api_only:
        print("Error: --run-id is required (or use --api-only for API-only mode)")
        print("Use --list-runs to discover available run IDs")
        sys.exit(1)

    run_validation(args)


if __name__ == "__main__":
    main()
