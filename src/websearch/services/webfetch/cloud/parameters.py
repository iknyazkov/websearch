"""Request parameters for the cloud web-fetch API call.

Port of internal/services/webfetch/cloud/parameters.go.
"""

from dataclasses import dataclass


@dataclass
class Parameters:
    """Body of the POST to <base>/web/fetch.

    Go declares JSON tags here; the port builds the wire dict explicitly at
    the boundary (service.make_request, rulebook §2 "struct JSON tags"), so
    this class is the bare value type. `format`'s `omitempty` is DEAD in the
    source: the service defaults an empty format to "markdown" BEFORE
    constructing Parameters (service.go:37-40), so the wire body always
    carries model/url/format (inventory row 63, FETCH side). Field defaults
    are the Go zero values (""), mirroring `Parameters{}`.
    """

    model: str = ""
    url: str = ""
    # Go-verbatim name; shadows the `format` builtin per rulebook §4.
    format: str = ""


# PORT STATUS: confidence=high todos=0
