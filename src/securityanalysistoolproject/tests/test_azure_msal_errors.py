'''Unit tests for SatDBClient.getAzureTokenWithMSAL error handling; no workspace needed.'''
import sys
import types

import pytest

from core.dbclient import SatDBClient


def _client():
    client = SatDBClient.__new__(SatDBClient)
    client._cloud_type = 'azure'
    client._client_id = '00000000-0000-0000-0000-000000000001'
    client._client_secret = 'not-a-secret'
    client._tenant_id = '00000000-0000-0000-0000-000000000002'
    client._MGMTURL = 'https://management.azure.com'
    return client


def _fake_msal(monkeypatch, result=None, error=None):
    class App:
        def __init__(self, **kwargs):
            if error is not None:
                raise error

        def acquire_token_silent(self, scopes, account):
            return None

        def acquire_token_for_client(self, scopes):
            return result

    monkeypatch.setitem(sys.modules, 'msal', types.SimpleNamespace(ConfidentialClientApplication=App))


def test_returns_token(monkeypatch):
    _fake_msal(monkeypatch, result={'access_token': 'tok'})
    assert _client().getAzureTokenWithMSAL('dbmgmt') == 'tok'


def test_rejected_request_raises_entra_error(monkeypatch):
    _fake_msal(monkeypatch, result={
        'error': 'invalid_client',
        'error_description': 'AADSTS7000215: Invalid client secret provided.',
        'correlation_id': 'abc-123',
    })
    with pytest.raises(Exception) as excinfo:
        _client().getAzureTokenWithMSAL('dbmgmt')
    message = str(excinfo.value)
    assert 'invalid_client' in message
    assert 'AADSTS7000215' in message
    assert 'abc-123' in message


def test_msal_exception_is_raised(monkeypatch):
    _fake_msal(monkeypatch, error=ValueError('Unable to get authority configuration'))
    with pytest.raises(ValueError, match='authority configuration'):
        _client().getAzureTokenWithMSAL('msmgmt')
