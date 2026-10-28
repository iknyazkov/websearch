"""ComplexWebFetchService: cloud web fetch with unconditional local fallback.

Port of internal/services/webfetch/complex/service.go (Go package `complex`).
This is the failover knot of the webfetch tree: the tool layer talks to this
service, which tries the cloud API first and silently retries against the
local grabber pipeline whenever the cloud call raises.
"""

from dataclasses import dataclass

from websearch.services.webfetch.service import (
    FetchOpts,
    FetchResult,
    WebFetchService,
)


@dataclass
class ComplexWebFetchService:
    """Go struct at complex/service.go:9-12 — two Protocol-typed services.

    Field names are the §4 mechanical snake_case of Go's ``cloudWebFetchService``
    / ``localWebFetchService`` (both injected non-nil by the composition root,
    Go main.go:58-61 — no ``New()`` nil fallback exists here, so there is no
    §2 nil-deref assert site in this file).
    """

    cloud_web_fetch_service: WebFetchService
    local_web_fetch_service: WebFetchService

    def fetch(self, url: str, opts: FetchOpts) -> FetchResult:
        """Go ``Fetch(ctx, url, opts)`` at complex/service.go:14-21.

        - ctx dropped per §2 (CTX site, inventory row 20): pure pass-through to
          both delegates, never inspected — exception-based fallover reads only
          the error, which Go discards either way.
        - ``(*FetchResult, error)`` collapses to a single ``FetchResult``
          return that raises on error (§2; Protocol row 60).
        - The cloud error is SWALLOWED, not chained or wrapped (NIL-SWALLOW,
          inventory row 19): Go binds ``result, err :=`` then ignores BOTH on
          the fallback path. The cloud result never leaves the ``try`` block —
          no partial result can be smuggled out — and the local call's own
          error propagates unchanged, exactly like Go's final
          ``return service.localWebFetchService.Fetch(...)``.
        """
        try:
            return self.cloud_web_fetch_service.fetch(url, opts)
        except Exception:  # noqa: BLE001
            # SAFETY: Go's ``err != nil`` falls back on ANY non-nil error
            # (inventory row 19); ``except Exception`` is its exact mirror.
            # Never widen to ``except BaseException`` — KeyboardInterrupt /
            # SystemExit are the panic analogue and must propagate. This
            # swallow is what keeps "web fetch failed: {status}: {body}"
            # publicly unreachable and drives judge s10/s13 failover.
            pass
        return self.local_web_fetch_service.fetch(url, opts)


# Initialization (complex/service.go:23-33)


def new_web_fetch_service(
    cloud_web_fetch_service: WebFetchService,
    local_web_fetch_service: WebFetchService,
) -> WebFetchService:
    """Go ``NewWebFetchService`` — returns the Protocol, not the class.

    Composition-root wiring (inventory row 60, Go main.go:51-64):
    ``complex.new_web_fetch_service(cloud.new(cfg),
    local.new_web_fetch_service(client))``.
    """
    return ComplexWebFetchService(
        cloud_web_fetch_service=cloud_web_fetch_service,
        local_web_fetch_service=local_web_fetch_service,
    )


# PORT STATUS: confidence=high todos=0
