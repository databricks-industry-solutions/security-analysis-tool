import json
import os
import subprocess
import sys

from databricks.sdk import WorkspaceClient
from sat.repair import repair as repair_install
from sat.utils import cloud_type


def install(client: WorkspaceClient, answers: dict, profile: str):
    from sat.config import generate_secrets, record_job_ids
    from sat.genie import create_or_update_space

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


def run_repair():
    """Restore an existing installation without re-answering the install prompts.

    Reads the configuration back from the secret scope the installer wrote, so a
    repair needs no input beyond the workspace profile. This is the recovery path
    for a deleted app service principal, which cannot be fixed in place.
    """
    import base64

    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()

    def read(key, default=""):
        try:
            got = client.secrets.get_secret(scope="sat_scope", key=key)
            return base64.b64decode(got.value or "").decode().strip()
        except Exception:  # noqa: BLE001
            return default

    uc_schema = read("analysis_schema_name")
    warehouse_id = read("sql-warehouse-id")
    if not uc_schema or not warehouse_id:
        print(
            "Could not read the existing configuration from the sat_scope secret "
            "scope, so there is nothing to repair. Run ./install.sh for a fresh "
            "installation."
        )
        return False

    # Schema owner. A schema owned by an individual service principal is left
    # ownerless if that principal is deleted, which is what turned this outage
    # into a manual repair -- so an SP is never used. Prefer an explicit
    # SAT_SCHEMA_OWNER (intended to be a group), otherwise the human running the
    # repair, and otherwise leave ownership untouched.
    owner = (os.environ.get("SAT_SCHEMA_OWNER") or "").strip() or None
    if not owner:
        try:
            me = client.current_user.me()
            candidate = me.user_name or ""
            # Service principals have no email-style user_name; only take an
            # address, so a repair run under an SP does not re-create the problem.
            owner = candidate if "@" in candidate else None
        except Exception:  # noqa: BLE001
            owner = None
    if not owner:
        print(
            "  Note: could not determine a durable schema owner, so ownership is "
            "left unchanged. Set SAT_SCHEMA_OWNER to a group to make this robust."
        )

    print(f"Repairing the SAT installation in {client.config.host}")
    print(f"  schema    : {uc_schema}")
    print(f"  warehouse : {warehouse_id}")
    print()
    return repair_install(
        client,
        profile="",
        uc_schema=uc_schema,
        warehouse_id=warehouse_id,
        owner=owner,
        source_code_path="/Workspace/Applications/SAT/files/app/security-analysis-tool",
    )


def setup():
    try:
        if "--repair" in sys.argv:
            ok = run_repair()
            sys.exit(0 if ok else 1)
        from sat.config import form

        client, answers, profile = form()
        install(client, answers, profile)
    except KeyboardInterrupt:
        print("Installation aborted.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    os.system("clear")
    setup()
