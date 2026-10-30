"""TTLCache — the bounded, thread-safe, expiring in-memory cache.

Post-port extension (2026-10-30), no Go twin: the Go source never cached
anything — the WebFetch tool description's "self-cleaning 15-minute cache"
line was captured aspiration, not behavior (a repo-wide grep found no cache
code). This module makes that line true and gives WebSearch the same
treatment: both tools sit in front of a slow or metered upstream (the cloud
search API carries a monthly quota; the cloud fetch path routes through an
LLM), and the dominant client — multi-agent runs — re-issues identical
requests within one session by design (three verifier panels per claim,
repeat research on the same question).

Shape:

- Keys are caller-owned strings built by ``search_cache_key`` /
  ``fetch_cache_key``; each tool owns its own ``TTLCache`` instance, so no
  cross-tool collision is possible.
- Values are stored as deep copies and every ``get`` returns another deep
  copy: a cached value is an immutable snapshot, and a handler may mutate
  what it receives without corrupting the store. Deepcopy is cheap at this
  scale — the payloads are dict/list/dataclass wrappers around immutable
  strings, which deepcopy aliases rather than copies.
- TTL rides an injectable monotonic clock (tests substitute a manual one;
  production uses ``time.monotonic``, immune to wall-clock jumps). Entries
  expire lazily on read and are swept on put when the table is full — the
  "self-cleaning" the description claims.
- One ``threading.Lock`` covers the whole table: the MCP server runs sync
  handlers via ``asyncio.to_thread``, so concurrent tool calls reach the
  cache from several threads.
- ``hits``/``misses`` are process-lifetime observability counters; no tool
  surface reads them yet.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from copy import deepcopy
from threading import Lock
from typing import Generic, TypeVar
from urllib.parse import urlsplit

V = TypeVar("V")

# The 15 minutes the WebFetch tool description has promised since the port.
# One constant for both tools: staleness tolerance is a property of a
# research session, not of a particular tool.
DEFAULT_TTL_SECONDS = 15 * 60

# Per-cache cap. Search results and fetched pages are MB-scale at worst;
# 100 entries bounds the process to a few hundred MB worst case while
# comfortably covering a research run (dozens of fetches and searches).
DEFAULT_MAX_ENTRIES = 100


class TTLCache(Generic[V]):
    """A fixed-capacity map with per-entry expiry and copy-out semantics."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = Lock()
        self._store: dict[str, tuple[float, V]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> V | None:
        """Return a private deep copy of the live entry, or None.

        A read of an expired entry deletes it (lazy expiry) and counts as a
        miss; counters are process-lifetime observability.
        """
        now = self._clock()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if now >= expires_at:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
        # SAFETY: deepcopy runs OUTSIDE the lock — the snapshot value is
        # never mutated after put (put stores its own copy), so copying an
        # escaped reference cannot race with another thread replacing the
        # entry; the worst case is copying a value another put is about to
        # orphan, which is harmless.
        return deepcopy(value)

    def put(self, key: str, value: V) -> None:
        """Store a deep copy of ``value`` under ``key``.

        A put into a full cache first drops every expired entry, then — if
        there is still no room — evicts the entry with the earliest expiry.
        A non-positive ``max_entries`` disables the cache entirely (put
        stores nothing, get always misses).
        """
        if self._max_entries <= 0:
            return
        now = self._clock()
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_entries:
                self._evict_locked(now)
            self._store[key] = (now + self._ttl_seconds, deepcopy(value))

    def _evict_locked(self, now: float) -> None:
        """Make room for one more entry. Called with the lock HELD."""
        for stale in [
            key
            for key, (expires_at, _) in self._store.items()
            if now >= expires_at
        ]:
            del self._store[stale]
        if len(self._store) >= self._max_entries:
            # With a fixed TTL, expiry order is insertion order, so the
            # earliest-expiring entry is the oldest live one.
            oldest = min(self._store, key=lambda key: self._store[key][0])
            del self._store[oldest]


def search_cache_key(query: str, limit: int) -> str:
    """Cache key for a WebSearch call: case/whitespace-folded query + limit.

    Lowercasing merges case variants ("React docs" == "react docs") — the
    upstream engine matches loosely enough that the merged results serve
    both callers. ``limit`` is part of the key: the same query at limit 5
    and 50 returns different result sets, and a smaller cached answer must
    never satisfy a larger request.
    """
    return f"search|{limit}|" + " ".join(query.split()).lower()


def fetch_cache_key(url: str) -> str:
    """Cache key for a WebFetch URL: canonical scheme/host, fragment dropped.

    Scheme and host are case-insensitive per RFC 3986 (the handler has
    already enforced the http(s) scheme); path and query are case-sensitive
    and kept byte-exact; userinfo is case-sensitive (basic-auth credentials)
    and preserved byte-exact; the fragment never reaches the origin, so URLs
    differing only in fragment are one resource and share an entry.
    Default-port collapsing is deliberately NOT done: the rare explicit
    :port is part of the address that was contacted.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)
        netloc = (parts.hostname or "").lower()
        if parts.port is not None:
            netloc += f":{parts.port}"
        if parts.username is not None:
            userinfo = parts.username
            if parts.password is not None:
                userinfo += ":" + parts.password
            netloc = userinfo + "@" + netloc
        target = f"{parts.scheme.lower()}://{netloc}{parts.path or '/'}"
        if parts.query:
            target += "?" + parts.query
        return "fetch|" + target
    except ValueError:
        # urlsplit raises on malformed components (bad IPv6 brackets, out-
        # of-range port); the handler has already scheme-validated the URL,
        # so the raw string is a serviceable fallback key.
        return "fetch|" + raw
