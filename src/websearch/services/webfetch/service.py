"""WebFetch service contract — the Protocol plus its three value types.

Port of internal/services/webfetch/service.go (Go package ``webfetch``).
Inventory rows 60/61 own every decision in this module: the interface is
a ``typing.Protocol`` with the same method set (§2 interfaces row), ctx
is dropped from the ported signature (§2 context.Context row — the whole
webfetch call tree never observes cancellation; repo-wide grep has zero
ctx.Done/Err/Deadline/Value hits), and Go's ``(*FetchResult, error)``
collapses to a single ``FetchResult`` that raises on error (§2). This
module is the leaf of the webfetch tree: cloud, local, and complex
import it; it imports nothing of ours.

The structs carry NO JSON tags in Go and never marshal — the tool layer
maps to its own Output (row 60) — so they stay plain dataclasses with no
wire representation of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class WebFetchService(Protocol):
    """Go ``WebFetchService`` interface (service.go:5-7).

    Implementations register exactly where Go's do (row 60):
    ``cloud.CloudWebFetchService`` (via ``cloud.new``),
    ``local.LocalWebFetchService`` (via ``local.new_web_fetch_service``),
    and ``complex.ComplexWebFetchService`` (via
    ``complex.new_web_fetch_service``) — each constructor returns this
    Protocol, not its class.
    """

    # `url` is the majority Go spelling — interface :6, complex :14, and
    # local :19 all say `url`; cloud :29 alone says `targetURL`. §4's
    # Protocol-compat exception: mypy strict compares parameter NAMES, so
    # every implementation and test double must spell it `url`.
    # (*FetchResult, error) -> FetchResult-or-raise, never Optional.
    def fetch(self, url: str, opts: FetchOpts) -> FetchResult: ...


@dataclass
class FetchOpts:
    """Go ``FetchOpts`` struct (service.go:9-11).

    Defaults mirror Go zero values; the only source construction sets
    Format explicitly — ``FetchOpts{Format: "markdown"}`` at
    tools/webfetch/webfetch.go:43.
    """

    # Go-verbatim name; shadows the `format` builtin per rulebook §4.
    format: str = ""


@dataclass
class Content:
    """Go ``Content`` struct (service.go:13-16).

    ``length`` counts whatever the producing implementation puts there:
    the local service pins it to UTF-8 BYTES (Go ``len(string)``
    semantics — that kept-bug lives in local/service.py, not here); the
    cloud service passes the API response's own length through.
    """

    text: str = ""
    length: int = 0


@dataclass
class FetchResult:
    """Go ``FetchResult`` struct (service.go:18-22).

    Defaults mirror Go zero values: the local service constructs the
    result with URL and Content only (local/service.go:32-38), so Title
    stays the Go zero value "" on that path — while the tool layer reads
    ``result.Title`` unconditionally (tools/webfetch/webfetch.go:50).
    """

    url: str = ""
    title: str = ""
    content: Content = field(default_factory=Content)


# PORT STATUS: confidence=high todos=0
