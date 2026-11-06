"""In-memory rate limiting for the endpoints that cost money or invite abuse.

`/api/soil-analysis` and `/api/farm-chat` call Gemini. Both are authenticated,
but a signed-in account is not a spending limit: without a cap, one user with a
script can exhaust the shared free-tier quota and take the feature down for
everyone. They were previously unlimited.

A sliding window per user is enough here. It is per-process, so it resets on
restart and does not coordinate across replicas — for a single free-tier
container that is the right trade (no Redis dependency, no extra service to
configure). If the API ever runs more than one instance, this needs to move to
shared storage; the limit below would otherwise be multiplied by the replica
count.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class SlidingWindow:
    """At most `limit` events per `window_s` seconds, per key."""

    def __init__(self, *, limit: int, window_s: int, label: str) -> None:
        self.limit = limit
        self.window_s = window_s
        self.label = label
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        cutoff = now - self.window_s
        while events and events[0] <= cutoff:
            events.popleft()
        return events

    def hit(self, key: str) -> None:
        """Record one event, or raise 429 with a retry hint."""
        now = time.monotonic()
        events = self._prune(key, now)

        if len(events) >= self.limit:
            retry_after = max(1, int(self.window_s - (now - events[0])))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You have reached the {self.label} limit "
                    f"({self.limit} per {self.window_s // 60} minutes). "
                    f"Try again in {retry_after} seconds."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        events.append(now)


# Photo analysis is the expensive call (images cost many tokens), so it is the
# tightest. Chat is cheap per message but easy to hammer from a loop.
photo_analysis_limiter = SlidingWindow(limit=10, window_s=600, label="photo analysis")
chat_limiter = SlidingWindow(limit=30, window_s=600, label="adviser chat")
