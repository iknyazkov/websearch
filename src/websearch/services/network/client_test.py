"""new_client's SOCKS_PROXY contract — SOCKS-only proxying (no Go twin).

Go parity context, not a Go port: the pruned spec's makeTransport wired its
proxy value through http.ProxyURL, and Go's net/http accepts http, https AND
socks5 proxy URL schemes natively. The port moved to a single SOCKS_PROXY
variable (2026-10-30): the value is socks5/socks5h or empty — nothing else
— and every value that cannot be honored as a SOCKS proxy fails LOUDLY at
construction (ValueError here, or httpx's ImportError without the
``socksio`` package / InvalidURL on a URL httpx rejects), never a silent
fall-back to direct egress. The tunnel legs are pinned end to end against a
real loop-back SOCKS5 endpoint (no-auth + CONNECT, the minimum an operator's
proxy does), so the tests exercise the actual socksio handshake and the
request riding through the tunnel — not httpx's internal transport classes.
"""

from __future__ import annotations

import socket
import threading

import pytest

from websearch.services.network.client import new_client


class _Socks5Endpoint:
    """One-shot loop-back SOCKS5 server: accept, greet, CONNECT, serve HTTP.

    Speaks RFC 1928 far enough to be a proxy for a single connection:
    method negotiation (reply NO AUTHENTICATION), a CONNECT request (reply
    success with the zero all-binds address), then the tunneled bytes —
    which for a plain-http origin are the origin's HTTP request, answered
    with a canned 200. Records what crossed the wire so the test can assert
    the client really tunneled to the URL's host:port.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._sock.settimeout(10)
        self.port = self._sock.getsockname()[1]
        self.connect_target: tuple[str, int] | None = None
        self.request_line: bytes | None = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> _Socks5Endpoint:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        # The thread exits on its own after one connection (or times out);
        # join first so `self.error` is settled before the assertion runs.
        self._thread.join(timeout=10)
        self._sock.close()

    def _serve(self) -> None:
        try:
            conn, _ = self._sock.accept()
            with conn:
                conn.settimeout(10)
                # Greeting: VER NMETHODS METHODS... -> NO AUTHENTICATION.
                header = self._recv_exact(conn, 2)
                self._recv_exact(conn, header[1])
                conn.sendall(b"\x05\x00")
                # Request: VER CMD RSV ATYP ADDR PORT. Only CMD=1 (CONNECT)
                # is accepted; the address is IPv4 (ATYP 1), DOMAINNAME
                # (ATYP 3), or IPv6 (ATYP 4) — all parsed, all answered the
                # same way, since the assertion below keys off the parsed
                # value rather than the wire encoding.
                req = self._recv_exact(conn, 4)
                atyp = req[3]
                if atyp == 1:
                    addr = ".".join(str(b) for b in self._recv_exact(conn, 4))
                elif atyp == 3:
                    length = self._recv_exact(conn, 1)[0]
                    addr = self._recv_exact(conn, length).decode()
                elif atyp == 4:
                    addr = socket.inet_ntop(socket.AF_INET6, self._recv_exact(conn, 16))
                else:
                    raise AssertionError(f"unknown SOCKS5 ATYP {atyp}")
                port = int.from_bytes(self._recv_exact(conn, 2), "big")
                self.connect_target = (addr, port)
                # BND.ADDR 0.0.0.0:0 — "assigned by the proxy", which for
                # this endpoint is itself: the tunnel dead-ends here and the
                # origin's HTTP is served directly on the same socket.
                conn.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + (0).to_bytes(2, "big"))
                # The tunneled origin request — read the full headers (the
                # body-less GET fits in one recv after the loop's first
                # chunk), answer with the body the test asserts on.
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                self.request_line = buf.split(b"\r\n", 1)[0]
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nhi")
        # SAFETY: the thread must never die silently — a daemon thread's
        # exception would otherwise vanish and the test would fail on the
        # missing assertion evidence instead of the real cause. Everything
        # (socket timeouts included) is captured and re-raised in the main
        # thread via the `endpoint.error` assertion.
        except BaseException as exc:  # noqa: BLE001
            self.error = exc

    @staticmethod
    def _recv_exact(conn: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise AssertionError(f"peer closed after {len(buf)}/{n} bytes")
            buf += chunk
        return buf


class _HttpEndpoint:
    """One-shot loop-back plain-HTTP origin: accept, read headers, answer 200.

    The direct-egress counterpart of ``_Socks5Endpoint``: no handshake, the
    request bytes ARE the origin's HTTP request. A client that somehow mounts
    a proxy for an empty SOCKS_PROXY value would never reach it (there is no
    SOCKS listener to answer the handshake), so a 200 here pins direct
    egress, not transport plumbing.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._sock.settimeout(10)
        self.port = self._sock.getsockname()[1]
        self.request_line: bytes | None = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> _HttpEndpoint:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._thread.join(timeout=10)
        self._sock.close()

    def _serve(self) -> None:
        try:
            conn, _ = self._sock.accept()
            with conn:
                conn.settimeout(10)
                buf = b""
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                self.request_line = buf.split(b"\r\n", 1)[0]
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nhi")
        except BaseException as exc:  # noqa: BLE001
            self.error = exc


