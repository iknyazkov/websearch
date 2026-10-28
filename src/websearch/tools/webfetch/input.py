"""Input type and input schema for the WebFetch tool.

Port of internal/tools/webfetch/input.go. The original Go file is a single
3-line struct (input.go:3-5)::

    type Input struct {
        URL string `json:"url" jsonschema:"The URL to fetch content from"`
    }

Go derived the inputSchema at runtime from those tags via the go-sdk's
AddTool reflection; the port hand-writes the dict (§2 "jsonschema-go tag
generation" row), byte-shaped to the judge's s01 capture (migration/judge/
amendments-capture.json, WebFetch inputSchema) and pinned by
migration/judge/harness.py:550-551 (required == ["url"]). Inventory row 82
(WIRE-SCHEMA) is the deciding row for this file.
"""

from dataclasses import dataclass


@dataclass
class Input:
    """WebFetch tool input (Go struct ``Input``).

    A plain carrier (row 82): the handler in tools/webfetch/webfetch.py
    reads ``input.url`` for the CASE-SENSITIVE ``http://`` / ``https://``
    prefix check (webfetch.go:39, pinned by judge s05). Field default
    mirrors the Go zero value (``Input{}``), house convention per
    tools/webfetch/output.py.
    """

    url: str = ""


# Hand-written replacement for the go-sdk's tag-reflection input-schema
# generation (row 82). Byte-shaped to the s01 capture:
# - the ``url`` property dict is PINNED EXACTLY:
#   {"type": "string", "description": "The URL to fetch content from"}.
# - FF-2 does NOT touch WebFetch: NO ``limit`` property ever (row 82).
# - additionalProperties: false is present byte-wise (the s01 capture pins
#   it) but UNENFORCED by the Python SDK — the already-decided SDK row (90):
#   no server-side unknown-arg validation.
INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to fetch content from"},
    },
    "required": ["url"],
    "additionalProperties": False,
}


# PORT STATUS: confidence=high todos=0
