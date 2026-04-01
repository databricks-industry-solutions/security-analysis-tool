"""Lightweight REST client for Databricks APIs. No SDK dependency."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests


class AccountAPIForbiddenError(Exception):
    """Raised when account-level API returns 403 (SP lacks external access)."""


class FeatureDisabledError(Exception):
    """Raised when a workspace feature is disabled (e.g., PAT tokens)."""


class DatabricksRestClient:
    """Stateless HTTP client — takes a token per call.

    Includes proactive throttling (delay between calls) and reactive retry
    (exponential backoff on 429) to avoid rate limits.
    """

    MAX_RETRIES = 5
    RETRY_BACKOFF = [2, 4, 8, 16, 30]  # seconds — generous backoff
    CALL_DELAY = 0.5  # seconds between every API call to stay under rate limits

    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._last_call_time: float = 0

    def _throttle(self):
        """Enforce minimum delay between API calls."""
        now = time.time()
        elapsed = now - self._last_call_time
        if elapsed < self.CALL_DELAY:
            time.sleep(self.CALL_DELAY - elapsed)
        self._last_call_time = time.time()

    def _request(self, method: str, url: str, token: str, **kwargs) -> dict:
        """Execute an HTTP request with throttling and retry on 429."""
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "sat-test-framework/1.0",
        }
        for attempt in range(self.MAX_RETRIES + 1):
            self._throttle()
            resp = requests.request(
                method, url, headers=headers, timeout=self.timeout, **kwargs
            )

            # Retry on 429 Too Many Requests with exponential backoff
            if resp.status_code == 429 and attempt < self.MAX_RETRIES:
                # Use Retry-After header if provided, otherwise use backoff table
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = self.RETRY_BACKOFF[attempt]
                time.sleep(wait)
                continue

            # Retry on 503 Service Unavailable (transient)
            if resp.status_code == 503 and attempt < self.MAX_RETRIES:
                time.sleep(self.RETRY_BACKOFF[attempt])
                continue

            # Raise specific errors for known conditions
            if resp.status_code == 403:
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                msg = body.get("message", resp.text[:200])
                raise AccountAPIForbiddenError(f"403 Forbidden: {msg}")

            if resp.status_code == 404:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                if body.get("error_code") == "FEATURE_DISABLED":
                    raise FeatureDisabledError(body.get("message", "Feature disabled"))

            resp.raise_for_status()
            return resp.json()

        # Exhausted retries
        resp.raise_for_status()
        return resp.json()

    def get(
        self,
        path: str,
        token: str,
        params: Optional[dict] = None,
        version: str = "2.0",
    ) -> dict:
        url = f"{self.base_url}/api/{version}{path}"
        return self._request("GET", url, token, params=params)

    def post(
        self,
        path: str,
        token: str,
        json_body: Optional[dict] = None,
        version: str = "2.0",
    ) -> dict:
        url = f"{self.base_url}/api/{version}{path}"
        return self._request("POST", url, token, json=json_body)

    def get_all_pages(
        self,
        path: str,
        token: str,
        list_key: str,
        version: str = "2.0",
        params: Optional[dict] = None,
        max_pages: int = 100,
    ) -> list[dict]:
        """Paginate through results using next_page_token.

        Adds a 1-second pause between pages to stay well within rate limits.
        """
        all_items: list[dict] = []
        params = dict(params) if params else {}
        page = 0
        while page < max_pages:
            resp = self.get(path, token, params=params, version=version)
            items = resp.get(list_key, [])
            all_items.extend(items)
            npt = resp.get("next_page_token")
            if not npt:
                break
            params["page_token"] = npt
            page += 1
            time.sleep(1)  # extra pause between pages
        return all_items
