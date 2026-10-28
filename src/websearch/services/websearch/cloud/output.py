"""Cloud websearch response decode target.

Port of internal/services/websearch/cloud/output.go — the Output/Results
structs that are the json.Decoder response target for the cloud websearch
API body. In Go the decode lives in perform_request
(websearch/cloud/service.go:103-109); the port moves the parse INTO this
module: from_response(text) is the module-level owner of the decode
(inventory row 62, WIRE-DECODE — the row wins over every general rule
where they differ).
"""

import json
from dataclasses import dataclass, field

_DECODER = json.JSONDecoder()

# JSON whitespace is exactly space/tab/LF/CR (RFC 8259) — the set Go's
# Decoder peeks past before a value.
_JSON_WHITESPACE = " \t\n\r"

# Sentinel distinguishing a MISSING "results" key from an EXPLICIT null.
_MISSING = object()


def _skip_whitespace(text: str, idx: int) -> int:
    """Advance idx past JSON whitespace; raw_decode itself refuses to."""
    while idx < len(text) and text[idx] in _JSON_WHITESPACE:
        idx += 1
    return idx


def _object_entries(
    text: str, idx: int, decoder: json.JSONDecoder
) -> list[tuple[str, object, int, int]]:
    """Walk the JSON object whose '{' sits at idx.

    Returns (key, value, value_start, value_end) per entry in DOCUMENT
    order, so callers can reproduce encoding/json's field matching
    (byExactName then byFoldedName, later match overwrites the earlier —
    decode.go:699-703; probed: {"Content":1,"content":2} keeps 2).

    Precondition: the whole value was already accepted by
    decoder.raw_decode on the same text — every structural branch below
    is then guaranteed, so this walker derives positions only and never
    re-validates.
    """
    entries: list[tuple[str, object, int, int]] = []
    idx = _skip_whitespace(text, idx + 1)  # past '{'
    if text[idx] == "}":
        return entries
    while True:
        idx = _skip_whitespace(text, idx)
        key, idx = decoder.raw_decode(text, idx)  # object keys are strings
        idx = _skip_whitespace(text, idx)  # RFC 8259: ws allowed before ':'
        idx = _skip_whitespace(text, idx + 1)  # past ':'
        start = idx
        value, idx = decoder.raw_decode(text, idx)
        entries.append((key, value, start, idx))
        idx = _skip_whitespace(text, idx)
        if text[idx] != ",":
            return entries  # '}' on validated input
        idx = _skip_whitespace(text, idx + 1)


def _array_elements(
    text: str, idx: int, decoder: json.JSONDecoder
) -> list[tuple[object, int, int]]:
    """Walk the JSON array whose '[' sits at idx.

    Returns (element, element_start, element_end) per element in document
    order; same validated-input precondition as _object_entries.
    """
    elements: list[tuple[object, int, int]] = []
    idx = _skip_whitespace(text, idx + 1)  # past '['
    if text[idx] == "]":
        return elements
    while True:
        start = idx
        element, idx = decoder.raw_decode(text, idx)
        elements.append((element, start, idx))
        idx = _skip_whitespace(text, idx)
        if text[idx] != ",":
            return elements  # ']' on validated input
        idx = _skip_whitespace(text, idx + 1)


def _go_kind(value: object) -> str:
    """The value word of Go's UnmarshalTypeError message for `value`."""
    if isinstance(value, bool):  # before int: bool subclasses int
        return "bool"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    return "object"


@dataclass
class Results:
    """Go's Results struct (output.go:9-14).

    title/url/snippet carry Go zero-value semantics: "" when the winning
    key is missing, null, or holds a non-string (see the flagged lenient
    edges at the bottom of this module).

    content is Go's json.RawMessage and is NOT interpreted here. It is the
    plain 3-tuple (present, parsed_value, raw_span) consumed by the
    snippet_from_content precedence chain in service.py (inventory row 75):
    present=False mirrors the nil (len 0) RawMessage of a missing key;
    raw_span reproduces the ORIGINAL response bytes of the winning value
    (a null decodes to the 4-byte span "null", exactly like Go's
    RawMessage — probed 2026-10-27) so the raw-JSON-echo branch emits
    byte-identical text to Go's string(content).
    """

    title: str = ""
    url: str = ""
    snippet: str = ""
    content: tuple[bool, object, str] = (False, None, "")


@dataclass
class Output:
    """Go's Output struct (output.go:5-7); results is never None (s17)."""

    results: list[Results] = field(default_factory=list)


