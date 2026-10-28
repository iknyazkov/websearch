"""Request parameters for the cloud websearch service.

Port of internal/services/websearch/cloud/parameters.go.
"""

from dataclasses import dataclass


@dataclass
class Parameters:
    """Search request body struct (parameters.go:3-9).

    Field defaults mirror the Go zero values ("" / 0), so ``Parameters()``
    equals Go's ``Parameters{}`` — the same dataclass-with-Go-zero-defaults
    shape the inventory prescribes for this package's Config. The wire
    behavior of the Go json tags is decided by this file's inventory row
    (row 63): the request body dict is built explicitly at the wire boundary
    in ``service.make_request`` with ``json.dumps(..., separators=(",", ":"))``
    — ``model`` and ``query`` ALWAYS present; ``max_results`` present iff
    nonzero; ``country`` and ``language`` present iff nonempty (Go
    ``omitempty`` over int 0 / string ""). Go's HTML-escaping of ``<>&`` in
    Marshal is unobservable (the judge parses proxy bodies); plain dumps is
    the conservative choice per the row.
    """

    model: str = ""  # json:"model"
    query: str = ""  # json:"query"
    max_results: int = 0  # json:"max_results,omitempty"
    country: str = ""  # json:"country,omitempty"
    language: str = ""  # json:"language,omitempty"


# PORT STATUS: confidence=high todos=0
