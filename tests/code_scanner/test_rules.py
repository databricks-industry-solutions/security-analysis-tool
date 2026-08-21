"""Ruleset tests for the Databricks Semgrep rules.

Two properties are enforced. Every rule must fire on the vulnerable fixture,
because a rule that never matches is dead weight that still costs scan time. And
no rule may fire on the safe fixture, because a scanner that reports correct code
as vulnerable stops being read.

The second property is the one that keeps regressing. An earlier version of the
SQL injection rule matched any f-string passed to spark.sql, which flags
spark.sql(f"OPTIMIZE {table}") -- safe, and common enough to bury the real
findings. Taint mode fixed it, and this test is what stops it coming back.

Run: python tests/code_scanner/test_rules.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
RULES = (
    Path(__file__).parents[2]
    / "notebooks/Includes/scan_code/rules/databricks-notebooks.yaml"
)

EXPECTED_RULES = {
    "databricks-widget-sql-injection",
    "databricks-secret-written-to-output",
    "databricks-tls-verification-disabled",
    "databricks-unsafe-deserialization-from-storage",
    "databricks-credential-in-spark-conf",
    "databricks-governed-data-to-unmanaged-path",
    "databricks-external-token-in-source",
}


def _run(*args: str) -> subprocess.CompletedProcess:
    binary = shutil.which("semgrep")
    if binary is None:
        sys.exit("semgrep is not on PATH; install it with: pip install semgrep")
    return subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        timeout=300,
        env={"SEMGREP_ENABLE_VERSION_CHECK": "0", "SEMGREP_SEND_METRICS": "off",
             "PATH": str(Path(binary).parent) + ":/usr/bin:/bin"},
    )


def _semgrep(*args: str) -> dict:
    result = _run(*args)
    if not result.stdout.strip():
        sys.exit(f"semgrep produced no output:\n{result.stderr[:2000]}")
    return json.loads(result.stdout)


def _scan(fixture: str) -> dict:
    return _semgrep(
        "scan", "--json", "--no-git-ignore", "--quiet",
        "--config", str(RULES), str(FIXTURES / fixture),
    )


def _rule_ids(report: dict) -> set[str]:
    return {r["check_id"].rsplit(".", 1)[-1] for r in report.get("results", [])}


def test_rules_are_valid() -> None:
    """Invalid rule YAML makes Semgrep report zero findings, which is
    indistinguishable from a clean scan. Validate explicitly.

    --validate reports on stderr and signals failure through its exit code, so
    neither can be ignored here.
    """
    result = _run("--validate", "--config", str(RULES))
    combined = result.stdout + result.stderr
    assert result.returncode == 0, f"invalid rules: {combined[:1000]}"
    assert "found 0 configuration error" in combined, combined[:1000]


def test_every_rule_fires() -> None:
    report = _scan("vulnerable.py")
    assert not report.get("errors"), f"scan errors: {report['errors']}"
    fired = _rule_ids(report)

    # The hardcoded-token rule needs a literal token to match, and committing one
    # would trip this repository's own secret scanner. Generate the sample in a
    # temporary file instead so the rule is still covered.
    with tempfile.TemporaryDirectory() as tmp:
        sample = Path(tmp) / "token_sample.py"
        sample.write_text("TOKEN = \"dapi" + "0123456789abcdef" * 2 + "\"\n")
        token_report = _semgrep(
            "scan", "--json", "--no-git-ignore", "--quiet",
            "--config", str(RULES), str(sample),
        )
    fired |= _rule_ids(token_report)

    missing = EXPECTED_RULES - fired
    assert not missing, f"rules that never matched: {sorted(missing)}"


def test_fingerprints_are_stable_and_distinct() -> None:
    """Findings must keep their identity when a notebook is edited, and separate
    occurrences of one rule must not collapse into a single finding."""
    sys.path.insert(0, str(Path(__file__).parents[2] / "notebooks/Includes/scan_code"))
    from runners import Finding

    shifted = [
        Finding("semgrep", "r", "HIGH", "t", "d", "/nb", line_start=n,
                matched_code="pickle.load(f)")
        for n in (5, 90)
    ]
    assert shifted[0].fingerprint == shifted[1].fingerprint, \
        "fingerprint changed when only the line number moved"

    distinct = Finding("semgrep", "r", "HIGH", "t", "d", "/nb", line_start=5,
                       matched_code="torch.load(p)")
    assert shifted[0].fingerprint != distinct.fingerprint, \
        "different statements produced the same fingerprint"


def test_no_false_positives() -> None:
    report = _scan("safe.py")
    findings = [
        f"{r['check_id'].rsplit('.', 1)[-1]} at line {r['start']['line']}"
        for r in report.get("results", [])
    ]
    assert not findings, f"correct code was flagged: {findings}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
