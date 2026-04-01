"""Multi-cloud OAuth token acquisition for Databricks APIs.

Mirrors the authentication logic in src/.../core/dbclient.py but without
any dependency on the SAT SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import requests

from tests.automated.config.credentials import CloudConfig


class TokenProvider(ABC):
    """Abstract base for cloud-specific token acquisition."""

    def __init__(self, config: CloudConfig):
        self.config = config

    @abstractmethod
    def get_workspace_token(self) -> str:
        """Get OAuth token for workspace-level API calls."""

    @abstractmethod
    def get_account_token(self) -> str:
        """Get OAuth token for account-level API calls."""

    @staticmethod
    def create(config: CloudConfig) -> TokenProvider:
        if config.cloud == "aws":
            return AWSTokenProvider(config)
        elif config.cloud == "azure":
            return AzureTokenProvider(config)
        elif config.cloud == "gcp":
            return GCPTokenProvider(config)
        raise ValueError(f"Unknown cloud: {config.cloud}")


class _OAuthTokenProvider(TokenProvider):
    """Shared OAuth flow for AWS and GCP (client_credentials grant)."""

    def _get_token(self, endpoint: str) -> str:
        resp = requests.post(
            endpoint,
            auth=(self.config.client_id, self.config.client_secret),
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            headers={"User-Agent": "sat-test-framework/1.0"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def get_workspace_token(self) -> str:
        return self._get_token(f"{self.config.databricks_url}/oidc/v1/token")

    def get_account_token(self) -> str:
        acct_id = self.config.account_console_id
        return self._get_token(
            f"{self.config.accounts_url}/oidc/accounts/{acct_id}/v1/token"
        )


class AWSTokenProvider(_OAuthTokenProvider):
    pass


class GCPTokenProvider(_OAuthTokenProvider):
    pass


class AzureTokenProvider(TokenProvider):
    """Azure uses MSAL for token acquisition."""

    _DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"
    _MGMT_SCOPE = "https://management.azure.com/.default"

    def _get_msal_token(self, scopes: list[str]) -> str:
        import msal  # lazy import — not needed for AWS/GCP

        app = msal.ConfidentialClientApplication(
            client_id=self.config.client_id,
            client_credential=self.config.client_secret,
            authority=f"https://login.microsoftonline.com/{self.config.tenant_id}",
        )
        token = app.acquire_token_silent(scopes=scopes, account=None)
        if not token:
            token = app.acquire_token_for_client(scopes=scopes)
        if not token or "access_token" not in token:
            error = token.get("error_description", "unknown") if token else "unknown"
            raise RuntimeError(f"Azure MSAL token acquisition failed: {error}")
        return token["access_token"]

    def get_workspace_token(self) -> str:
        return self._get_msal_token([self._DATABRICKS_SCOPE])

    def get_account_token(self) -> str:
        return self._get_msal_token([self._DATABRICKS_SCOPE])

    def get_azure_mgmt_token(self) -> str:
        """For Azure Management API calls (subscription-level)."""
        return self._get_msal_token([self._MGMT_SCOPE])
