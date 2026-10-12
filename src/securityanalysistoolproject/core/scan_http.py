"""Adaptive HTTP pacing and workspace-tree traversal for the secret scanners."""

import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class AdaptiveRateLimiter:
    """Bounds concurrent requests and self-tunes to the workspace rate limit.

    Starts low, grows after sustained success, and multiplicatively shrinks
    whenever the server throttles, so a single setting works across workspaces
    of any size.
    """

    def __init__(self, start=4, min_limit=1, max_limit=16,
                 decrease_factor=0.5, increase_after=25):
        self._min = max(1, int(min_limit))
        self._max = max(self._min, int(max_limit))
        self._limit = min(max(int(start), self._min), self._max)
        self._decrease_factor = decrease_factor
        self._increase_after = max(1, int(increase_after))
        self._in_use = 0
        self._successes = 0
        self._cv = threading.Condition()

    @property
    def limit(self):
        with self._cv:
            return self._limit

    def acquire(self):
        with self._cv:
            while self._in_use >= self._limit:
                self._cv.wait()
            self._in_use += 1

    def release(self):
        with self._cv:
            if self._in_use > 0:
                self._in_use -= 1
            self._cv.notify()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def record_throttled(self):
        with self._cv:
            self._limit = max(self._min, int(self._limit * self._decrease_factor))
            self._successes = 0

    def record_success(self):
        with self._cv:
            self._successes += 1
            if self._successes >= self._increase_after and self._limit < self._max:
                self._limit += 1
                self._successes = 0
                self._cv.notify()


def parse_retry_after(headers, now=None):
    """Return the Retry-After value in seconds, or None if absent or invalid."""
    if not headers:
        return None
    value = None
    for key in headers:
        if str(key).lower() == "retry-after":
            value = headers[key]
            break
    if value is None:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (when - current).total_seconds())


def request_with_retry(do_request, limiter=None, max_attempts=8,
                       base_sleep=1.0, max_sleep=60.0,
                       sleep=time.sleep, rand=random.random, now=None,
                       on_retry=None):
    """Call ``do_request`` with adaptive pacing and 429/transport retries.

    ``do_request`` returns a response exposing ``status_code`` and ``headers``,
    or raises for transport errors. Honors Retry-After when present, otherwise
    uses equal-jitter backoff. Returns the response, or None if every attempt
    failed to reach the server.
    """
    last = None
    for attempt in range(max_attempts):
        if limiter is not None:
            limiter.acquire()
        try:
            resp = do_request()
            err = None
        except Exception as exc:
            resp, err = None, exc
        finally:
            if limiter is not None:
                limiter.release()

        if err is None and resp is not None and getattr(resp, "status_code", None) != 429:
            if limiter is not None:
                limiter.record_success()
            return resp

        if err is None and resp is not None:
            last = resp
            if limiter is not None:
                limiter.record_throttled()
            wait = parse_retry_after(getattr(resp, "headers", None), now=now)
        else:
            wait = None

        if attempt == max_attempts - 1:
            return last

        if wait is None:
            base = min(max_sleep, base_sleep * (2 ** attempt))
            wait = base / 2 + rand() * (base / 2)
        else:
            wait = min(max_sleep, wait)
        if on_retry is not None:
            on_retry(attempt, wait, resp, err)
        sleep(wait)

    return last


def collect_tree(list_children, roots, mapper=map):
    """Breadth-first walk of a workspace tree.

    ``list_children(path)`` returns ``(dirs, leaves, listed_ok)``. Returns
    ``(leaves, failed)`` where ``failed`` counts directories that could not be
    listed.
    """
    leaves = []
    failed = 0
    pending = list(roots)
    while pending:
        next_dirs = []
        for dirs, found, listed_ok in mapper(list_children, pending):
            if not listed_ok:
                failed += 1
            leaves.extend(found)
            next_dirs.extend(dirs)
        pending = next_dirs
    return leaves, failed
