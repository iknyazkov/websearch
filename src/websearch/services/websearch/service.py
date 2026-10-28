"""WebSearchService protocol plus the Input/Output/SearchResult value types.

Port of internal/services/websearch/service.go (Go package `websearch`).
The wire structs with JSON tags live in websearch/cloud/output.py per §4
ownership; these dataclasses carry no tags (inventory row 79).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WebSearchService(Protocol):
    def search(self, input: Input) -> Output:  # noqa: A002
        # NOTE: `input` is the Go-verbatim parameter name (§4) — a local
        # binding only, never a use of the builtin.
        # ctx dropped per §2; Go's (*Output, error) becomes Output-or-raise
        # (inventory rows 80/81 — never Optional, never None).
        ...


@dataclass
class Input:
    # All four fields default to the Go zero value: the tool handler sets
    # query and limit only, so Country/Language arrive here as '' (inventory
    # row 94, NIL-ZERO — zero value is load-bearing: mirror '' so the body
    # builder never sees None; never Optional[str]).
    query: str = ""
    limit: int = 0
    country: str = ""
    language: str = ""


@dataclass
class Output:
    results: list[SearchResult]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


# PORT STATUS: confidence=high todos=0
