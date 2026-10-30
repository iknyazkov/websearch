"""WebSearch tool wire-output value types.

Port of internal/tools/websearch/output.go (Go package `websearch`, the
tools/websearch package) — the tool-layer Output/SearchHit structs that shape
the structured-content payload of every WebSearch call.

Ownership, so nothing drifts (§4: output.py owns Output; §2 struct-JSON-tags
row: output dicts are built EXPLICITLY at the wire boundary — no asdict, no
pydantic):

- The JSON serialization lives in the tool handler, tools/websearch/
  websearch.py (inventory row 95: {'url': ..., 'title': ..., 'content': ...}
  built over a never-None results list, always {'results': [...]}, s17;
  POST-PORT 2026-10-30: the wire dict also carries the ``cached`` flag).
- The outputSchema dict generated from the jsonschema tags documented below
  lives in tools/websearch/websearch.py too (inventory row 96 evidence:
  "outputSchema() at websearch.go:33-41 (NOT output.go — that file is the
  11-line Output struct with jsonschema tags)"). This module owns only the
  value types; the tag text below is documentation of the Go source only —
  the schema dict in websearch.py carries its own hand-written description
  literals, byte-shaped to the captured s01 outputSchema (inventory row 96),
  and reads nothing from this module.

§5 flag: NO inventory row carries this file's path in its file column
(migration/inventory.tsv, verified by grep) — the webfetch twin's WIRE-SCHEMA
row attached to tools/webfetch/output.go has its websearch counterpart
attached to internal/tools/websearch/websearch.go instead (row 96), whose
evidence explicitly relocates the schema site off this file. Every construct
remaining here (two pure struct declarations) is decided by §4 naming, §2
nil-slice, and FF-1 — no UNKNOWN site, so no deferred-decision marker is
owed under the UNKNOWN rule. The deciding rows followed: 95, 96 (handler +
schema, file column websearch.go), 79 (service-twin Output shape).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Output:
    """Top-level tool output.

    Go (output.go:3-5):

        Results []SearchHit `json:"results"
                             jsonschema:"Array of search hits"`

    Over the wire the value is ALWAYS a list, never null (§2 nil-slice rule,
    judge s17): Go's handler pre-makes the slice with make([]SearchHit, 0,
    len(...)) (websearch.go:54), so the tool layer never carries a nil
    Results — the field is a plain list, mirroring the service-layer twin
    services/websearch/service.py Output.results (inventory row 79).
    """

    results: list[SearchHit]
    # POST-PORT EXTENSION (2026-10-30), no Go twin: True when the response
    # was served from the process-wide cache (services/cache) instead of
    # the upstream API. Default False keeps the Go zero-value convention.
    cached: bool = False


@dataclass
class SearchHit:
    """One search hit.

    Go (output.go:7-11), declaration order preserved:

        URL     string `json:"url"
                        jsonschema:"The URL of the search result"`
        Title   string `json:"query"
                        jsonschema:"The title of the search result"`
        Content string `json:"content"
                        jsonschema:"Result of search"`

    FF-1 (§0 FIX-FORWARD list — the spec, not a kept-quirk marker site): Title
    serializes as "title" in results AND the outputSchema property is
    "title"; the Go json:"query" tag is the defect fixed forward. The Python
    field is `title` either way (§4 single-identifier names stay verbatim);
    the wire key itself is spelled at the explicit-dict boundary in the
    handler (row 95: 'title'), never via a tag mechanism.

    Field mapping from the service layer happens in the handler (Go
    websearch.go:56-61: URL<-result.URL, Title<-result.Title,
    Content<-result.Snippet) — not here.
    """

    url: str
    title: str
    content: str


# PORT STATUS: confidence=high todos=0
