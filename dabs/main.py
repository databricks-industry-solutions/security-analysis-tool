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
        "google_service_account": answers.get("gcp-impersonate-service-account", None),
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
