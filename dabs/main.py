import json
import os
import subprocess

from databricks.sdk import WorkspaceClient
from sat.config import (
    build_secret_key_names,
    form,
    generate_secrets,
    validate_secrets,
    _resolve_app_config_scope,
    _resolve_key_overrides,
)
from sat.utils import cloud_type


def install(client: WorkspaceClient, answers: dict, profile: str):
    cloud = cloud_type(client)
    manage = answers.get("manage_secrets", True)

    # Build the structured key-name dict from checkbox + key-name prompt answers
    # and store it back into answers so _resolve_key_overrides() finds it.
    key_names_dict = build_secret_key_names(answers, cloud)
    answers["secret_key_names_dict"] = key_names_dict

    if manage:
        generate_secrets(client, answers, cloud)
    else:
        # Validate that the pre-existing scope has all required keys before
        # deploying the bundle — fail early with a clear message if not.
        validate_secrets(client, answers, cloud)

    scope_name = answers.get("secret_scope", "sat_scope") or "sat_scope"

    # Resolve the app config scope using the same logic as config.py so both
    # the DABS template and the installer write to the same scope.
    app_config_scope = _resolve_app_config_scope(answers, scope_name, manage)

    scope_contains = answers.get("scope_contains") or []

    def _param(logical, value):
        """Return blank when the value lives in the user's scope so that
        initialize.py falls back to reading it from there.  Pass the typed
        value otherwise so new installs work without a scope for these fields.
        """
        return "" if logical in scope_contains else (value or "")

    # Resolve non-secret config values to pass as job base_parameters.
    schema_deferred = "analysis_schema_name" in scope_contains
    analysis_schema_name = (
        ""  # initialize.py resolver reads from scope
        if schema_deferred
        else f'`{answers["catalog"]}`.{answers["security_analysis_schema"]}'
    )
    # Resolved physical key name for the analysis_schema_name app resource
    # binding in the bundle template ({{.analysis_schema_key}}).
    analysis_schema_key = key_names_dict.get("analysis_schema_name", "analysis_schema_name")

    proxies_json = "{}"
    if answers.get("use_proxy"):
        proxies_json = json.dumps({
            "http": answers.get("http", ""),
            "https": answers.get("https", ""),
        })
    elif "proxies" in scope_contains:
        proxies_json = ""

    use_sp_auth = "true" if cloud in ("aws", "gcp") else "false"

    config = {
        "catalog": "" if schema_deferred else answers.get("catalog", None),
        "cloud": cloud,
        "latest_lts": client.clusters.select_spark_version(
            long_term_support=True,
            latest=True,
        ),
        "node_type": client.clusters.select_node_type(
            local_disk=True,
            min_cores=4,
            gb_per_core=8,
            photon_driver_capable=True,
            photon_worker_capable=True,
        ),
        "serverless": answers.get("enable_serverless", False),
        "driver_schedule": answers.get("driver_schedule", "0 0 8 * * ?"),
        "secrets_scanner_schedule": answers.get("secrets_scanner_schedule", "0 0 8 * * ?"),
        "job_timezone": answers.get("job_timezone", "UTC"),
        "enable_brickhound": answers.get("enable_brickhound", False),
        "brickhound_schedule": answers.get("brickhound_schedule", "0 0 2 * * ?"),
        "warehouse_id": answers.get("warehouse", {}).get("id", None),
        # BYO scope / key-name config
        "secret_scope": scope_name,
        "secret_key_names": json.dumps(key_names_dict) if key_names_dict else "",
        "app_config_scope": app_config_scope,
        # Physical key used for the app resource binding (may differ from default).
        "analysis_schema_key": analysis_schema_key,
        # Non-secret config values: blank when deferred to the scope.
        "account_id":              _param("account_id",           answers.get("account_id", "")),
        "client_id":               _param("client_id",            _resolve_cloud_answer(answers, cloud, "client-id")),
        "tenant_id":               _param("tenant_id",            answers.get("azure-tenant-id", "")),
        "subscription_id":         _param("subscription_id",      answers.get("azure-subscription-id", "")),
        "sql_warehouse_id":        answers.get("warehouse", {}).get("id", ""),
        "analysis_schema_name":    analysis_schema_name,
        "proxies":                 proxies_json,
        "use_sp_auth":             use_sp_auth,
    }

    config_file = "tmp_config.json"
    with open(config_file, "w") as fp:
        json.dump(config, fp)

    os.system("clear")
    subprocess.call(f"sh ./setup.sh tmp {profile} {config_file}".split(" "))
    print("Installation complete.")
    print(f"Review workspace -> {client.config.host}")


def _resolve_cloud_answer(answers: dict, cloud: str, suffix: str) -> str:
    """Return the cloud-prefixed answer or empty string if not present."""
    key = f"{cloud}-{suffix}"
    return answers.get(key, "") or ""


def setup():
    try:
        client, answers, profile = form()
        install(client, answers, profile)
    except KeyboardInterrupt:
        print("Installation aborted.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    os.system("clear")
    setup()
