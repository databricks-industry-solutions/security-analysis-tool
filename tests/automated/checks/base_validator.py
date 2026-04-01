"""Base validator class and result dataclass for SAT check validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from tests.automated.auth.token_provider import TokenProvider
from tests.automated.clients.rest_client import (
    AccountAPIForbiddenError,
    DatabricksRestClient,
    FeatureDisabledError,
)
from tests.automated.config.credentials import CloudConfig


@dataclass
class ValidationResult:
    """Result of validating one SAT check."""

    check_id: str  # e.g. "DP-2"
    check_db_id: str  # e.g. "2" (numeric id from CSV)
    check_name: str  # human-readable name
    cloud: str  # "aws" | "azure" | "gcp"
    category: str  # "Data Protection", "Governance", etc.
    severity: str  # "Low", "Medium", "High", "Critical"
    # Ground truth from direct API call
    api_score: int = 0
    api_details: dict = field(default_factory=dict)
    api_error: Optional[str] = None
    # SAT's reported result
    sat_score: Optional[int] = None
    sat_details: Optional[dict] = None
    sat_error: Optional[str] = None

    @property
    def agreement(self) -> str:
        if self.api_error:
            return "API_ERROR"
        if self.sat_error:
            return "SAT_MISSING"
        if self.sat_score is None:
            return "SAT_MISSING"
        # Binary comparison: both 0 = agree pass, both >0 = agree fail
        api_pass = self.api_score == 0
        sat_pass = self.sat_score == 0
        if api_pass == sat_pass:
            return "AGREE"
        return "DISAGREE"


class BaseValidator(ABC):
    """Abstract validator that every check must implement."""

    CHECK_DB_ID: str = ""
    CHECK_ID: str = ""
    CHECK_NAME: str = ""
    CLOUDS: list[str] = []

    def __init__(
        self,
        config: CloudConfig,
        token_provider: TokenProvider,
        rest_client: DatabricksRestClient,
        account_rest_client: Optional[DatabricksRestClient] = None,
    ):
        self.config = config
        self.token_provider = token_provider
        self.rest = rest_client
        self.account_rest = account_rest_client

    @abstractmethod
    def evaluate_from_api(self) -> tuple[int, dict]:
        """Call REST API directly and return (score, details).

        score: 0 = pass, 1 = fail
        details: evidence dict with raw API data
        """

    def validate(self, sat_result: Optional[dict]) -> ValidationResult:
        """Run the full validation: API check + compare with SAT."""
        api_score, api_details, api_error = 0, {}, None
        try:
            api_score, api_details = self.evaluate_from_api()
        except AccountAPIForbiddenError as e:
            api_error = f"ACCOUNT_API_FORBIDDEN: {e}"
        except FeatureDisabledError as e:
            api_error = f"FEATURE_DISABLED: {e}"
        except Exception as e:
            api_error = f"{type(e).__name__}: {e}"

        sat_score, sat_details, sat_error = None, None, None
        if sat_result:
            try:
                score_val = sat_result.get("score")
                sat_score = int(score_val) if score_val is not None else None
                sat_details = sat_result.get("additional_details", {})
            except Exception as e:
                sat_error = f"Error parsing SAT result: {e}"
        else:
            sat_error = "No SAT result found for this check in the specified run"

        return ValidationResult(
            check_id=self.CHECK_ID,
            check_db_id=self.CHECK_DB_ID,
            check_name=self.CHECK_NAME,
            cloud=self.config.cloud,
            category="",
            severity="",
            api_score=api_score,
            api_details=api_details,
            api_error=api_error,
            sat_score=sat_score,
            sat_details=sat_details,
            sat_error=sat_error,
        )
