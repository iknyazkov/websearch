"""Grabber result type.

Port of internal/services/webfetch/local/grabber/result.go (struct Result).
"""

from dataclasses import dataclass


@dataclass
class Result:
    """Fetch outcome a grabber hands to the local service.

    Go source::

        type Result struct {
            Reader     io.Reader
            Parameters http.Header
        }

    Field shapes are the decided inventory convention (inventory row for
    result.go, pinned by the FF-5 producer rows):

    - ``Reader io.Reader`` -> ``data: bytes`` (field renamed Reader->data):
      eager bytes, not a lazy reader. §1 keeps bytes only at the HTTP
      boundary; every downstream consumer wants raw bytes — the html
      extractor's charset detection runs on the RAW BYTES (BYTES-CHARSET
      row) and the plain branch decodes utf-8 errors="replace" (choice row).
    - ``Parameters http.Header`` (map[string][]string, canonical-case keys,
      Get() canonicalizes its lookup) -> ``parameters: dict[str, str]`` with
      keys LOWERCASED at construction — the choice processor's
      ``parameters.get("content-type", "")`` lookup relies on it (FF-6 row).
      Both producers lowercase keys at construction: the client grabber
      flattens ``resp.headers.multi_items()`` with ``setdefault(k.lower(),
      v)`` — first value wins, like Go's Header.Get (FF-5 row + post-parity
      fix F3, 2026-10-28) — while the github fetch synthesizes
      a fresh single-entry dict ``{"content-type": contentType}`` — the
      upstream response headers are discarded entirely (github fetch
      rows); the consumer is local/service.py's fetch, which hands
      ``result.data`` and ``result.parameters`` to postprocessor.handle.
    """

    data: bytes
    parameters: dict[str, str]
    # Header flattening — RESOLVED (post-parity fix F3, 2026-10-28): the
    # client producer builds via multi_items() + setdefault, so a repeated
    # header keeps its FIRST value exactly like Go's Header.Get (httpx
    # items() would comma-join, a plain comprehension would keep the LAST).
    # Only Content-Type is ever read and no fixture repeats headers.


# PORT STATUS: confidence=high todos=0
