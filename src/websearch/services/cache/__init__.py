"""Public surface of the response cache (post-port extension, 2026-10-30).

No Go twin: the Go source never cached; see memory.py for the contract.
The per-tool singleton instances live in the tool modules
(tools/websearch/websearch.py, tools/webfetch/webfetch.py) — typed with
each tool's own Output, so this package ships only the mechanics and the
key builders.
"""

from websearch.services.cache.memory import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_TTL_SECONDS,
    TTLCache,
    fetch_cache_key,
    search_cache_key,
)

__all__ = [
    "DEFAULT_MAX_ENTRIES",
    "DEFAULT_TTL_SECONDS",
    "TTLCache",
    "fetch_cache_key",
    "search_cache_key",
]
