from databricks.sdk import WorkspaceClient
from inquirer import Confirm, List, list_input, prompt

from sat.utils import (
    get_profiles,
    get_warehouses,
    loading,
)


def form():
    """Collect the minimum needed to deploy the app.

    The app is the source of truth for everything else: catalog/schema, account
    id, credentials, the Genie space and the collection jobs are all configured
    from the app's own setup flow after it is deployed (credentials are stored as
    Unity Catalog secrets). So the installer only needs a profile and the SQL
    warehouse to bind to the app.
    """
    profile = list_input(
        message="Select profile",
        choices=loading(get_profiles, "Loading profiles..."),
    )
    client = WorkspaceClient(profile=profile)
    questions = [
        List(
            name="warehouse",
            message="Select the SQL warehouse the app will use",
            choices=loading(get_warehouses, client=client),
        ),
        Confirm(
            name="enable_app",
            message="Deploy the Security Analysis app?",
            default=True,
        ),
    ]
    return client, prompt(questions), profile
