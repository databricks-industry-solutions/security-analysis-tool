import json
import os
import re
import subprocess

from databricks.sdk import WorkspaceClient
from inquirer import Confirm, List, Password, Text, list_input, prompt
from rich.progress import Progress, SpinnerColumn, TextColumn


def loading(func, message: str = "Loading...", client: WorkspaceClient = None):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.start()
        progress.add_task(description=message)
        if client is None:
            res = func()
        else:
            res = func(client)
        progress.stop()

    return res


def cloud_validation(client, cloud):
    cloud_type = None
    if "azure" in client.config.host:
        cloud_type = "azure"
    elif "gcp" in client.config.host:
        cloud_type = "gcp"
    else:
        cloud_type = "aws"

    if cloud_type == cloud:
        return False
    return True


def cloud_type(client: WorkspaceClient):
    if "azure" in client.config.host:
        return "azure"
    elif "gcp" in client.config.host:
        return "gcp"
    else:
        return "aws"


def databricks_command(commmand: str):
    return json.loads(
        subprocess.run(
            commmand.split(" "),
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def get_profiles():
    output = databricks_command("databricks auth profiles -o json")["profiles"]
    valid_profiles = []
    for p in output:
        if p["valid"] and "accounts" not in p["host"]:
            valid_profiles.append(p["name"])
    return valid_profiles


def get_catalogs(client: WorkspaceClient):
    if uc_enabled(client) is False:
        return []
    valid_catalogs = []
    for c in client.catalogs.list():
        if c.catalog_type is not None and c.catalog_type.value != "SYSTEM_CATALOG":
            valid_catalogs.append(c.name)
    return valid_catalogs


def get_warehouses(client: WorkspaceClient):
    valid_warehouses = []
    for w in client.warehouses.list():
        valid_warehouses.append({"name": w.name, "id": w.id})
    return valid_warehouses


def uc_enabled(client: WorkspaceClient):
    try:
        client.metastores.current()
        return True
    except:
        return False
