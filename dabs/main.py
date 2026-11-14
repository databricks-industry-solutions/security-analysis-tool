import json
import os
import subprocess
import sys

from databricks.sdk import WorkspaceClient
from sat.repair import repair as repair_install


def install(client: WorkspaceClient, answers: dict, profile: str):
    """Deploy the app. The app is the source of truth for everything else:
    catalog/schema, account id, credentials (stored as Unity Catalog secrets),
    the Genie space and the collection jobs are all configured from the app's own
    setup flow after it is deployed."""
    warehouse_id = answers.get("warehouse", {}).get("id", None)

    config = {
        "enable_app": answers.get("enable_app", False),
        "warehouse_id": warehouse_id,
    }

    config_file = "tmp_config.json"
    with open(config_file, "w") as fp:
        json.dump(config, fp)

    os.system("clear")
    subprocess.call(f"sh ./setup.sh tmp {profile} {config_file}".split(" "))

    print("Installation complete.")
    print(f"Review workspace -> {client.config.host}")
    if answers.get("enable_app", False):
        print("The Security Analysis app is deployed. Open it from Compute -> Apps,")
        print("then complete the in-app setup: choose the catalog/schema, enter your")
        print("account id and credentials. The app stores the credentials as Unity")
        print("Catalog secrets and provisions its own collection jobs and Genie space.")


def run_repair():
    """Restore an existing installation without re-answering the install prompts.

    The warehouse is read back from the app's resource binding and the schema
    from the app's own config file, so a repair needs no input beyond the
    workspace profile. Set SAT_SCHEMA=<catalog>.<schema> to override the schema
    if the app's config file is no longer available.
    """
    from sat.repair import APP_NAME

    client = WorkspaceClient()

    # Warehouse id from the app's warehouse resource binding (survives an SP
    # deletion, unlike anything in the app service principal's home).
    warehouse_id = ""
    app_sp = None
    try:
        app = client.apps.get(name=APP_NAME)
        app_sp = app.service_principal_client_id
        for resource in (app.resources or []):
            wh = getattr(resource, "sql_warehouse", None)
            if wh and getattr(wh, "id", None):
                warehouse_id = wh.id
                break
    except Exception:  # noqa: BLE001
        pass

    # Schema from SAT_SCHEMA, else the app's own config file in the app service
    # principal's home.
    uc_schema = (os.environ.get("SAT_SCHEMA") or "").strip()
    if not uc_schema and app_sp:
        try:
            raw = client.workspace.download(
                f"/Users/{app_sp}/.sat/app_config.json").read()
            uc_schema = (json.loads(raw).get("schema") or "").strip()
        except Exception:  # noqa: BLE001
            uc_schema = ""

    if not uc_schema or not warehouse_id:
        print(
            "Could not determine the existing configuration automatically. Set "
            "SAT_SCHEMA=<catalog>.<schema> and make sure the app's SQL warehouse "
            "is bound, then re-run ./install.sh --repair. For a fresh installation "
            "run ./install.sh."
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
