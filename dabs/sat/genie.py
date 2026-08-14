"""
Genie space provisioning, performed by the installer.

Runs as part of ``dabs/main.py`` using the same authenticated client that creates
the secret scope, so the customer never has to open the Genie UI or run a
notebook. The resulting space_id is written to the SAT secret scope and bound
into the app's environment.

Idempotent: an existing space with the same title is reused, and its definition
updated in place, so re-running the installer does not accumulate spaces or
invalidate the id already bound to the app.
"""

from __future__ import annotations

import json
import os
from typing import Any

SPACE_TITLE = "Security Analysis Tool [SAT]"
SPACE_DESCRIPTION = (
    "Natural-language questions over the Databricks permissions graph and "
    "secret scanning results."
)

_TEMPLATE_RELATIVE = os.path.join("configs", "sat_genie_space_template.json")


def _repo_root() -> str:
    # dabs/sat/genie.py -> repo root is two directories up.
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_serialized_space(uc_schema: str) -> str:
    """Read the template, substitute the schema, and normalise ordering.

    The Genie export format requires tables and column configs to be sorted;
    an unsorted payload fails with an opaque 400, so sort here rather than
    relying on the template being maintained in order.
    """
    path = os.path.join(_repo_root(), _TEMPLATE_RELATIVE)
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    # analysis_schema_name is stored as `catalog`.schema; strip backticks so the
    # three-part identifiers in the template are clean UC names.
    raw = raw.replace("{UC_SCHEMA}", uc_schema.replace("`", ""))

    parsed = json.loads(raw)
    tables = parsed.get("data_sources", {}).get("tables", [])
    tables.sort(key=lambda t: t["identifier"])
    for table in tables:
        table.get("column_configs", []).sort(key=lambda c: c["column_name"])
    return json.dumps(parsed)


def _find_existing(client, title: str) -> str | None:
    """Return the space_id of a space with this title, if one exists."""
    page_token = None
    while True:
        try:
            resp = client.api_client.do(
                "GET",
                "/api/2.0/genie/spaces",
                query={"page_token": page_token} if page_token else None,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  Could not list Genie spaces: {exc}")
            return None

        for space in resp.get("spaces", []) or []:
            if space.get("title") == title:
                return space.get("space_id")

        page_token = resp.get("next_page_token")
        if not page_token:
            return None


def _ensure_parent_path(client, parent_path: str) -> bool:
    """Create the workspace folder the Genie space is stored under.

    The space is provisioned before the bundle deploys, so /Applications/SAT does
    not exist yet on a first install; the API rejects a parent_path whose tree
    node is missing. mkdirs is recursive and idempotent.
    """
    try:
        client.workspace.mkdirs(parent_path)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not create {parent_path}: {exc}")
        return False


def create_or_update_space(
    client,
    uc_schema: str,
    warehouse_id: str,
    parent_path: str | None = None,
) -> str | None:
    """Create the SAT Genie space, or update it if it already exists.

    Returns the space_id, or None if provisioning failed. A failure here is not
    fatal to installation — the app degrades to its structured views and reports
    the assistant's Genie tool as unconfigured.
    """
    try:
        serialized = _load_serialized_space(uc_schema)
    except (OSError, ValueError) as exc:
        print(f"  Could not read the Genie space template: {exc}")
        return None

    body: dict[str, Any] = {
        "title": SPACE_TITLE,
        "description": SPACE_DESCRIPTION,
        "serialized_space": serialized,
        "warehouse_id": warehouse_id,
    }
    # Only pass parent_path if the folder could be created; otherwise let the
    # workspace place the space at its default location rather than failing.
    if parent_path and _ensure_parent_path(client, parent_path):
        body["parent_path"] = parent_path

    existing_id = _find_existing(client, SPACE_TITLE)

    if existing_id:
        # Update in place so the id already bound to the app stays valid.
        try:
            client.api_client.do(
                "PATCH", f"/api/2.0/genie/spaces/{existing_id}", body=body
            )
            print(f"  Updated existing Genie space: {existing_id}")
            return existing_id
        except Exception as exc:  # noqa: BLE001
            print(f"  Could not update Genie space {existing_id}: {exc}")
            # Fall through and try creating a fresh one.

    try:
        created = client.api_client.do("POST", "/api/2.0/genie/spaces", body=body)
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not create the Genie space: {exc}")
        print("  The app will still work; the assistant's Genie tool stays disabled.")
        return None

    space_id = created.get("space_id")
    print(f"  Created Genie space: {space_id}")
    return space_id
