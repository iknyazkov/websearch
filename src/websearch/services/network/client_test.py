"""TestNewClientSocks5 — SOCKS5 proxy support in new_client (no Go twin).

Go parity context, not a Go port: the pruned spec's makeTransport wired the
HTTPS_PROXY value through http.ProxyURL, and Go's net/http accepts http,
https AND socks5 proxy URL schemes natively — so a ``socks5://`` value was
always legal on the Go side. On the httpx side the same value needs the
``socksio`` package (the ``httpx[socks]`` extra): without it httpx raises
ImportError at CONSTRUCTION time, which the ValueError/InvalidURL degrade
guard in client.py deliberately does NOT swallow — an operator who pinned
egress to a proxy must get a loud startup failure, never a silent fall-back
to direct egress (the NIL-SWALLOW rows cover garbage URLs, not missing
dependencies). This file pins the behavior end to end: a real loop-back
SOCKS5 endpoint (no-auth + CONNECT, the minimum an operator's proxy does),
so the test exercises the actual socksio handshake and the request riding
through the tunnel — not httpx's internal transport classes.
"""

from __future__ import annotations

import socket
import threading

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


def test_socks5_proxy_value_egresses_through_socks5() -> None:
    """``new_client("socks5://…")`` tunnels the request to the URL's host:port.

    The client is built exactly as main.py builds it (HTTPS_PROXY value in,
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
