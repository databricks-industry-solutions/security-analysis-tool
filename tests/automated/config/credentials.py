"""Parse terraform.tfvars files into CloudConfig dataclasses."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CloudConfig:
    """Connection details for one cloud deployment."""

    cloud: str  # "aws" | "azure" | "gcp"
    databricks_url: str
    workspace_id: str
    account_console_id: str
    client_id: str
    client_secret: str
    sqlw_id: str
    analysis_schema_name: str
    # Azure-only
    tenant_id: Optional[str] = None
    subscription_id: Optional[str] = None

    @property
    def accounts_url(self) -> str:
        urls = {
            "aws": "https://accounts.cloud.databricks.com",
            "azure": "https://accounts.azuredatabricks.net",
            "gcp": "https://accounts.gcp.databricks.com",
        }
        return urls[self.cloud]


def parse_tfvars(filepath: str) -> dict[str, str]:
    """Parse terraform.tfvars into key-value dict.

    Handles:
      key = "value"          (double-quoted)
      key = 'value'          (single-quoted)
      key = "value" // comment
      key = "value" # comment
    Ignores non-string values (booleans, maps, numbers).
    """
    result: dict[str, str] = {}
    with open(filepath) as f:
        for line in f:
            # Strip inline comments only outside quotes
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            # Match: key = "value"  with possible // or # trailing comment
            match = re.match(
                r'(\w+)\s*=\s*"([^"]*)"', stripped
            )
            if not match:
                match = re.match(r"(\w+)\s*=\s*'([^']*)'", stripped)
            if match:
                result[match.group(1)] = match.group(2)
    return result


def load_cloud_config(cloud: str, repo_root: str) -> CloudConfig:
    """Load CloudConfig from terraform/{cloud}/terraform.tfvars."""
    tfvars_path = Path(repo_root) / "terraform" / cloud / "terraform.tfvars"
    if not tfvars_path.exists():
        raise FileNotFoundError(f"tfvars not found: {tfvars_path}")
    tfvars = parse_tfvars(str(tfvars_path))
    return CloudConfig(
        cloud=cloud,
        databricks_url=tfvars["databricks_url"].rstrip("/"),
        workspace_id=tfvars["workspace_id"],
        account_console_id=tfvars["account_console_id"],
        client_id=tfvars["client_id"],
        client_secret=tfvars["client_secret"],
        sqlw_id=tfvars["sqlw_id"],
        analysis_schema_name=tfvars["analysis_schema_name"],
        tenant_id=tfvars.get("tenant_id"),
        subscription_id=tfvars.get("subscription_id"),
    )
