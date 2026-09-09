'''Unit tests for Azure Entra vs Databricks-managed SP token selection.'''
from unittest.mock import patch

from core.dbclient import SatDBClient


def _azure_client(tenant_id='', subscription_id=''):
    return SatDBClient(
        {
            'url': 'https://adb-123.4.azuredatabricks.net',
            'workspace_id': '123',
            'account_id': 'acct-1',
            'clusterid': '0101-000000-unit',
            'verbosity': 'error',
            'client_id': 'client',
            'client_secret': 'secret',
            'tenant_id': tenant_id,
            'subscription_id': subscription_id,
        }
    )


def test_azure_without_tenant_uses_databricks_oidc():
    client = _azure_client(tenant_id='')
    assert client._azure_uses_entra() is False
    with patch.object(client, 'getAWSTokenwithOAuth', return_value='oidc-token') as oidc:
        with patch.object(client, 'getAzureTokenWithMSAL') as msal:
            token = client.getAzureToken(False, None, 'client', 'secret')
    assert token == 'oidc-token'
    oidc.assert_called_once_with(False, 'client', 'secret')
    msal.assert_not_called()


def test_azure_with_tenant_uses_msal():
    client = _azure_client(tenant_id='tenant-1')
    assert client._azure_uses_entra() is True
    with patch.object(client, 'getAzureTokenWithMSAL', return_value='msal-token') as msal:
        with patch.object(client, 'getAWSTokenwithOAuth') as oidc:
            token = client.getAzureToken(False, None, 'client', 'secret')
    assert token == 'msal-token'
    msal.assert_called_once_with('dbmgmt')
    oidc.assert_not_called()


def test_azure_without_tenant_rejects_management_api():
    client = _azure_client(tenant_id='')
    try:
        client.getAzureToken(
            True, 'workspaces?api-version=2018-04-01', 'client', 'secret'
        )
        assert False, 'expected Azure Management call to fail without tenant-id'
    except Exception as exc:
        assert 'Azure Management APIs require tenant-id' in str(exc)
