import json
import re
import subprocess

import inquirer
import sh
import typer
from databricks.sdk import WorkspaceClient
from inquirer.themes import GreenPassion
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer()


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


def prompt(questions: list):
    return inquirer.prompt(questions, theme=GreenPassion())


def get_profiles():
    output = json.loads(
        subprocess.run(
            "databricks auth profiles -o json".split(" "),
            capture_output=True,
            text=True,
        ).stdout.strip()
    )["profiles"]
    valid_profiles = []
    for p in output:
        if p["valid"] and "accounts" not in p["host"]:
            valid_profiles.append(p["name"])
    return valid_profiles


def get_warehouses():
    valid_warehouses = []
    for w in client.warehouses.list():
        valid_warehouses.append({"name": w.name, "id": w.id})
    # valid_warehouses.append("Create new warehouse...")
    return valid_warehouses


def get_catalogs():
    # TODO: search for catalogs for filtering
    valid_catalogs = []
    for c in client.catalogs.list():
        if c.catalog_type is not None and c.catalog_type.value != "SYSTEM_CATALOG":
            valid_catalogs.append(c.name)
    return valid_catalogs


def setup(profiles: list):
    questions = [
        inquirer.List(
            name="profile",
            message="Select Databricks profile",
            choices=profiles,
            default="default",
        ),
        inquirer.Text(
            name="account_id",
            message="Databricks Account ID",
            validate=lambda _, x: re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", x
            ),
        ),
        inquirer.Confirm(
            name="enable_uc",
            message="Use Unity Catalog?",
            default=True,
        ),
    ]
    return questions


def setupUC(catalogs: list, uc: bool):
    if uc:
        questions = [
            inquirer.List(
                name="catalog",
                message="Select catalog",
                choices=catalogs,
            ),
            inquirer.List(
                name="warehouse",
                message="Select warehouse",
                choices=get_warehouses(),
            ),
        ]
    else:
        questions = [
            inquirer.List(
                name="warehouse",
                message="Select warehouse",
                choices=get_warehouses(),
            ),
        ]
    return questions


def generate_secrets(data: dict, cloud_data: dict):

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
        string_value=data["account_id"],
    )
    client.secrets.put_secret(
        scope=scope_name,
        key="sql-warehouse-id",
        string_value=data["warehouse"]["id"],
    )

    if cloud_type == "aws":
        client.secrets.put_secret(
            scope=scope_name,
            key="use-sp-auth",
            string_value=True,
        )

    for value in cloud_data.keys():
        client.secrets.put_secret(
            scope=scope_name,
            key=value,
            string_value=cloud_data[value],
        )


def cloud_requirements():
    host = client.config.host
    global cloud_type
    if "azure" in host:
        cloud_type = "azure"
        questions = [
            inquirer.Text(
                name="tenant-id",
                message="Azure Tenant ID",
            ),
            inquirer.Text(
                name="subscription-id",
                message="Azure Subscription ID",
            ),
            inquirer.Text(
                name="client-id",
                message="Client ID",
            ),
            inquirer.Password(
                name="client-secret",
                message="Client Secret",
            ),
        ]
    elif "gcp" in host:
        cloud_type = "gcp"
        questions = [
            inquirer.Text(
                name="gs-path-to-json",
                message="Path to JSON key file",
            ),
            inquirer.Text(
                name="impersonate-service-account",
                message="Impersonate Service Account",
            ),
        ]
    else:
        cloud_type = "aws"
        questions = [
            inquirer.Text(
                name="client-id",
                message="Client ID",
            ),
            inquirer.Password(
                name="client-secret",
                message="Client Secret",
            ),
        ]

    return questions


def dabs(profile: str, catalog: str, cloud_type: str, gcp_sa: str):
    subprocess.call(
        ["sh", "./install.sh", "deployment", profile, catalog, cloud_type, gcp_sa]
    )


def install_sat(answers: dict, cloud_answers: dict):
    generate_secrets(data=answers, cloud_data=cloud_answers)
    gcp_sa = ""
    if cloud_answers.get("impersonate-service-account"):
        gcp_sa = cloud_answers["impersonate-service-account"]
    if answers.get("catalog"):
        dabs(answers["profile"], answers["catalog"], cloud_type, gcp_sa)
    else:
        dabs(answers["profile"], "hive_metastore", cloud_type, gcp_sa)


@app.command()
def migrate():
    typer.clear()
    typer.echo("Migrate to Unity Catalog")


@app.command()
def install():
    try:
        global client
        typer.clear()
        answers = prompt(setup(loading(get_profiles)))
        client = WorkspaceClient(profile=answers["profile"])
        answersUC = prompt(
            setupUC(loading(get_catalogs), answers["enable_uc"]),
        )
        cloud_answers = prompt(cloud_requirements())

        loading(
            lambda: install_sat(
                answers={**answers, **answersUC},
                cloud_answers=cloud_answers,
            ),
            message="Installing...",
        )
        typer.echo("Installation complete!")
    except Exception as e:
        typer.echo("Installation failed - Try again!")


if __name__ == "__main__":
    app()
