"""ContentGrabber interface.

Port of internal/services/webfetch/local/grabber/grabber.go (Go source is
the 4-line ``type ContentGrabber interface`` declaration).
"""

from typing import Protocol

from websearch.services.webfetch.local.grabber.resource import Resource
from websearch.services.webfetch.local.grabber.result import Result


class ContentGrabber(Protocol):
    """Structural contract every grabber satisfies (Go grabber.go:7-10).

    Inventory rows for grabber.go (IFACE + CTX sites) pin this shape:

    - ``IsCanGrab(resource Resource) bool`` -> ``is_can_grab`` (§4
      multi-word snake_case); already ctx-free in Go, otherwise unchanged.
    - ``Grab(ctx context.Context, resource Resource) (*Result, error)`` ->
      ``grab`` with NO ctx parameter (§2 ``context.Context`` row: no ported
      site observes cancellation mid-flight) and a single ``Result`` return
      — the ``(*Result, error)`` pair collapses to raise-on-error (§2). The
      signature difference from Go's ``Grab(ctx, ...)`` is the spec, not
      drift.
    - Implementations register exactly where Go's do and never inherit this
      Protocol explicitly: Go has no implements clause, satisfaction is
      structural, and the only explicit interface declarations are
      constructor return types (client.py ``new_grabber -> ContentGrabber``
      whose ``is_can_grab`` always returns True; github.py ``new_grabber(
      client, fallback: ContentGrabber) -> ContentGrabber``). The sole
      ``IsCanGrab`` call site is local/service.py's ``get_grabber``:
      github grabber iff ``is_can_grab(resource)`` else the client grabber.
      mypy checks duck-typed implementations structurally at those annotated
      sites — mirroring Go (mockGrabber satisfies the interface with zero
      declaration, github/grabber_test.go:160-172).
    """

    def is_can_grab(self, resource: Resource) -> bool: ...

    def grab(self, resource: Resource) -> Result: ...


# PORT STATUS: confidence=high todos=0
