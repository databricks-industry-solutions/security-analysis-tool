import json
import os
import subprocess

from databricks.sdk import WorkspaceClient
from sat.config import form, generate_secrets
from sat.utils import cloud_type


def install(client: WorkspaceClient, answers: dict, profile: str):
    cloud = cloud_type(client)
    generate_secrets(client, answers, cloud)

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
        "serverless": answers.get("enable_serverless", False),
        "driver_schedule": answers.get("driver_schedule", "0 0 8 * * ?"),
        "secrets_scanner_schedule": answers.get("secrets_scanner_schedule", "0 0 8 * * ?"),
        "job_timezone": answers.get("job_timezone", "UTC"),
        "enable_brickhound": answers.get("enable_brickhound", False),
        "brickhound_schedule": answers.get("brickhound_schedule", "0 0 2 * * ?"),
    }

    config_file = "tmp_config.json"
    with open(config_file, "w") as fp:
        json.dump(config, fp)

    os.system("clear")
    subprocess.call(f"sh ./setup.sh tmp {profile} {config_file}".split(" "))
    print("Installation complete.")
    print(f"Review workspace -> {client.config.host}")


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
