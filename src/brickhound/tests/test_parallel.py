"""Unit tests for brickhound.utils.parallel.collect_permission_edges."""

import threading
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from brickhound.utils.parallel import collect_permission_edges


def test_empty_object_specs_returns_empty_list():
    """An empty input list must return an empty edge list without touching the SDK."""
    mock_client = MagicMock()
    result = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="clusters",
        object_specs=[],
    )
    assert result == []
    mock_client.permissions.get.assert_not_called()


def _make_acl(user_name=None, group_name=None, sp_name=None, permission_levels=()):
    """Build a mock AccessControlList entry matching the SDK shape."""
    acl = MagicMock()
    acl.user_name = user_name
    acl.group_name = group_name
    acl.service_principal_name = sp_name
    acl.all_permissions = [MagicMock(permission_level=lv, inherited=False) for lv in permission_levels]
    return acl


def _make_permissions_response(acls):
    """Build a mock permissions.get() return value."""
    resp = MagicMock()
    resp.access_control_list = acls
    return resp


def test_single_object_one_principal_one_permission():
    """A single object with one principal and one permission produces one edge."""
    mock_client = MagicMock()
    mock_client.permissions.get.return_value = _make_permissions_response(
        [_make_acl(user_name="alice@example.com", permission_levels=["CAN_MANAGE"])]
    )

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="clusters",
        object_specs=[("cluster-1", "cluster-1")],
    )

    assert len(edges) == 1
    edge = edges[0]
    assert edge["src"] == "alice@example.com"
    assert edge["dst"] == "cluster-1"
    assert edge["relationship"] == "CAN_MANAGE"
    assert edge["permission_level"] == "CAN_MANAGE"
    assert edge["inherited"] is False
    assert edge["properties"] is None
    assert isinstance(edge["created_at"], datetime)
    mock_client.permissions.get.assert_called_once_with("clusters", "cluster-1")


def test_multi_object_fans_out_to_all_specs():
    """All object_ids must be queried and all edges returned."""
    mock_client = MagicMock()

    def fake_get(_type, object_id):
        return _make_permissions_response(
            [_make_acl(user_name=f"user-{object_id}", permission_levels=["CAN_USE"])]
        )

    mock_client.permissions.get.side_effect = fake_get
    specs = [(f"id-{i}", f"id-{i}") for i in range(5)]

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="clusters",
        object_specs=specs,
        max_workers=4,
    )

    assert len(edges) == 5
    dsts = sorted(e["dst"] for e in edges)
    assert dsts == [f"id-{i}" for i in range(5)]
    assert mock_client.permissions.get.call_count == 5


def test_principal_resolution_prefers_user_then_group_then_sp():
    """The principal field is taken from user_name, then group_name, then service_principal_name."""
    mock_client = MagicMock()
    mock_client.permissions.get.return_value = _make_permissions_response([
        _make_acl(user_name="u@x", permission_levels=["CAN_MANAGE"]),
        _make_acl(group_name="admins", permission_levels=["CAN_VIEW"]),
        _make_acl(sp_name="sp-1", permission_levels=["CAN_USE"]),
    ])

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="jobs",
        object_specs=[("job-1", "job-1")],
    )

    srcs = sorted(e["src"] for e in edges)
    assert srcs == ["admins", "sp-1", "u@x"]


def test_edge_properties_override_passes_through():
    """When edge_properties is set, every edge's properties field gets that value."""
    mock_client = MagicMock()
    mock_client.permissions.get.return_value = _make_permissions_response(
        [_make_acl(user_name="alice", permission_levels=["CAN_MANAGE"])]
    )

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="jobs",
        object_specs=[("job-1", "job-1")],
        edge_properties='{"workspace_id": "ws-42"}',
    )

    assert edges[0]["properties"] == '{"workspace_id": "ws-42"}'


def test_dst_can_differ_from_object_id():
    """object_id is what's queried; dst is what goes on the edge — they can differ."""
    mock_client = MagicMock()
    mock_client.permissions.get.return_value = _make_permissions_response(
        [_make_acl(user_name="alice", permission_levels=["CAN_MANAGE"])]
    )

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="pipelines",
        object_specs=[("abc-123", "pipeline:abc-123")],
    )

    assert mock_client.permissions.get.call_args.args == ("pipelines", "abc-123")
    assert edges[0]["dst"] == "pipeline:abc-123"


def test_exception_for_one_object_does_not_block_others():
    """A failed permissions.get() for one object yields no edges for it,
    but other objects' edges are still returned (matches existing notebook
    behavior of silently swallowing per-object permission errors)."""
    mock_client = MagicMock()

    def fake_get(_type, object_id):
        if object_id == "broken":
            raise RuntimeError("simulated 500")
        return _make_permissions_response(
            [_make_acl(user_name=f"u-{object_id}", permission_levels=["CAN_USE"])]
        )

    mock_client.permissions.get.side_effect = fake_get
    specs = [("ok-1", "ok-1"), ("broken", "broken"), ("ok-2", "ok-2")]

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="clusters",
        object_specs=specs,
    )

    dsts = sorted(e["dst"] for e in edges)
    assert dsts == ["ok-1", "ok-2"]


def test_no_acls_returns_empty_edge_list_for_that_object():
    """An object whose permissions response has no access_control_list contributes no edges."""
    mock_client = MagicMock()
    empty_resp = MagicMock()
    empty_resp.access_control_list = None
    mock_client.permissions.get.return_value = empty_resp

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="experiments",
        object_specs=[("exp-1", "experiment:exp-1")],
    )

    assert edges == []


def test_calls_actually_run_in_parallel():
    """With max_workers >= N and a blocking fake fetch, all N calls must be
    in flight simultaneously — proving the helper isn't running serially."""
    barrier = threading.Barrier(parties=5, timeout=5.0)
    mock_client = MagicMock()

    def fake_get(_type, object_id):
        # If the helper is serial, the barrier will time out and raise.
        barrier.wait()
        return _make_permissions_response(
            [_make_acl(user_name=f"u-{object_id}", permission_levels=["CAN_USE"])]
        )

    mock_client.permissions.get.side_effect = fake_get
    specs = [(f"id-{i}", f"id-{i}") for i in range(5)]

    edges = collect_permission_edges(
        workspace_client=mock_client,
        request_object_type="clusters",
        object_specs=specs,
        max_workers=5,
    )

    assert len(edges) == 5
