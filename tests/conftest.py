import pytest
import os
import logging
from databricks.sdk import WorkspaceClient

@pytest.fixture(scope='session')
def logger():
    logger = logging.getLogger('pytest_logger')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(ch)

    return logger

@pytest.fixture(scope='session')
def databricks_client():
    """
    Fixture to create a Databricks client that can be used across test sessions.
    Configure your Databricks host and token as environment variables or directly in the code.
    """
    # Configure the Databricks client. You can also use environment variables.
    databricks_host = os.environ.get("DATABRICKS_HOST")
    databricks_token = os.environ.get("DATABRICKS_TOKEN")

    # Create a Databricks client instance
    client = WorkspaceClient(
        host=databricks_host,
        token=databricks_token
    )

    yield client

