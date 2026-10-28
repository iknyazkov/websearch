"""Input type and input schema for the WebSearch tool.

Port of internal/tools/websearch/input.go. The original Go file is a single
3-line struct (input.go:3-5)::

    type Input struct {
        Query string `json:"query" jsonschema:"The search query to use"`
    }

The ``Limit`` field is the §0 FIX-FORWARD FF-2a addition (migration/judge/
fixedgo.py:37-42) — the executable spec, not a kept-bug marker site (§0)::

    Limit int `json:"limit,omitempty" jsonschema:"Maximum number of results to return"`

Go derived the inputSchema at runtime from those tags via the go-sdk's
jsonschema reflection; the port hand-writes the dict (§2 "jsonschema-go tag
generation" row), byte-shaped to the judge's s01 capture (migration/judge/
amendments-capture.json, WebSearch inputSchema) and pinned by
migration/judge/harness.py:538-544. Inventory row 88 (WIRE-SCHEMA-FF2) is the
deciding row for this file.
"""

from dataclasses import dataclass


@dataclass
class Input:
    """WebSearch tool input (Go struct ``Input``).

    Field defaults mirror the Go zero values (``Input{}``), house convention
    per tools/webfetch/output.py; row 88 pins ``limit: int`` with default 0.

    Consumption of ``limit`` is FF-2b and lives in the tool handler
    (tools/websearch/websearch.py, rows 90/94: 50 unless input limit > 0) —
    not here.
    """

    query: str = ""
    limit: int = 0


# Hand-written replacement for the go-sdk's tag-reflection input-schema
# generation (row 88). Byte-shaped to the s01 capture:
# - the ``limit`` property dict is PINNED EXACTLY (harness.py:538-544):
#   {"type": "integer", "description": "Maximum number of results to return"}.
# - ``limit`` is NOT in required: the fixedGo FF-2a tag carries
#   json:"limit,omitempty" and jsonschema-go omits omitempty fields from
#   required; required must sort to exactly ["query"] or s01/s18 fail.
# - additionalProperties: false is present byte-wise but UNENFORCED by the
#   Python SDK — the accepted divergence already decided by the SDK row (90);
#   on the old side the go-sdk used it to reject the unknown ``limit``
#   argument outright (judge s18's old-side marker).
INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to use"},
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return",
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


# PORT STATUS: confidence=high todos=0