def from_response(text: str) -> Output:
    """Decode the FIRST JSON value of a 200 cloud websearch body.

    First-value semantics (inventory row 62 / A-6): Go's
    json.Decoder.Decode reads the FIRST JSON value and IGNORES trailing
    bytes (stream.go:46) — a 200 body of '{"results":[]}garbage' DECODES
    in Go while resp.json()/json.loads would raise "Extra data". This
    scans the first value from the RAW text the call site passes
    (resp.text), never resp.json(). Malformed JSON raises straight out of
    raw_decode (Go surfaces the raw decode error as the tool error; the
    message text differs — unjudged, no scenario serves malformed JSON
    with a 200).
    """
    idx = _skip_whitespace(text, 0)
    value, _end = _DECODER.raw_decode(text, idx)
    if value is None:
        # Go: a top-level null into the Output struct is an error-free
        # no-op leaving the zero Output (probed 2026-10-27) — empty list.
        return Output(results=[])
    if not isinstance(value, dict):
        # Go: UnmarshalTypeError on a non-object first value (probed:
        # [1,2] and 123 both error).
        raise ValueError(
            f"json: cannot unmarshal {_go_kind(value)} into Go value of type cloud.Output"
        )

    results_value: object = _MISSING
    results_start = -1
    for key, entry_value, start, _entry_end in _object_entries(text, idx, _DECODER):
        # encoding/json field match: exact name, else case-folded
        # (decode.go:699-703); a later match overwrites an earlier one.
        # Probed: {"Results":[...],"results":[]} decodes the LAST one.
        if key.lower() == "results":
            results_value = entry_value
            results_start = start
    if results_value is _MISSING or results_value is None:
        # MISSING key and EXPLICIT null both leave Go's nil slice, which
        # make([]SearchResult, 0, 0) then delivers as [] (service.go:56).
        return Output(results=[])
    if not isinstance(results_value, list):
        # C-6: a NON-LIST non-null results RAISES — Go's whole-decode
        # UnmarshalTypeError surfaces as the tool error; never a silent [].
        raise ValueError(
            "json: cannot unmarshal "
            f"{_go_kind(results_value)} into Go struct field "
            "Output.results of type []cloud.Results"
        )

    results: list[Results] = []
    for element, element_start, _element_end in _array_elements(
        text, results_start, _DECODER
    ):
        # A NON-DICT element maps to the Go zero row, never an
        # AttributeError (row 62): Go decodes a null array element
        # error-free into a zero-valued Results row (probed).
        row = element if isinstance(element, dict) else {}
        title = ""
        url = ""
        snippet = ""
        content: tuple[bool, object, str] = (False, None, "")
        if row:
            for key, entry_value, start, end in _object_entries(
                text, element_start, _DECODER
            ):
                folded = key.lower()
                if folded == "title":
                    title = entry_value if isinstance(entry_value, str) else ""
                elif folded == "url":
                    url = entry_value if isinstance(entry_value, str) else ""
                elif folded == "snippet":
                    snippet = entry_value if isinstance(entry_value, str) else ""
                elif folded == "content":
                    # RAW span, not a re-serialization: the echo branch must
                    # reproduce the original bytes (row 75).
                    content = (True, entry_value, text[start:end])
        results.append(Results(title=title, url=url, snippet=snippet, content=content))
    return Output(results=results)


# Lenient-parse edges (row 62; closed post-parity 2026-10-28,
# document-and-close) — Go fails the WHOLE decode on a
# mistyped field while this parse accepts: a non-string title/url/snippet
# coerces to "", and a NON-NULL non-dict results element ("str", 5, [1])
# maps to the zero row (probed 2026-10-27: {"results":["str"]} and
# {"results":[{"title":1}]} both error in Go; null elements do not). The
# never-type-checked class spans EVERY duplicate whose LAST match is valid,
# not just an earlier case-folded duplicate "results" key: an earlier EXACT
# duplicate "results" key, and a row-level title/url/snippet duplicate
# whose earlier (exact or folded) spelling is mistyped — last-match-wins
# drops all of them before any type check, where Go decodes every matching
# key in document order and fails the whole decode (probed 2026-10-28:
# {"results":[1],"results":[]}, {"Results":[1],"results":[]}, and
# {"results":[{"TITLE":1,"title":"ok"}]} all error in Go). Python json also
# accepts NaN/Infinity literals, lone \ud800 surrogate escapes, and nesting
# deeper than Go's 10000-level scanner cap — encoding/json errors "exceeded
# max depth" there (probed 2026-10-28: a depth-10001 content array errors
# in Go, decodes here); Go substitutes U+FFFD for the surrogates on decode,
# so raw spans echo identically either way; only a decoded title/url/snippet
# VALUE could differ. No fixture mistypes a field, so the strictness
# divergence stays a flagged edge.

# PORT STATUS: confidence=high todos=0
