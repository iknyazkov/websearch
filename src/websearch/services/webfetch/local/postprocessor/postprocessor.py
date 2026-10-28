"""Postprocessing contract for the local webfetch service.

Port of internal/services/webfetch/local/postprocessor/postprocessor.go.
"""

from typing import Protocol

# Go: const ContentWasNotFound = "" (postprocessor.go:9). The empty string IS
# the "nothing extracted" result — there is no distinct sentinel. handle()
# never raises for bad content; implementations convert every failure to this
# value (html/postprocessor.go:28-35, choice/processor.go:21-37).
ContentWasNotFound = ""


class Postprocessor(Protocol):
    """Mirror of Go's postprocessor.Postprocessor interface (rulebook §2).

    The parameter types are deliberately NOT Go-verbatim: io.Reader -> bytes
    and http.Header -> dict[str, str] with lowercased keys, forced by the
    FF-5 Result dataclass (Result.data is bytes, Result.parameters is a
    lowercased dict); the single call site (local/service.py fetch) passes
    result.data and result.parameters where Go passes result.Reader and
    result.Parameters. Implementations must spell the first parameter ``data``
    even though all three Go sites spell it ``reader`` (postprocessor.go:13,
    choice/processor.go:21, html/postprocessor.go:28): the rename is decided
    by inventory row 56 — coherent with row 44's Reader->data rename — and
    §4's case-split alone would have kept ``reader``. The spelling must be
    uniform across implementations because mypy strict Protocol
    compatibility compares parameter names (rulebook §4).
    """

    def handle(self, data: bytes, parameters: dict[str, str]) -> str: ...


# PORT STATUS: confidence=high todos=0
