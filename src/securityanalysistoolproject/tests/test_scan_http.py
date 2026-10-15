import threading
import time

from core.scan_http import (
    AdaptiveRateLimiter,
    parse_retry_after,
    request_with_retry,
    collect_tree,
    completeness_verdict,
    TokenProvider,
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


def test_token_provider_caches_within_ttl():
    mints = {"n": 0}
    clock = {"t": 0.0}

    def mint():
        mints["n"] += 1
        return f"tok{mints['n']}"

    tp = TokenProvider(mint, refresh_after=1800, clock=lambda: clock["t"])
    assert tp.header()["Authorization"] == "Bearer tok1"
    clock["t"] = 1799
    tp.header()
    assert mints["n"] == 1  # still cached


def test_token_provider_refreshes_after_ttl():
    mints = {"n": 0}
    clock = {"t": 0.0}
    tp = TokenProvider(lambda: f"tok{mints.__setitem__('n', mints['n']+1) or mints['n']}",
                       refresh_after=1800, clock=lambda: clock["t"])
    tp.header()
    clock["t"] = 1800
    assert tp.header()["Authorization"] == "Bearer tok2"


def test_token_provider_force_refresh():
    mints = {"n": 0}
    tp = TokenProvider(lambda: f"tok{mints.__setitem__('n', mints['n']+1) or mints['n']}")
    tp.header()
    tp.refresh()
    assert mints["n"] == 2


def test_request_with_retry_refreshes_on_401():
    calls = {"n": 0}
    refreshed = {"n": 0}

    class TP:
        def refresh(self):
            refreshed["n"] += 1

    def do():
        calls["n"] += 1
        return FakeResponse(401) if calls["n"] == 1 else FakeResponse(200)

    resp = request_with_retry(do, token_provider=TP(), sleep=lambda s: None, rand=lambda: 0.0)
    assert resp.status_code == 200
    assert refreshed["n"] == 1


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


def test_completeness_clean_scan_not_partial_not_fatal():
    gap, tol, partial, fatal = completeness_verdict(500, 0, 0, 0)
    assert gap == 0 and partial is False and fatal is False


def test_completeness_small_residue_partial_not_fatal():
    # 3 unreadable files on a tiny workspace -> partial, under the floor of 25
    gap, tol, partial, fatal = completeness_verdict(40, 3, 0, 0)
    assert gap == 3 and tol == 25 and partial is True and fatal is False


def test_completeness_customer_case_within_tolerance():
    # 15 unreadable + 1 listing failure out of 642 -> within tolerance, not fatal
    gap, tol, partial, fatal = completeness_verdict(642, 15, 1, 0)
    assert gap == 16 and partial is True and fatal is False


def test_completeness_large_gap_is_fatal():
    # sustained throttling: 300 of 642 unscanned -> exceeds tolerance
    gap, tol, partial, fatal = completeness_verdict(642, 300, 0, 0)
    assert fatal is True


def test_completeness_lost_finding_is_fatal():
    gap, tol, partial, fatal = completeness_verdict(500, 0, 0, 1)
    assert fatal is True


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
