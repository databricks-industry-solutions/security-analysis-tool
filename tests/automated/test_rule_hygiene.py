"""Static hygiene lint for SAT check rules.

Each test here catches a bug class we actually hit during 0.8.0 / pre-0.8.0
verification. Failing the test at commit time is cheaper than discovering
it after a driver run misses violations.

Run:
    pytest tests/automated/test_rule_hygiene.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULE_FILES = [
    REPO / "notebooks" / "Includes" / "workspace_analysis.py",
    REPO / "notebooks" / "Includes" / "workspace_settings.py",
]


def test_rule_files_import_functions_as_F():
    """Any rule that uses F.col / F.regexp_replace / F.lit / etc. must have
    `from pyspark.sql import functions as F` at module scope.

    Background: seven rules (INFO-6, DP-2, IA-4, IA-6, token-3, UC-770, admin)
    used F.* without importing F. At rule-run time they raised
    `NameError: name 'F' is not defined`. sqlctrl's outer try/except
    swallowed the error, no row was written, and the workspace vanished
    from security_checks for that check across every run back to run 1.
    Fixed in commit eb990f3 by adding the import.
    """
    F_USAGE = re.compile(r"\bF\.(col|regexp_replace|lit|when|expr|concat|count|substring)\s*\(")
    F_IMPORT = re.compile(r"from\s+pyspark\.sql\s+import\s+functions\s+as\s+F")

    for path in RULE_FILES:
        src = path.read_text()
        if not F_USAGE.search(src):
            continue
        assert F_IMPORT.search(src), (
            f"{path.name}: uses F.col/F.regexp_replace/... but does not "
            f"import `from pyspark.sql import functions as F`. Every rule "
            f"that hits the F.* path will crash silently via NameError."
        )


def test_f_string_unions_over_intermediate_tables_are_guarded():
    """Rules that UNION two `<prefix>_{workspace_id}` intermediate tables must
    first call `spark.catalog.listTables(json_['intermediate_schema'])` and
    only include tables that exist.

    Background: `bootstrap()` skips writing a table when the source list is
    empty. UNION against a missing table raises AnalysisException, sqlctrl
    substitutes an empty df, the rule's `isEmpty(df) → violation` branch
    fires, and a false violation is recorded. See INFO-38 fix (commit
    9bea747). Also surfaces when a new check UNIONs multiple bootstrap
    tables without following the same pattern.
    """
    # Find UNION ... SELECT ... FROM {tbl_name_...} or similar f-string table
    # references. If any match, the surrounding 1500 chars must contain a
    # spark.catalog.listTables() call (the existence guard).
    UNION_FSTR_TABLE = re.compile(
        r"UNION(?:\s+ALL)?\s+\n?\s*SELECT\s+\*\s+FROM\s+\{[a-zA-Z_]\w*\}",
        re.IGNORECASE,
    )

    offenders: list[tuple[str, int]] = []
    for path in RULE_FILES:
        src = path.read_text()
        for m in UNION_FSTR_TABLE.finditer(src):
            window_start = max(0, m.start() - 1500)
            window = src[window_start : m.start()]
            if "listTables" not in window:
                line_no = src[: m.start()].count("\n") + 1
                offenders.append((path.name, line_no))

    assert not offenders, (
        "UNION across f-string bootstrap tables without a "
        "spark.catalog.listTables() guard — if one side's source is empty, "
        "bootstrap skips writing the table and the UNION fails:\n"
        + "\n".join(f"  {f}:{line}" for f, line in offenders)
    )
