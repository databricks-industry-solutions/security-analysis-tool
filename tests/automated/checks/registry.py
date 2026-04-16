"""Check registry and CSV loading for the SAT test framework."""

from __future__ import annotations

import csv
from typing import Optional

from tests.automated.checks.base_validator import BaseValidator

# Map of check db_id -> validator class
VALIDATOR_MAP: dict[str, type[BaseValidator]] = {}


def register(check_db_id: str):
    """Decorator to register a validator class for a check db_id."""

    def decorator(cls: type[BaseValidator]) -> type[BaseValidator]:
        cls.CHECK_DB_ID = check_db_id
        VALIDATOR_MAP[check_db_id] = cls
        return cls

    return decorator


class CheckDefinition:
    """One row from security_best_practices.csv."""

    def __init__(self, row: dict):
        self.id = row["id"]
        self.check_id = row["check_id"]
        self.category = row["category"]
        self.check = row["check"]
        self.evaluation_value = row["evaluation_value"]
        self.severity = row["severity"]
        self.logic = row.get("logic", "")
        self.api = row.get("api", "")
        self.enabled = row.get("enable", "1") == "1"
        self.clouds: list[str] = []
        if row.get("aws") == "1":
            self.clouds.append("aws")
        if row.get("azure") == "1":
            self.clouds.append("azure")
        if row.get("gcp") == "1":
            self.clouds.append("gcp")


def load_check_definitions(csv_path: str) -> dict[str, CheckDefinition]:
    """Load all check definitions from CSV, keyed by id."""
    checks: dict[str, CheckDefinition] = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            defn = CheckDefinition(row)
            checks[defn.id] = defn
    return checks


def get_validator(check_db_id: str) -> Optional[type[BaseValidator]]:
    """Look up the validator class for a given check db_id."""
    return VALIDATOR_MAP.get(check_db_id)
