"""Routing HTTP(S) intercept proxy for the parity judge.

All egress from the binaries under test flows through this proxy
(HTTPS_PROXY env; both implementations honor it by design — see the Go
`internal/services/network/client.go` and its Python port).

Two request shapes are handled:

  * absolute-form  `GET http://host/path HTTP/1.1`  (plain-http URLs) — the
    proxy serves the canned response itself: full request/response visibility.
  * `CONNECT host:443` (https URLs) — recorded as a routing signal, then the
    tunnel is acknowledged and closed. TLS interception is impossible for the
    Go reference binary on darwin (env CAs are rejected in every build
    variant), so both sides get the identical treatment: the https attempt
    fails as a transport error, and only the CONNECTED HOST is observable.

Every proxied request is recorded: (host, method, target, selected headers,
body). Scenarios assert on the record (routing decisions, User-Agent,
Accept); responses come from a per-scenario route table.

Route table: dict host -> handler(request) -> (status, headers, body_bytes).
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field

MAX_LINE = 65536
MAX_BODY = 8 * 1024 * 1024

# Headers worth asserting on; everything else is transport noise.
RECORDED_HEADERS = ("user-agent", "accept", "content-type", "authorization")


@dataclass
class RecordedRequest:
    host: str
    method: str
    target: str  # path (or full absolute-form URL as sent)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def key(self) -> dict:
        return {
            "host": self.host,
            "method": self.method,
            "target": self.target,
            "headers": dict(sorted(self.headers.items())),
            "body": self.body.decode("utf-8", "replace"),
        }


class JudgeProxy:
    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.records: list[RecordedRequest] = []
        self.errors: list[str] = []  # transport-layer failures; gate the scenario
        self.idle_timeouts: list[str] = []  # benign: keep-alive sockets closing
        self._lock = threading.Lock()
        self._active = 0  # handler threads currently mid-request
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def reset(self, routes: dict[str, object]) -> None:
        """Install the route table for one scenario and clear the record log.

        Quiesces first: waits (bounded) for in-flight handler threads from the
        previous observation, so a slow request cannot contaminate the next
        scenario's records."""
        deadline = 2.0
        waited = 0.0
        while waited < deadline:
            with self._lock:
                if self._active == 0:
                    break
            time.sleep(0.01)
            waited += 0.01
        with self._lock:
            self.routes = dict(routes)
            self.records = []

    def requests(self) -> list[dict]:
        with self._lock:
            return [r.key() for r in self.records]

    def stop(self) -> None:
        self._stop.set()
        self._sock.close()

    # ---------------------------------------------------------------- serving

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(30)
            with self._lock:
                self._active += 1
            first = self._read_request_head(conn)
            if first is None:
                conn.close()
                return
            method, target, headers, body = first
            if method == "CONNECT":
                host = target.rsplit(":", 1)[0]
                self._tunnel(conn, host)
            else:
                # absolute-form: http://host:port/path
                host = target.split("/")[2] if "://" in target else "unknown"
                self._serve_plain(conn, host, method, target, headers, body)
        except Exception as exc:  # noqa: BLE001 - record, never crash the proxy
            with self._lock:
                if isinstance(exc, socket.timeout):
                    # benign: an idle keep-alive connection timing out after
                    # its scenario finished — not a judge failure
                    self.idle_timeouts.append(f"{type(exc).__name__}: {exc}")
                else:
                    self.errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._active -= 1
            try:
                conn.close()
            except OSError:
                pass

    def _tunnel(self, conn: socket.socket, host: str) -> None:
        """CONNECT handling: record the routing signal, acknowledge, close.

        Go on darwin rejects env-provided CAs in every build variant (proven
        empirically during judge setup), so TLS interception is off the table
        for the reference binary — and the judge must treat both binaries
        alike. The CONNECT target host is itself the observable: which
        upstream the implementation chose to contact. The tunnel then fails
        identically for both sides; norm_call canonicalizes the resulting
        transport error text to a class.
        """
        rec = RecordedRequest(host=host, method="CONNECT", target="")
        with self._lock:
            self.records.append(rec)
        try:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        except OSError:
            pass
        # deliberate close: TLS handshake cannot succeed, for either side

    def _serve_plain(self, conn: socket.socket, host: str, method: str, target: str,
                     headers: dict[str, str], body: bytes) -> None:
        self._record_and_respond(conn, host, method, target, headers, body)
        # keep-alive loop for further absolute-form requests on this connection
        while True:
            nxt = self._read_request_head(conn)
            if nxt is None:
                return
            m, t, h, b = nxt
            h2 = t.split("/")[2] if "://" in t else host
            self._record_and_respond(conn, h2, m, t, h, b)

    def _record_and_respond(self, sock: socket.socket, host: str, method: str,
                            target: str, headers: dict[str, str], body: bytes) -> bool:
        rec = RecordedRequest(host=host, method=method, target=target)
        for name, value in headers.items():
            if name.lower() in RECORDED_HEADERS:
                rec.headers[name.lower()] = value
        rec.body = body
        with self._lock:
            self.records.append(rec)
        status, resp_headers, resp_body = self._route(host, method, target, headers, body)
        reason = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request",
                  401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
                  429: "Too Many Requests", 500: "Internal Server Error",
                  502: "Bad Gateway", 503: "Service Unavailable"}.get(status, "Status")
        head = f"HTTP/1.1 {status} {reason}\r\n"
        all_headers = dict(resp_headers)
        all_headers.setdefault("Content-Length", str(len(resp_body)))
        all_headers.setdefault("Connection", "keep-alive")
        for name, value in all_headers.items():
            head += f"{name}: {value}\r\n"
        try:
            sock.sendall(head.encode() + b"\r\n" + resp_body)
        except OSError:
            return False
        return True

    def _route(self, host: str, method: str, target: str,
               headers: dict[str, str], body: bytes) -> tuple[int, dict[str, str], bytes]:
        with self._lock:
            handler = self.routes.get(host)
        if handler is None:
            return 404, {"Content-Type": "text/plain"}, b"no route for host"
        result = handler(method, target, headers, body)
        return result

    # ------------------------------------------------------------------ parsing

    @staticmethod
    def _read_request_head(sock: socket.socket) -> tuple[str, str, dict[str, str], bytes] | None:
        buf = b""
        while b"\r\n\r\n" not in buf:
            if len(buf) > MAX_LINE:
                return None
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) < 3:
            return None
        method, target = parts[0], parts[1]
        headers: dict[str, str] = {}
        lower: dict[str, str] = {}  # wire casing varies (Go canonical, httpx lowercase)
        for line in lines[1:]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip()] = value.strip()
                lower[name.strip().lower()] = value.strip()
        if "chunked" in lower.get("transfer-encoding", ""):
            body = JudgeProxy._read_chunked(sock, rest)
        else:
            length = int(lower.get("content-length", "0") or 0)
            body = rest
            while len(body) < length:
                if len(body) > MAX_BODY:
                    return None
                chunk = sock.recv(min(65536, length - len(body)))
                if not chunk:
                    break
                body += chunk
            body = body[:length]
        return method, target, headers, body

    @staticmethod
    def _read_chunked(sock: socket.socket, initial: bytes) -> bytes:
        """Decode a chunked request body (Transfer-Encoding: chunked)."""
        buf = initial
        body = b""
        while True:
            while b"\r\n" not in buf:
                buf += sock.recv(4096)
            size_line, _, buf = buf.partition(b"\r\n")
            try:
                size = int(size_line.split(b";")[0].strip(), 16)
            except ValueError:
                return body
            if size == 0:
                return body
            while len(buf) < size + 2:
                buf += sock.recv(min(65536, size + 2 - len(buf)))
            body += buf[:size]
            if len(body) > MAX_BODY:
                return body
            buf = buf[size + 2:]  # skip chunk + trailing CRLF
