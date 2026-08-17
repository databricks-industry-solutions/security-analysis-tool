import json
import os
import subprocess

from databricks.sdk import WorkspaceClient
from sat.config import form, generate_secrets, record_job_ids
from sat.genie import create_or_update_space
from sat.utils import cloud_type


def install(client: WorkspaceClient, answers: dict, profile: str):
    cloud = cloud_type(client)
    generate_secrets(client, answers, cloud)

    warehouse_id = answers.get("warehouse", {}).get("id", None)
    uc_schema = f'{answers["catalog"]}.{answers["security_analysis_schema"]}'

    # Provision the Genie space here rather than in a notebook, so installation
    # is a single command and the customer never opens the Genie UI. Idempotent:
    # an existing space is updated in place, keeping the id already bound to the
    # app valid across re-installs.
    genie_space_id = ""
    if answers.get("enable_app", False) and answers.get("enable_genie", False):
        print("Creating Genie space for the security assistant...")
        genie_space_id = (
            create_or_update_space(
                client,
                uc_schema=uc_schema,
                warehouse_id=warehouse_id,
                parent_path="/Applications/SAT/genie",
            )
            or ""
        )

    # Bind the id even when empty: the app treats an unset value as "Genie tool
    # unavailable" and keeps working without it.
    client.secrets.put_secret(
        scope="sat_scope",
        key="genie-space-id",
        string_value=genie_space_id,
    )

    config = {
        "catalog": answers.get("catalog", None),
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
        # Serverless still selects the compute the collection jobs run on.
        "serverless": answers.get("enable_serverless", True),
        "secrets_scanner_schedule": answers.get("secrets_scanner_schedule", "0 0 8 ? * *"),
        "job_timezone": answers.get("job_timezone", "UTC"),
        # Permissions analysis is core now; the flag stays for template compatibility.
        "enable_brickhound": True,
        "brickhound_schedule": answers.get("brickhound_schedule", "0 0 2 ? * *"),
        "enable_app": answers.get("enable_app", False),
        "warehouse_id": warehouse_id,
    }

    config_file = "tmp_config.json"
    with open(config_file, "w") as fp:
        json.dump(config, fp)

    os.system("clear")
    subprocess.call(f"sh ./setup.sh tmp {profile} {config_file}".split(" "))

    # The bundle has now created the jobs, so their ids can be recorded. The app
    # reads these to enable its in-app run controls; the secrets were seeded empty
    # before the deploy because the app's resource bindings require the keys to
    # exist, and the ids were not known until now.
    unresolved = record_job_ids(client)
    if unresolved:
        print(
            "Note: could not record job ids for: " + ", ".join(unresolved) + ". "
            "Those collections will show as not connected in the app; re-running "
            "the installer will retry."
        )

    print("Installation complete.")
    print(f"Review workspace -> {client.config.host}")
    if answers.get("enable_app", False):
        print("The Security Analysis app is deployed. Open it from Compute -> Apps.")
        print(
            "Collection jobs run on the schedules above; you can also trigger "
            "them from within the app."
        )


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
