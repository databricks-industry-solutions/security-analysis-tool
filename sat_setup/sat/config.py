import json
import os
import re
import subprocess

from databricks.sdk import WorkspaceClient
from inquirer import Confirm, List, Password, Text, list_input, prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from sat.utils import (
    cloud_validation,
    get_catalogs,
    get_profiles,
    get_warehouses,
    loading,
)


def form():
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
            choices=loading(get_catalogs, client=client),
            ignore=lambda x: not x["enable_uc"],
            default="hive_metastore",
        ),
        List(
            name="warehouse",
            message="Select warehouse",
            choices=loading(get_warehouses, client=client),
        ),
    ]
    questions = questions + cloud_specific_questions(client)
    return client, prompt(questions), profile


def cloud_specific_questions(client: WorkspaceClient):
    azure = [
        Text(
            name="azure-tenant-id",
            message="Azure Tenant ID",
            ignore=cloud_validation(client, "azure"),
        ),
        Text(
            name="azure-subscription-id",
            message="Azure Subscription ID",
            ignore=cloud_validation(client, "azure"),
        ),
        Text(
            name="azure-client-id",
            message="Client ID",
            ignore=cloud_validation(client, "azure"),
        ),
        Password(
            name="azure-client-secret",
            message="Client Secret",
            ignore=cloud_validation(client, "azure"),
        ),
    ]
    gcp = [
        Text(
            name="gcp-gs-path-to-json",
            message="Path to JSON key file",
            ignore=cloud_validation(client, "gcp"),
        ),
        Text(
            name="gcp-impersonate-service-account",
            message="Impersonate Service Account",
            ignore=cloud_validation(client, "gcp"),
            default="",
        ),
    ]
    aws = [
        Text(
            name="aws-client-id",
            message="Client ID",
            ignore=cloud_validation(client, "aws"),
        ),
        Password(
            name="aws-client-secret",
            message="Client Secret",
            ignore=cloud_validation(client, "aws"),
        ),
    ]
    return aws + azure + gcp


def generate_secrets(client: WorkspaceClient, answers: dict, cloud_type: str):

    scope_name = "sat_scope"
    for scope in client.secrets.list_scopes():
        if scope.name == scope_name:
            client.secrets.delete_scope(scope_name)
            break

    client.secrets.create_scope(scope_name)

    token = client.tokens.create(
        lifetime_seconds=86400 * 90,
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
