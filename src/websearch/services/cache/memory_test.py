"""TTLCache and key-normalization contract (post-port extension, no Go twin).

The clock is injected: no sleeps, no flakes — a manual clock advances only
when a test says so, which also pins the exact TTL boundary (expiry at
``now >= expires_at``, inclusive).
"""

from __future__ import annotations

from websearch.services.cache.memory import TTLCache, fetch_cache_key, search_cache_key


class _Clock:
    """Fake monotonic clock: manual advance, deterministic boundaries."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_miss_then_hit_and_copy_out_isolation() -> None:
    clock = _Clock()
    cache: TTLCache[dict[str, list[int]]] = TTLCache(
        ttl_seconds=60, max_entries=10, clock=clock
    )
    assert cache.get("k") is None
    cache.put("k", {"n": [1, 2]})
    got = cache.get("k")
    assert got == {"n": [1, 2]}
    # Copy-out contract: mutating the returned value must not corrupt the
    # store — the next read still sees the stored snapshot.
    assert got is not None
    got["n"].append(3)
    assert cache.get("k") == {"n": [1, 2]}
    assert (cache.hits, cache.misses) == (2, 1)


def test_entries_expire_after_ttl() -> None:
    clock = _Clock()
    cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=8, clock=clock)
    cache.put("k", "v")
    assert cache.get("k") == "v"
    clock.advance(59)
    assert cache.get("k") == "v"
    clock.advance(1)  # exactly at the boundary: now >= expires_at -> expired
    assert cache.get("k") is None
    # A re-put after expiry works (lazy deletion freed the key).
    cache.put("k", "v2")
    assert cache.get("k") == "v2"


def test_full_cache_purges_expired_entries_before_evicting() -> None:
    clock = _Clock()
    cache: TTLCache[int] = TTLCache(ttl_seconds=60, max_entries=2, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    clock.advance(61)  # both expired
    cache.put("c", 3)  # expired sweep makes room — no live entry is lost
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_full_cache_evicts_earliest_expiry_when_nothing_expired() -> None:
    clock = _Clock()
    cache: TTLCache[int] = TTLCache(ttl_seconds=60, max_entries=2, clock=clock)
    cache.put("a", 1)  # expires at 1060
    clock.advance(10)
    cache.put("b", 2)  # expires at 1070
    clock.advance(5)
    cache.put("c", 3)  # full, nothing expired -> evict a (earliest expiry)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_zero_capacity_disables_storage() -> None:
    cache: TTLCache[str] = TTLCache(max_entries=0)
    cache.put("k", "v")
    assert cache.get("k") is None


def test_search_key_folds_case_and_whitespace_and_keeps_limit() -> None:
    assert search_cache_key("  React   DOCS ", 6) == search_cache_key("react docs", 6)
    assert search_cache_key("react docs", 6) != search_cache_key("react docs", 50)
    assert search_cache_key("react docs", 6) != search_cache_key("rust docs", 6)


def test_fetch_key_normalizes_scheme_host_and_drops_fragment() -> None:
    assert fetch_cache_key("HTTPS://Example.com/Path?a=1#frag") == fetch_cache_key(
        "https://example.com/Path?a=1"
    )
    # Path is case-sensitive; empty path folds to "/".
    assert fetch_cache_key("https://example.com/Path") != fetch_cache_key(
        "https://example.com/path"
    )
    assert fetch_cache_key("https://example.com") == fetch_cache_key(
        "https://example.com/"
    )


def test_fetch_key_preserves_userinfo_case() -> None:
    # Basic-auth credentials are case-sensitive — only the host folds.
    assert fetch_cache_key("https://user:PW@example.com/") != fetch_cache_key(
        "https://user:pw@example.com/"
    )
    assert fetch_cache_key("https://user:PW@EXAMPLE.com/") == fetch_cache_key(
        "https://user:PW@example.com/"
    )
