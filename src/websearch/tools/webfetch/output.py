"""Output type and output schema for the WebFetch tool.

Port of internal/tools/webfetch/output.go (structs ``Content`` and
``Output``) plus the hand-written outputSchema dict this module owns
(inventory row 83, WIRE-SCHEMA): Go generated the schema at runtime via
``jsonschema.For[Output](nil)`` reflection (webfetch.go:30-36); the port
hand-writes the dict byte-shaped to the judge's s01 capture, with the
pinned description strings taken verbatim from the Go ``jsonschema``
struct tags (output.go:3-12). Go's error-fallback branch (``err ->``
``&jsonschema.Schema{}``) is NOT ported here — a dict literal cannot fail
(row 83); the guard shape lives in webfetch.py's output_schema() (row 87).
"""

from dataclasses import dataclass, field


@dataclass
class Content:
    """Processed page content (Go struct ``Content``).

    Bare value type: the wire dict is built explicitly at the boundary in
    webfetch.py's handler (rulebook §2 "struct JSON tags" — no asdict, no
    pydantic). Field defaults mirror the Go zero values (``Content{}``).
    """

    text: str = ""
    # Carries Go's byte-count Length: the VALUE counts UTF-8 bytes and its
    # computation (plus the required kept-quirk marker of rulebook §0)
    # lives in services/webfetch/local/service.py per inventory row 59;
    # the schema description text below ports verbatim bug-for-bug even
    # though Go's byte count makes "Character length" a false claim
    # (row 59).
    length: int = 0


@dataclass
class Output:
    """WebFetch tool output (Go struct ``Output``).

    Field defaults mirror the Go zero values (``Output{}``) per the house
    convention in cloud/parameters.py. ``Content`` is a VALUE struct in Go
    (never a pointer, never nil), so a ``default_factory`` mirrors the zero
    struct — the §2 Optional-deref rule does not apply here.
    """

    url: str = ""
    title: str = ""
    content: Content = field(default_factory=Content)
    # POST-PORT EXTENSION (2026-10-30), no Go twin: True when the response
    # was served from the process-wide cache (services/cache) instead of
    # the upstream fetch. Default False keeps the Go zero-value convention.
    cached: bool = False


# Hand-written replacement for jsonschema.For[Output](nil) reflection
# generation (row 83). Byte-shaped to the s01 capture
# (migration/judge/amendments-capture.json, WebFetch outputSchema):
# - ``content`` is a VALUE struct -> plain "object" type, NO null union
#   (unlike WebSearch's results ["array", "null"]).
# - ``length`` is "integer"; required lists ALL fields at every level (no
#   omitempty in these tags) and every level carries
#   additionalProperties: false.
# - required/type-list order is judge-normalized (norm_schema sorts);
#   declaration order here mirrors the capture anyway.
OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL that was fetched"},
        "title": {"type": "string", "description": "Title of the fetched page"},
        "content": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text content (typically markdown)",
                },
                "length": {
                    "type": "integer",
                    "description": "Character length of the text content",
                },
            },
            "description": "Processed content",
            "required": ["length", "text"],
            "additionalProperties": False,
        },
        # POST-PORT EXTENSION (2026-10-30): beyond the s01 capture — the
        # response-cache flag (services/cache).
        "cached": {
            "type": "boolean",
            "description": "True when the response was served from the in-memory cache",
        },
    },
    "required": ["cached", "content", "title", "url"],
    "additionalProperties": False,
}


# PORT STATUS: confidence=high todos=0