def test_socks5_proxy_value_egresses_through_socks5() -> None:
    """``new_client("socks5://…")`` tunnels the request to the URL's host:port.

    The client is built exactly as main.py builds it (SOCKS_PROXY value in,
    all-scheme proxying), pointed at a loop-back SOCKS5 endpoint, and asked
    for a plain-http URL whose port has no listener — the only way the
    response can arrive is through the proxy, and the only way the endpoint
    can know the URL's port is the CONNECT request, so both assertions pin
    tunneled egress rather than transport plumbing.
    """
    with _Socks5Endpoint() as endpoint:
        client = new_client(f"socks5://127.0.0.1:{endpoint.port}")
        # Per-request timeout only: new_client pins timeout=None (Go parity),
        # and a handshake bug must fail the test, not hang it.
        response = client.get("http://127.0.0.1:65501/hello?x=1", timeout=10)
        client.close()

    assert endpoint.error is None
    assert response.status_code == 200
    assert response.text == "hi"
    # CONNECT carried the request URL's host and port (ATYP IPv4).
    assert endpoint.connect_target == ("127.0.0.1", 65501)
    # The origin request itself rode the tunnel.
    assert endpoint.request_line == b"GET /hello?x=1 HTTP/1.1"


def test_socks5h_proxy_value_sends_the_hostname_through_the_proxy() -> None:
    """``new_client("socks5h://…")`` hands the HOSTNAME to the proxy, unresolved.

    ``socks5h`` means DNS through the proxy: httpx must ship the URL's
    hostname in the CONNECT request without a local getaddrinfo. The probe
    URL uses the RFC 2606 reserved ``.invalid`` TLD — resolvable nowhere — so
    the only way the endpoint can see the hostname (and the only way the 200
    arrives) is the proxy carrying name resolution. A local-DNS
    implementation (plain ``socks5`` behavior) fails the request instead.
    """
    with _Socks5Endpoint() as endpoint:
        client = new_client(f"socks5h://127.0.0.1:{endpoint.port}")
        response = client.get("http://never-resolved.invalid:65502/hello", timeout=10)
        client.close()

    assert endpoint.error is None
    assert response.status_code == 200
    assert response.text == "hi"
    # CONNECT carried the unresolved hostname (ATYP DOMAINNAME) and the URL's port.
    assert endpoint.connect_target == ("never-resolved.invalid", 65502)
    assert endpoint.request_line == b"GET /hello HTTP/1.1"


def test_empty_proxy_value_egresses_direct() -> None:
    """``new_client("")`` mounts no proxy: the request reaches the origin itself.

    The unset/empty leg of the SOCKS_PROXY contract — direct egress, the
    zero-value Go parity (client.go:24-26). Asserted against a real origin so
    the test fails if "" ever stops building a working client.
    """
    with _HttpEndpoint() as origin:
        client = new_client("")
        response = client.get(f"http://127.0.0.1:{origin.port}/hello?x=1", timeout=10)
        client.close()

    assert origin.error is None
    assert response.status_code == 200
    assert response.text == "hi"
    assert origin.request_line == b"GET /hello?x=1 HTTP/1.1"


@pytest.mark.parametrize(
    "proxy",
    [
        # The removed HTTP-proxy leg, both spellings.
        "http://127.0.0.1:3128",
        "https://127.0.0.1:3128",
        # SOCKS, but not a supported version.
        "socks4://127.0.0.1:1080",
        # Scheme-less: urlparse reads the pre-colon token as the scheme
        # ("localhost"), so it lands here, not in the parse-failure path.
        "localhost:1080",
    ],
)
def test_non_socks_proxy_value_raises_at_construction(proxy: str) -> None:
    """Any set-but-non-SOCKS proxy value fails loudly at startup, ValueError.

    SOCKS_PROXY is the only proxy contract (2026-10-30): an operator who
    pinned egress must never get silent direct egress — nor a silently
    honored HTTP proxy — for a value outside the socks5/socks5h set. This
    replaces the old NIL-SWALLOW degrade legs, which existed for Go-parity on
    a scheme-dispatching HTTPS_PROXY the port no longer has.
    """
    with pytest.raises(ValueError, match="socks5"):
        new_client(proxy)
