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
        Confirm(
            name="workspace_only",
            message="Skip Databricks account APIs? (registers this workspace)",
            default=False,
        ),
        Text(
            name="account_id",
            message="Databricks Account ID",
            ignore=lambda x: x.get("workspace_only", False),
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
            message="Run on serverless? [Only monitor current workspace]",
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

    # Job Scheduling Configuration
    scheduling = [
        Text(
            name="driver_schedule",
            message="Driver job schedule (Quartz cron expression)",
            default="0 0 8 ? * Mon,Wed,Fri",
        ),
        Text(
            name="secrets_scanner_schedule", 
            message="Secrets scanner job schedule (Quartz cron expression)",
            default="0 0 8 ? * *",
        ),
        Text(
            name="job_timezone",
            message="Job schedule timezone (IANA timezone ID)",
            default="UTC",
        ),
    ]

    # Permissions Analysis Configuration
    brickhound = [
        Confirm(
            name="enable_brickhound",
            message="Deploy Permissions Analysis?",
            default=True,
        ),
        Text(
            name="brickhound_schedule",
            message="Permissions Analysis schedule (Quartz cron expression)",
            default="0 0 2 ? * *",
            ignore=lambda x: not x.get("enable_brickhound", False),
        ),
    ]

    questions = questions + cloud_specific_questions(client) + proxies + scheduling + brickhound
    return client, prompt(questions), profile


def cloud_specific_questions(client: WorkspaceClient):
    skip_azure = cloud_validation(client, "azure")
    skip_gcp = cloud_validation(client, "gcp")
    skip_aws = cloud_validation(client, "aws")
    azure = [
        Confirm(
            name="azure_use_entra",
            message="Use Entra ID (tenant + subscription) so Azure GOV-3 can run?",
            default=False,
            ignore=lambda x: skip_azure or not x.get("workspace_only", False),
        ),
        Text(
            name="azure-tenant-id",
            message="Azure Tenant ID",
            ignore=lambda x: skip_azure
            or (
                x.get("workspace_only", False)
                and not x.get("azure_use_entra", False)
            ),
        ),
        Text(
            name="azure-subscription-id",
            message="Azure Subscription ID",
            ignore=lambda x: skip_azure
            or (
                x.get("workspace_only", False)
                and not x.get("azure_use_entra", False)
            ),
        ),
        Text(
            name="azure-client-id",
            message="Client ID",
            ignore=skip_azure,
        ),
        Password(
            name="azure-client-secret",
            message="Client Secret",
            ignore=skip_azure,
            echo="",
        ),
    ]
    gcp = [
        Text(
            name="gcp-client-id",
            message="Client ID",
            ignore=skip_gcp,
        ),
        Password(
            name="gcp-client-secret",
            message="Client Secret",
            ignore=skip_gcp,
            echo="",
        ),
    ]
    aws = [
        Text(
            name="aws-client-id",
            message="Client ID",
            ignore=skip_aws,
        ),
        Password(
            name="aws-client-secret",
            message="Client Secret",
            ignore=skip_aws,
            echo="",
        ),
    ]
    return aws + azure + gcp


def generate_secrets(client: WorkspaceClient, answers: dict, cloud_type: str):

    scope_name = "sat_scope"
    # Only create the scope if it doesn't already exist. Previous versions
    # deleted and recreated the scope on every install, which wiped ACLs —
    # including the READ ACL that Databricks Apps auto-creates when a
    # `secret` resource is bound to an app. That left re-installs with the
    # BrickHound app unable to resolve its `valueFrom` env vars and crashing
    # at startup. Overwriting individual keys with `put_secret` below
    # preserves existing ACLs.
    existing = {scope.name for scope in client.secrets.list_scopes()}
    if scope_name not in existing:
        client.secrets.create_scope(scope_name)

    workspace_only = bool(answers.get("workspace_only", False))
    client.secrets.put_secret(
        scope=scope_name,
        key="workspace-only-mode",
        string_value="true" if workspace_only else "false",
    )
    client.secrets.put_secret(
        scope=scope_name,
        key="account-console-id",
        string_value=answers.get("account_id") or "",
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

    if cloud_type == "aws" or cloud_type == "gcp":
        client.secrets.put_secret(
            scope=scope_name,
            key="use-sp-auth",
            string_value=True,
        )

    prefix = f"{cloud_type}-"
    for value in answers.keys():
        if value.startswith(prefix):
            client.secrets.put_secret(
                scope=scope_name,
                key=value.replace(prefix, "", 1),
                string_value=answers[value],
            )

    # Workspace-only without Entra: clear leftover tenant/subscription so SAT
    # uses a Databricks-managed SP instead of mixing with MSAL.
    if cloud_type == "azure" and workspace_only and not answers.get(
        "azure_use_entra", False
    ):
        client.secrets.put_secret(
            scope=scope_name, key="tenant-id", string_value=""
        )
        client.secrets.put_secret(
            scope=scope_name, key="subscription-id", string_value=""
        )
