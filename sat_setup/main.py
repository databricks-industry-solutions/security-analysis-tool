import json
import os
import re
import subprocess

from databricks.sdk import WorkspaceClient
from inquirer import Confirm, List, Password, Text, list_input, prompt
from rich.progress import Progress, SpinnerColumn, TextColumn


def loading(func, message: str = "Loading..."):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.start()
        progress.add_task(description=message)
        res = func()
        progress.stop()

    return res


def cloud_validation(cloud):
    global cloud_type
    if "azure" in client.config.host:
        cloud_type = "azure"
    elif "gcp" in client.config.host:
        cloud_type = "gcp"
    else:
        cloud_type = "aws"

    if cloud_type == cloud:
        return False
    return True


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


def get_catalogs():
    valid_catalogs = []
    for c in client.catalogs.list():
        if c.catalog_type is not None and c.catalog_type.value != "SYSTEM_CATALOG":
            valid_catalogs.append(c.name)
    return valid_catalogs


def get_warehouses():
    valid_warehouses = []
    for w in client.warehouses.list():
        valid_warehouses.append({"name": w.name, "id": w.id})
    return valid_warehouses


def form():
    global client
    profile = list_input(
        message="Select profile",
        choices=loading(get_profiles, "Loading profiles..."),
    )
    client = WorkspaceClient(profile=profile)

    questions = [
        Text(
            name="account_id",
            message="Databricks Account ID",
            validate=lambda _, x: re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", x
            ),
        ),
        Confirm(
            name="enable_uc",
            message="Use Unity Catalog?",
            default=True,
        ),
        List(
            name="catalog",
            message="Select catalog",
            choices=loading(get_catalogs),
            ignore=lambda x: not x["enable_uc"],
        ),
        List(
            name="warehouse",
            message="Select warehouse",
            choices=loading(get_warehouses),
        ),
    ]
    questions = questions + cloud_specific_questions()
    return prompt(questions), profile


def cloud_specific_questions():
    azure = [
        Text(
            name="azure-tenant-id",
            message="Azure Tenant ID",
            ignore=cloud_validation("azure"),
        ),
        Text(
            name="azure-subscription-id",
            message="Azure Subscription ID",
            ignore=cloud_validation("azure"),
        ),
        Text(
            name="azure-client-id",
            message="Client ID",
            ignore=cloud_validation("azure"),
        ),
        Password(
            name="azure-client-secret",
            message="Client Secret",
            ignore=cloud_validation("azure"),
        ),
    ]
    gcp = [
        Text(
            name="gcp-gs-path-to-json",
            message="Path to JSON key file",
            ignore=cloud_validation("gcp"),
        ),
        Text(
            name="gcp-impersonate-service-account",
            message="Impersonate Service Account",
            ignore=cloud_validation("gcp"),
            default="",
        ),
    ]
    aws = [
        Text(
            name="aws-client-id",
            message="Client ID",
            ignore=cloud_validation("aws"),
        ),
        Password(
            name="aws-client-secret",
            message="Client Secret",
            ignore=cloud_validation("aws"),
        ),
    ]
    return aws + azure + gcp


def generate_secrets(answers: dict):

    scope_name = "sat_scope"
    for scope in client.secrets.list_scopes():
        if scope.name == scope_name:
            client.secrets.delete_scope(scope_name)
            break

    client.secrets.create_scope(scope_name)

    token = client.tokens.create(
        lifetime_seconds=86400 * 365,
        comment="Security Analysis Tool",
    )
    client.secrets.put_secret(
        scope=scope_name,
        key=f"sat-token-{client.get_workspace_id()}",
        string_value=token.token_value,
    )
    client.secrets.put_secret(
        scope=scope_name,
        key="account-console-id",
        string_value=answers["account_id"],
    )
    client.secrets.put_secret(
        scope=scope_name,
        key="sql-warehouse-id",
        string_value=answers["warehouse"]["id"],
    )

    if cloud_type == "aws":
        client.secrets.put_secret(
            scope=scope_name,
            key="use-sp-auth",
            string_value=True,
        )

    for value in answers.keys():
        if cloud_type in value:
            client.secrets.put_secret(
                scope=scope_name,
                key=value.replace(f"{cloud_type}-", ""),
                string_value=answers[value],
            )


def install(answers: dict, profile: str):
    generate_secrets(answers)
    config = {
        "catalog": profile,
        "cloud": cloud_type,
        "google_service_account": answers.get("gcp-impersonate-service-account", None),
    }

    config_file = "tmp_config.json"
    with open(config_file, "w") as fp:
        json.dump(config, fp)
    subprocess.call(f"sh ./setup.sh tmp {profile} {config_file}".split(" "))


def setup():
    try:
        answers, profile = form()
        install(answers, profile)
    except KeyboardInterrupt:
        print("Installation aborted.")


if __name__ == "__main__":
    os.system("clear")
    setup()
