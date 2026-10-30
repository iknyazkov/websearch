"""handler-level cache wiring (post-port extension, no Go twin).

The contract: identical (query, limit) requests — modulo the
search_cache_key folding — reach the upstream service exactly once per TTL
window; the first response carries ``cached=False``, repeats ``cached=True``
with identical content. Negative answers (zero hits) cache like any other:
a repeated empty query must not re-hit the metered upstream quota.
"""

from __future__ import annotations

from websearch.services.cache import TTLCache
from websearch.services.websearch import service as websearch_service
from websearch.tools.websearch import websearch
from websearch.tools.websearch.input import Input as ToolInput
from websearch.tools.websearch.output import Output


class _CountingSearchService:
    """WebSearchService double: one fixed hit, counts upstream calls."""

    def __init__(self) -> None:
        self.calls = 0

    def search(self, input: websearch_service.Input) -> websearch_service.Output:  # noqa: A002
        self.calls += 1
        return websearch_service.Output(
            results=[
                websearch_service.SearchResult(
                    title="Fixed title",
                    url="https://example.com/hit",
                    snippet="Fixed snippet",
                )
            ]
        )


def test_same_query_and_limit_served_from_cache() -> None:
    service = _CountingSearchService()
    cache: TTLCache[Output] = TTLCache(max_entries=8)
    first = websearch.handler(
        ToolInput(query="react docs", limit=6), service, cache=cache
    )
    # Case/whitespace variants fold to one key (search_cache_key contract).
    second = websearch.handler(
        ToolInput(query="  REACT  docs ", limit=6), service, cache=cache
    )
    assert service.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert second.results == first.results


def test_different_limit_misses_the_cache() -> None:
    service = _CountingSearchService()
    cache: TTLCache[Output] = TTLCache(max_entries=8)
    websearch.handler(ToolInput(query="react docs", limit=6), service, cache=cache)
    websearch.handler(ToolInput(query="react docs", limit=50), service, cache=cache)
    assert service.calls == 2


def test_empty_results_are_cached_too() -> None:
    class _EmptyService(_CountingSearchService):
        def search(self, input: websearch_service.Input) -> websearch_service.Output:  # noqa: A002
            self.calls += 1
            return websearch_service.Output(results=[])

    service = _EmptyService()
    cache: TTLCache[Output] = TTLCache(max_entries=8)
    websearch.handler(ToolInput(query="no hits", limit=6), service, cache=cache)
    websearch.handler(ToolInput(query="no hits", limit=6), service, cache=cache)
    assert service.calls == 1
