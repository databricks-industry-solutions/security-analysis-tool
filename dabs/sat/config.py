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
    uc_enabled,
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
        List(
            name="catalog",
            message="Select catalog",
            choices=loading(get_catalogs, client=client),
        ),
        Text(
            name="security_analysis_schema",
            message="Schema name for SAT",
            default="security_analysis",
        ),
        Confirm(
            name="enable_serverless",
            message="Run collection jobs on serverless compute?",
            default=True,
        ),
        List(
            name="warehouse",
            message="Select warehouse",
            choices=loading(get_warehouses, client=client),
        ),
    ]
    proxies = [
        Confirm(
            name="use_proxy",
            message="Want to use a proxy?",
            default=False,
        ),
        Text(
            name="http",
            message="HTTP Proxy",
            ignore=lambda x: not x["use_proxy"],
            default="",
        ),
        Text(
            name="https",
            message="HTTPS Proxy",
            ignore=lambda x: not x["use_proxy"],
            default="",
        ),
    ]

    # Collection schedules. SAT now collects two datasets: the permissions graph
    # and hardcoded-secret scan results.
    scheduling = [
        Text(
            name="secrets_scanner_schedule",
            message="Secret scanning schedule (Quartz cron expression)",
            default="0 0 8 ? * *",
        ),
        Text(
            name="job_timezone",
            message="Job schedule timezone (IANA timezone ID)",
            default="UTC",
        ),
    ]

    # Permissions analysis is a core dataset, not an add-on.
    permissions = [
        Text(
            name="brickhound_schedule",
            message="Permissions analysis schedule (Quartz cron expression)",
            default="0 0 2 ? * *",
        ),
    ]

    # The app surfaces both datasets and hosts the security assistant. The Genie
    # space it uses is created by this installer; nothing to set up by hand.
    application = [
        Confirm(
            name="enable_app",
            message="Deploy the Security Analysis app (dashboards + assistant)?",
            default=True,
        ),
        Text(
            name="model_endpoint",
            message="Model serving endpoint for the assistant",
            default="databricks-claude-opus-4-7",
            ignore=lambda x: not x.get("enable_app", False),
        ),
        Confirm(
            name="enable_genie",
            message="Create the Genie space for natural-language queries?",
            default=True,
            ignore=lambda x: not x.get("enable_app", False),
        ),
    ]

    # Genie Space Configuration
    genie = [
        Confirm(
            name="enable_genie_space",
            message="Create a SAT Genie space for natural-language queries over findings?",
            default=True,
        ),
    ]

    questions = (
        questions
        + cloud_specific_questions(client)
        + proxies
        + scheduling
        + permissions
        + application
    ) + genie
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
            echo="",
        ),
    ]
    gcp = [
        Text(
            name="gcp-client-id",
            message="Client ID",
            ignore=cloud_validation(client, "gcp"),
        ),
        Password(
            name="gcp-client-secret",
            message="Client Secret",
            ignore=cloud_validation(client, "gcp"),
            echo="",
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
            echo="",
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
    client.secrets.put_secret(
        scope=scope_name,
        key="analysis_schema_name",
        string_value=f'`{answers["catalog"]}`.{answers["security_analysis_schema"]}',
    )

    # Workspace id, used by the app to scope audit-log queries by default.
    try:
        client.secrets.put_secret(
            scope=scope_name,
            key="workspace-id",
            string_value=str(client.get_workspace_id()),
        )
    except Exception:  # noqa: BLE001
        # Non-fatal: the app falls back to resolving this at runtime.
        pass

    if answers.get("enable_app", False):
        client.secrets.put_secret(
            scope=scope_name,
            key="model-endpoint",
            string_value=answers.get("model_endpoint", "databricks-claude-opus-4-7"),
        )

    if answers["use_proxy"]:
        client.secrets.put_secret(
            scope=scope_name,
            key="proxies",
            string_value=json.dumps(
                {
                    "http": answers["http"],
                    "https": answers["https"],
                }
            ),
        )
    else:
        client.secrets.put_secret(
            scope=scope_name,
            key="proxies",
            string_value="{}",
        )

    client.secrets.put_secret(
        scope=scope_name,
        key="enable-genie-space",
        string_value="true" if answers.get("enable_genie_space", False) else "false",
    )

    if cloud_type == "aws" or cloud_type == "gcp":
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
