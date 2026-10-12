import threading
import time

from core.scan_http import (
    AdaptiveRateLimiter,
    parse_retry_after,
    request_with_retry,
    collect_tree,
)


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_limiter_never_exceeds_cap():
    limiter = AdaptiveRateLimiter(start=3, max_limit=3, increase_after=10**9)
    peak = {"n": 0}
    live = {"n": 0}
    lock = threading.Lock()

    def worker():
        with limiter:
            with lock:
                live["n"] += 1
                peak["n"] = max(peak["n"], live["n"])
            time.sleep(0.01)
            with lock:
                live["n"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak["n"] <= 3


def test_aimd_shrinks_on_throttle_and_recovers():
    limiter = AdaptiveRateLimiter(start=8, min_limit=1, max_limit=16, increase_after=3)
    assert limiter.limit == 8
    limiter.record_throttled()
    assert limiter.limit == 4
    limiter.record_throttled()
    assert limiter.limit == 2
    for _ in range(3):
        limiter.record_success()
    assert limiter.limit == 3


def test_parse_retry_after_seconds_and_date():
    assert parse_retry_after({"Retry-After": "12"}) == 12.0
    assert parse_retry_after({"retry-after": "0"}) == 0.0
    assert parse_retry_after({}) is None
    assert parse_retry_after({"Retry-After": "not-a-number"}) is None

    now = parsedate_now()
    future = "Wed, 21 Oct 2099 07:28:00 GMT"
    assert parse_retry_after({"Retry-After": future}, now=now) > 0


def parsedate_now():
    from datetime import datetime, timezone
    return datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_request_with_retry_honors_retry_after():
    calls = {"n": 0}
    slept = []
    limiter = AdaptiveRateLimiter(start=4, max_limit=8)

    def do():
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(429, {"Retry-After": "7"})
        return FakeResponse(200)

    resp = request_with_retry(do, limiter=limiter, sleep=slept.append)
    assert resp.status_code == 200
    assert slept == [7.0]
    assert limiter.limit == 2  # one throttle halved 4 -> 2


def test_request_with_retry_backoff_without_retry_after():
    calls = {"n": 0}
    slept = []

    def do():
        calls["n"] += 1
        return FakeResponse(429) if calls["n"] == 1 else FakeResponse(200)

    resp = request_with_retry(
        do, base_sleep=2.0, sleep=slept.append, rand=lambda: 0.0
    )
    assert resp.status_code == 200
    assert slept == [1.0]  # base 2 -> half 1 + 0 jitter


def test_request_with_retry_returns_last_429_on_exhaustion():
    def do():
        return FakeResponse(429)

    resp = request_with_retry(do, max_attempts=3, sleep=lambda s: None, rand=lambda: 0.0)
    assert resp.status_code == 429


def test_request_with_retry_transport_error_recovers():
    calls = {"n": 0}

    def do():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return FakeResponse(200)

    resp = request_with_retry(do, max_attempts=5, sleep=lambda s: None, rand=lambda: 0.0)
    assert resp.status_code == 200
    assert calls["n"] == 3


def test_request_with_retry_transport_error_exhausts_to_none():
    def do():
        raise ConnectionError("boom")

    resp = request_with_retry(do, max_attempts=3, sleep=lambda s: None, rand=lambda: 0.0)
    assert resp is None


def test_collect_tree_walks_entire_tree():
    tree = {
        "/": (["/Users", "/Shared", "/Repos"], []),
        "/Users": (["/Users/a"], []),
        "/Users/a": ([], ["/Users/a/nb1", "/Users/a/nb2"]),
        "/Shared": ([], ["/Shared/nb3"]),
        "/Repos": (["/Repos/team"], []),
        "/Repos/team": ([], ["/Repos/team/nb4"]),
    }

    def list_children(path):
        dirs, leaves = tree[path]
        return dirs, leaves, True

    leaves, failed = collect_tree(list_children, ["/"])
    assert failed == 0
    assert sorted(leaves) == [
        "/Repos/team/nb4", "/Shared/nb3", "/Users/a/nb1", "/Users/a/nb2",
    ]


def test_collect_tree_counts_failed_listings():
    def list_children(path):
        if path == "/":
            return ["/good", "/bad"], [], True
        if path == "/good":
            return [], ["/good/nb1"], True
        return [], [], False  # /bad could not be listed

    leaves, failed = collect_tree(list_children, ["/"])
    assert leaves == ["/good/nb1"]
    assert failed == 1
