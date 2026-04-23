"""CSV health tests for configs/security_best_practices.csv.

These tests surface formatting / reference bugs that would otherwise escape
code review — e.g. unquoted commas inside the `logic` column that shift
every column after it, stale doc URLs that have been relocated, duplicate
`id` or `check_id` values.

Found during 0.8.0 verification:
  - GOV-21's `logic` field had unquoted commas, shifting `api` content into
    `azure_doc_url` and pushing a 3rd doc URL past the 16-column header.
  - DP-8's azure_doc_url chained through 3 Microsoft redirects to its
    current location; updated inline.

Run:
  pytest tests/automated/test_csv_health.py
  pytest tests/automated/test_csv_health.py -m 'not online'   # skip URL reachability
"""

from __future__ import annotations

import csv
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "configs" / "security_best_practices.csv"
URL_TIMEOUT_S = 15
URL_CONCURRENCY = 10
USER_AGENT = "Mozilla/5.0 (Macintosh)"


def _load_rows():
    with CSV_PATH.open() as f:
        return list(csv.DictReader(f))


def test_csv_ids_are_unique():
    seen: dict[str, int] = {}
    dups = []
    for i, row in enumerate(_load_rows(), start=2):  # +1 for 1-indexed +1 for header
        if row["id"] in seen:
            dups.append(f"id={row['id']} on rows {seen[row['id']]} and {i}")
        else:
            seen[row["id"]] = i
    assert not dups, "Duplicate id values:\n  " + "\n  ".join(dups)


def test_csv_check_ids_are_unique():
    seen: dict[str, int] = {}
    dups = []
    for i, row in enumerate(_load_rows(), start=2):
        if row["check_id"] in seen:
            dups.append(f"check_id={row['check_id']} on rows {seen[row['check_id']]} and {i}")
        else:
            seen[row["check_id"]] = i
    assert not dups, "Duplicate check_id values:\n  " + "\n  ".join(dups)


def test_csv_has_no_column_misalignment():
    """Each row must have exactly 16 fields matching the header."""
    with CSV_PATH.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        expected = len(header)
        bad = []
        for i, row in enumerate(reader, start=2):
            if len(row) != expected:
                bad.append(f"row {i} has {len(row)} fields (expected {expected})")
    assert not bad, "Column misalignment:\n  " + "\n  ".join(bad)


def _check_url(task):
    i, cid, col, url = task
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        urllib.request.urlopen(req, timeout=URL_TIMEOUT_S)
        return None
    except urllib.error.HTTPError as e:
        return f"row {i} [{cid}] {col}: HTTP {e.code} — {url}"
    except Exception as e:
        return f"row {i} [{cid}] {col}: {type(e).__name__} — {url}"


@pytest.mark.online
def test_csv_doc_urls_reachable():
    """Every non-blank doc URL returns a 2xx/3xx response.

    Gated with pytest marker `online` so CI environments without egress can
    skip: `pytest -m 'not online'`.
    """
    # Allow override from env — useful for CI secrets/flaky-network retries
    if os.environ.get("SAT_SKIP_URL_CHECK"):
        pytest.skip("SAT_SKIP_URL_CHECK set")

    tasks = []
    for i, row in enumerate(_load_rows(), start=2):
        for col in ("aws_doc_url", "azure_doc_url", "gcp_doc_url"):
            url = (row.get(col) or "").strip()
            if url and url != "N/A":
                tasks.append((i, row["check_id"], col, url))

    errors = []
    with ThreadPoolExecutor(max_workers=URL_CONCURRENCY) as ex:
        for result in ex.map(_check_url, tasks):
            if result:
                errors.append(result)

    assert not errors, (
        f"Unreachable doc URLs ({len(errors)} of {len(tasks)} total):\n  "
        + "\n  ".join(errors)
    )
