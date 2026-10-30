"""Composition root — port of main.go (Go module ``main``).

Wiring only: this file owns no behavior the Go file did not. Every decision
is pinned by this file's two inventory rows (the rows win over anything
re-derived here):

- Row 97 (NIL-ZERO, env zero-values + log.Fatal): every ``os.Getenv`` call
  becomes ``os.environ.get(NAME, "")`` — the Config str fields receive Go's
  "" zero value, never None. Load-bearing: the webfetch cloud service guards
  ``base_url == ""`` (webfetch/cloud/service.go:33-35, "base_url must not be
  empty") and a None would skip that guard; the websearch cloud service has
  NO empty-BaseURL guard (websearch/cloud/service.go:40-49 — url.Parse("")
  succeeds and the failure surfaces later as a transport error), and none is
  added here. ``server.Run`` failure becomes ``raise SystemExit`` (log.Fatal
  parity).
- Row 98 (NIL-ZERO, nil *ServerOptions + zero-value StdioTransport): the
  server is built as ``Server(name="websearch", version="v1.0.0")`` with the
  options argument OMITTED entirely — Go's nil *ServerOptions means
  all-default options and the Python low-level Server's own constructor
  defaults are the equivalent (never a placeholder options object). The
  serverInfo block {name "websearch", version "v1.0.0"} is pinned byte-exact
  by judge s01. The zero-value ``&mcp.StdioTransport{}`` maps to the SDK's
  default stdio run path over anyio stdin/stdout (nothing to configure), and
  ``context.Background()`` is dropped per rulebook §2.

Row 98 also pins the wiring ORDER: client -> server -> RegisterWebSearch ->
RegisterWebFetch -> run. FF-1..FF-6 touch no site in this file.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server

from websearch.services.network import client as network
from websearch.services.webfetch.cloud import service as webfetch_cloud

# SAFETY: `complex` is Go's verbatim import alias (main.go:13, alias for
# internal/services/webfetch/complex) — a module-level binding only; the
# builtin `complex` type is never used in this file.
from websearch.services.webfetch.complex import service as complex  # noqa: A004
from websearch.services.webfetch.local import service as local
from websearch.services.websearch.cloud import service as websearch_cloud
from websearch.tools.webfetch import webfetch
from websearch.tools.websearch import websearch

# Go: const serverName = "websearch" (main.go:20-22).
SERVER_NAME = "websearch"


def main() -> None:
    """Go ``main`` (main.go:24-38) — row 98's exact wiring ORDER."""
    client = network.new_client(os.environ.get("SOCKS_PROXY", ""))

    # Go: implementation := &mcp.Implementation{Name: serverName, Version:
    # "v1.0.0"}; server := mcp.NewServer(implementation, nil) (main.go:26-30).
    # Row 98 collapses both statements into the constructor kwargs — probed
    # against the pinned mcp 2.3.0: ``Server.__init__(name: str, *, version:
    # str = "", ...)`` derives the serverInfo Implementation from exactly
    # these identity fields. The options argument is OMITTED (nil options ==
    # the SDK's own defaults); ``client`` is always non-None here, which is
    # exactly why both cloud services' DefaultClient fallbacks are
    # production-dead (row 98).
    server = Server(name=SERVER_NAME, version="v1.0.0")

    register_web_search(server, client)
    register_web_fetch(server, client)

    # Go: if err := server.Run(context.Background(), &mcp.StdioTransport{});
    # err != nil { log.Fatal(err) } (main.go:35-37). ctx dropped (§2); the
    # zero-value transport is the SDK's default stdio path (_run_stdio
    # below, row 98). Failure -> SystemExit (row 97): a str-argument
    # SystemExit prints its message to stderr and exits with status 1, the
    # log.Fatal parity the row pins. BaseException (KeyboardInterrupt /
    # SystemExit — the panic/signal analogue) propagates unconverted.
    try:
        asyncio.run(_run_stdio(server))
    except Exception as exc:
        # SAFETY: Go's ``err != nil`` fires on ANY non-nil Run error —
        # transport and session failures alike; ``except Exception`` is its
        # exact mirror, and ``str(exc)`` is the text log.Fatal printed.
        raise SystemExit(str(exc)) from exc


def register_web_search(server: Server[Any], client: httpx.Client) -> None:
    """Go ``RegisterWebSearch`` (main.go:40-49).

    Row 97: each env read yields "" when unset — the Config str fields ride
    Go's zero values into the cloud service (which has no empty-BaseURL
    guard; none is invented here).
    """
    cfg = websearch_cloud.Config(
        base_url=os.environ.get("WEB_SEARCH_BASE", ""),
        api_key=os.environ.get("WEB_SEARCH_API_KEY", ""),
        search_model=os.environ.get("WEB_SEARCH_MODEL", ""),
        http_client=client,
    )
    service = websearch_cloud.new(cfg)
    websearch.register(server, service)


def register_web_fetch(server: Server[Any], client: httpx.Client) -> None:
    """Go ``RegisterWebFetch`` (main.go:51-64) — row 97 env zero-values.

    ``complex.new_web_fetch_service`` wraps the cloud service with the
    unconditional local fallback; Go's alias ``local`` and the constructor
    argument order (cloud first, local second) are verbatim (main.go:58-61).
    """
    cfg = webfetch_cloud.Config(
        base_url=os.environ.get("WEB_FETCH_BASE", ""),
        api_key=os.environ.get("WEB_FETCH_API_KEY", ""),
        fetch_model=os.environ.get("WEB_FETCH_MODEL", ""),
        http_client=client,
    )
    service = complex.new_web_fetch_service(
        webfetch_cloud.new(cfg),
        local.new_web_fetch_service(client),
    )

    webfetch.register(server, service)


# Private (Go inlined this in main: server.Run(ctx, &mcp.StdioTransport{}))


async def _run_stdio(server: Server[Any]) -> None:
    """Serve ``server`` over the process's stdin/stdout.

    The zero-value ``&mcp.StdioTransport{}`` (main.go:35) maps to the SDK's
    default stdio run path (row 98): ``stdio_server()`` with no explicit
    streams serves over anyio stdin/stdout. ``create_initialization_options()``
    with no arguments is the nil-options analogue — the SDK derives the
    serverInfo block and capabilities from the constructor identity — and
    ``raise_exceptions`` stays False (the production default: handler errors
    become JSON-RPC error responses, so Run itself errors only on
    connection-level failures, exactly the errors Go's Run returned).
    """
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    main()


# PORT STATUS: confidence=high todos=0
