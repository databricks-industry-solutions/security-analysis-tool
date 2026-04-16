"""Generate markdown validation reports from check results."""

from __future__ import annotations

import datetime
from pathlib import Path

from tests.automated.checks.base_validator import ValidationResult


def generate_report(
    results: list[ValidationResult],
    cloud: str,
    run_id: int,
    output_path: str,
) -> str:
    """Generate a markdown report from validation results.

    Returns the report text and writes it to output_path.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    agree = [r for r in results if r.agreement == "AGREE"]
    disagree = [r for r in results if r.agreement == "DISAGREE"]
    api_errors = [r for r in results if r.agreement == "API_ERROR"]
    missing = [r for r in results if r.agreement == "SAT_MISSING"]

    lines = [
        f"# SAT Validation Report - {cloud.upper()}",
        f"",
        f"**Generated:** {timestamp}  ",
        f"**SAT Run ID:** {run_id}  ",
        f"**Cloud:** {cloud}  ",
        f"**Total checks validated:** {len(results)}",
        "",
        "## Summary",
        "",
        "| Status | Count | Description |",
        "|--------|-------|-------------|",
        f"| AGREE | {len(agree)} | API ground truth matches SAT result |",
        f"| DISAGREE | {len(disagree)} | API and SAT disagree on pass/fail |",
        f"| SAT_MISSING | {len(missing)} | Check not found in SAT output for this run |",
        f"| API_ERROR | {len(api_errors)} | Could not call the API to verify |",
        f"| **Total** | **{len(results)}** | |",
        "",
    ]

    if disagree:
        lines.append("## Discrepancies")
        lines.append("")
        lines.append(
            "These checks have different results between the API ground truth "
            "and what SAT reported. Each entry includes the raw API evidence "
            "and SAT's stored result."
        )
        lines.append("")
        for r in sorted(disagree, key=lambda x: x.check_id):
            lines.append(f"### {r.check_id}: {r.check_name}")
            lines.append("")
            lines.append(f"- **Category:** {r.category}")
            lines.append(f"- **Severity:** {r.severity}")
            lines.append(
                f"- **API says:** score={r.api_score} "
                f"({'PASS' if r.api_score == 0 else 'FAIL'})"
            )
            lines.append(f"- **API details:** `{r.api_details}`")
            lines.append(
                f"- **SAT says:** score={r.sat_score} "
                f"({'PASS' if r.sat_score == 0 else 'FAIL'})"
            )
            lines.append(f"- **SAT details:** `{r.sat_details}`")
            lines.append("")
            lines.append("**Possible issue:** ")
            if r.api_score == 0 and r.sat_score and r.sat_score > 0:
                lines.append(
                    "SAT reports a violation but the API shows the configuration "
                    "is correct. This could indicate stale intermediate data, "
                    "a timing issue between data collection and analysis, or "
                    "a bug in the SAT check logic."
                )
            elif r.api_score > 0 and r.sat_score == 0:
                lines.append(
                    "SAT reports a pass but the API shows a violation. This could "
                    "indicate the check logic is not evaluating the correct field, "
                    "missing a condition, or the API response schema has changed."
                )
            lines.append("")

    if api_errors:
        lines.append("## API Errors")
        lines.append("")
        lines.append(
            "These checks could not be validated because the API call failed."
        )
        lines.append("")
        for r in sorted(api_errors, key=lambda x: x.check_id):
            lines.append(f"### {r.check_id}: {r.check_name}")
            lines.append(f"- **Error:** `{r.api_error}`")
            lines.append("")

    if missing:
        lines.append("## Missing from SAT Output")
        lines.append("")
        lines.append(
            "These checks have validators but no corresponding result was found "
            f"in the SAT `security_checks` table for run_id={run_id}."
        )
        lines.append("")
        for r in sorted(missing, key=lambda x: x.check_id):
            lines.append(f"- **{r.check_id}**: {r.check_name}")
        lines.append("")

    lines.append("## Full Results")
    lines.append("")
    lines.append(
        "| Check ID | Name | Category | Severity | API | SAT | Verdict |"
    )
    lines.append(
        "|----------|------|----------|----------|-----|-----|---------|"
    )
    for r in sorted(results, key=lambda x: x.check_id):
        api_str = (
            f"{'PASS' if r.api_score == 0 else 'FAIL'}"
            if r.api_error is None
            else "ERR"
        )
        sat_str = (
            f"{'PASS' if r.sat_score == 0 else 'FAIL'}"
            if r.sat_score is not None
            else "N/A"
        )
        lines.append(
            f"| {r.check_id} | {r.check_name} | {r.category} | "
            f"{r.severity} | {api_str} | {sat_str} | {r.agreement} |"
        )
    lines.append("")

    report = "\n".join(lines)

    # Write to file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)

    return report
