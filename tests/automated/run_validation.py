#!/usr/bin/env python3
"""CLI entry point for SAT validation framework.

Usage:
    # List available SAT runs
    python -m tests.automated.run_validation --cloud aws --list-runs

    # Run all checks for the tfvars workspace
    python -m tests.automated.run_validation --cloud aws --run-id 24

    # Run all checks across ALL workspaces in the account
    python -m tests.automated.run_validation --cloud aws --run-id 24 --all-workspaces

    # Run a single check
    python -m tests.automated.run_validation --cloud aws --run-id 24 --check-id DP-2

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
from tests.automated.config.credentials import CloudConfig, load_cloud_config
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


def _get_applicable_checks(check_defs, cloud, check_id_filter=None):
    """Return sorted list of check db_ids that are enabled, cloud-applicable, and have validators."""
    applicable = []
    for db_id, defn in check_defs.items():
        if not defn.enabled or cloud not in defn.clouds:
            continue
        if get_validator(db_id) is None:
            continue
        if check_id_filter and defn.check_id != check_id_filter:
            continue
        applicable.append(db_id)
    return sorted(applicable, key=int)


def _run_checks_for_workspace(
    workspace_id: str,
    workspace_name: str,
    workspace_url: str,
    config: CloudConfig,
    tp: TokenProvider,
    acct_rest: DatabricksRestClient,
    sql: SQLClient,
    check_defs: dict,
    applicable: list[str],
    run_id: int | None,
    api_only: bool,
) -> list[ValidationResult]:
    """Run all applicable checks for a single workspace."""
    # Create a rest client pointing at this workspace's URL
    ws_rest = DatabricksRestClient(f"https://{workspace_url}")

    # We reuse the same SP — get a workspace token for THIS workspace
    # The SP OAuth endpoint is per-workspace
    ws_tp = TokenProvider.create(
        CloudConfig(
            cloud=config.cloud,
            databricks_url=f"https://{workspace_url}",
            workspace_id=workspace_id,
            account_console_id=config.account_console_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
            sqlw_id=config.sqlw_id,
            analysis_schema_name=config.analysis_schema_name,
            tenant_id=config.tenant_id,
            subscription_id=config.subscription_id,
        )
    )

    # Load SAT results for this workspace
    sat_results_map: dict[str, dict] = {}
    if run_id and not api_only:
        home_token = tp.get_workspace_token()
        rows = sql.get_sat_results(
            home_token, config.analysis_schema_name, workspace_id, run_id
        )
        sat_results_map = {str(row["id"]): row for row in rows}

    results: list[ValidationResult] = []
    for i, db_id in enumerate(applicable, 1):
        defn = check_defs[db_id]
        validator_cls = get_validator(db_id)
        validator = validator_cls(
            ws_tp.config, ws_tp, ws_rest, acct_rest
        )
        validator.CHECK_ID = defn.check_id
        validator.CHECK_NAME = defn.check
        validator.CLOUDS = defn.clouds

        sat_result = sat_results_map.get(db_id)
        result = validator.validate(sat_result if not api_only else None)
        result.category = defn.category
        result.severity = defn.severity
        results.append(result)

        status = "PASS" if result.api_score == 0 else "FAIL"
        if result.api_error:
            status = "ERR"
        verdict = result.agreement if not api_only else status
        print(
            f"  [{i}/{len(applicable)}] {defn.check_id:10s} {status:4s}  "
            f"{verdict:12s}  {defn.check[:50]}"
        )

    return results


def _print_summary(results, label, output_path=None):
    agree = sum(1 for r in results if r.agreement == "AGREE")
    disagree = sum(1 for r in results if r.agreement == "DISAGREE")
    errors = sum(1 for r in results if r.agreement == "API_ERROR")
    missing = sum(1 for r in results if r.agreement == "SAT_MISSING")
    print(f"\n  {label}: AGREE={agree} | DISAGREE={disagree} | API_ERROR={errors} | SAT_MISSING={missing}")
    if output_path:
        print(f"  Report: {output_path}")
    if disagree > 0:
        for r in results:
            if r.agreement == "DISAGREE":
                print(f"    {r.check_id}: API={r.api_score}, SAT={r.sat_score} — {r.check_name}")


def run_validation(args):
    config = load_cloud_config(args.cloud, REPO_ROOT)
    tp = TokenProvider.create(config)
    rest = DatabricksRestClient(config.databricks_url)
    acct_rest = DatabricksRestClient(config.accounts_url)
    sql = SQLClient(rest, config.sqlw_id)
    check_defs = load_check_definitions(
        os.path.join(REPO_ROOT, "configs", "security_best_practices.csv")
    )
    applicable = _get_applicable_checks(check_defs, args.cloud, args.check_id)

    # Determine workspaces to test
    if args.all_workspaces:
        home_token = tp.get_workspace_token()
        workspaces = sql.get_workspaces(home_token, config.analysis_schema_name)
        print(f"Found {len(workspaces)} workspaces to validate")
    else:
        # Single workspace from tfvars
        workspaces = [
            {
                "workspace_id": config.workspace_id,
                "workspace_name": "tfvars-workspace",
                "deployment_url": config.databricks_url.replace("https://", ""),
            }
        ]

    rid = args.run_id or 0
    all_results: dict[str, list[ValidationResult]] = {}

    for ws in workspaces:
        ws_id = ws["workspace_id"]
        ws_name = ws["workspace_name"]
        ws_url = ws["deployment_url"]

        print(f"\n{'='*60}")
        print(f"Workspace: {ws_name} ({ws_id})")
        print(f"URL: https://{ws_url}")
        print(f"{'='*60}")

        # Load SAT result count for this workspace
        if args.run_id and not args.api_only:
            home_token = tp.get_workspace_token()
            rows = sql.get_sat_results(
                home_token, config.analysis_schema_name, ws_id, args.run_id
            )
            print(f"SAT results for run {args.run_id}: {len(rows)} checks")
        print(f"Running {len(applicable)} check validators...")

        results = _run_checks_for_workspace(
            workspace_id=ws_id,
            workspace_name=ws_name,
            workspace_url=ws_url,
            config=config,
            tp=tp,
            acct_rest=acct_rest,
            sql=sql,
            check_defs=check_defs,
            applicable=applicable,
            run_id=args.run_id,
            api_only=args.api_only,
        )
        all_results[ws_id] = results

        # Per-workspace report
        output_path = os.path.join(
            REPO_ROOT, "tests", "automated", "reports",
            f"{args.cloud}_{ws_name}_run{rid}_report.md",
        )
        generate_report(results, f"{args.cloud} — {ws_name}", rid, output_path)
        _print_summary(results, ws_name, output_path)

    # Grand summary across all workspaces
    if len(workspaces) > 1:
        print(f"\n{'='*60}")
        print(f"GRAND SUMMARY (all {len(workspaces)} workspaces, run_id={rid})")
        print(f"{'='*60}")
        grand_agree = grand_disagree = grand_errors = grand_missing = 0
        for ws_id, results in all_results.items():
            ws_name = next(w["workspace_name"] for w in workspaces if w["workspace_id"] == ws_id)
            a = sum(1 for r in results if r.agreement == "AGREE")
            d = sum(1 for r in results if r.agreement == "DISAGREE")
            e = sum(1 for r in results if r.agreement == "API_ERROR")
            m = sum(1 for r in results if r.agreement == "SAT_MISSING")
            grand_agree += a
            grand_disagree += d
            grand_errors += e
            grand_missing += m
            print(f"  {ws_name:20s}  AGREE={a:2d}  DISAGREE={d}  API_ERROR={e}  SAT_MISSING={m}")

        print(f"  {'TOTAL':20s}  AGREE={grand_agree:2d}  DISAGREE={grand_disagree}  API_ERROR={grand_errors}  SAT_MISSING={grand_missing}")

        if grand_disagree > 0:
            print(f"\nAll discrepancies:")
            for ws_id, results in all_results.items():
                ws_name = next(w["workspace_name"] for w in workspaces if w["workspace_id"] == ws_id)
                for r in results:
                    if r.agreement == "DISAGREE":
                        print(f"  [{ws_name}] {r.check_id}: API={r.api_score}, SAT={r.sat_score} — {r.check_name}")


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
    parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Run validation across all workspaces in the account (from account_workspaces table)",
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
