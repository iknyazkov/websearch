"""Port of internal/services/webfetch/local/grabber/github/grabber_test.go.

Go's in-package test file (package github) covers the github grabber's host
gate (TestIsCanGrab), URL routing + wire headers (TestGrabRoutesGithubURLs),
the regex-miss fallback (TestGrabFallsBackForUnsupportedGithubURL), and the
fetch status/body contract (TestFetch, TestFetchReturnsClientError).
Inventory rows 31-40 decide this file; the rows win over general rules.

Mapping decisions, per row:

- Row 39 (TEST-DOUBLE): Go's ``roundTripFunc`` transport double is DROPPED —
  ``httpx.MockTransport(handler)`` IS the double. The handler runs
  synchronously inside ``grab``'s ``client.send`` and captures the outgoing
  request, mirroring ``gotReq`` at grabber_test.go:54-62; headers are read
  case-insensitively and the URL as ``str(request.url)``.
- Row 31 (TEST-HTTP; conflict C-7): ``httptest.NewServer`` + ``defer
  srv.Close()`` is REPLACED by the MockTransport double (deterministic, no
  sockets, no close); the fetch URL is the arbitrary absolute
  ``http://testserver/x`` — the transport is a mock, only the absolute-http
  fetch contract is exercised.
- Row 38 (CTX): every ``context.Background()`` call site drops ctx — the
  ported ``grab``/``fetch`` take none (§2 context row).
- Rows 35/40 (NIL-TEST zero values): ``g := &GithubGrabber{}`` (:28) ->
  ``GithubGrabber(client=None, fallback=None)``; the nil ``fallback`` of
  :120/:143-146 -> ``fallback=None``. The Nones pin that ``is_can_grab`` and
  ``fetch`` never touch those fields. The ported grabber types both fields
  non-Optional (its ``new_grabber`` always sets them), so each None argument
  carries a §3 ``type: ignore[arg-type]`` with a SAFETY line — the row-pinned
  zero-value construction is not fixable from the test side.
- Row 34 (TEST-FIX-FF4): Go's stale ``User-Agent != "websearch/1.0"``
  assertion is corrected in the port — the source sends
  ``client.Firefox.Value()`` (grabber.go:74), which FF-4 pins to the Firefox
  literal below; the Go literal matches nothing in the source tree.
- Row 36 (TEST-FILE): absolute imports only (never relative, never star);
  ``ContentGrabber`` is NOT imported — the port never names it, the fakes are
  checked structurally at the ``fallback=`` argument.
"""

import httpx2 as httpx
import pytest

from websearch.services.webfetch.local.grabber.github.grabber import (
    GithubGrabber,
    RequestFailedError,
)
from websearch.services.webfetch.local.grabber.resource import Resource
from websearch.services.webfetch.local.grabber.result import Result

# FF-4 (rulebook §0) byte-exact literal, asserted instead of Go's stale
# "websearch/1.0" (row 34) — same constant the grabber sends via
# fingerprint.FIREFOX_UA (github/grabber.go:74). Spelled inline, not
# imported, so a wrong constant in fingerprint.py cannot self-validate.
FIREFOX_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0"


@pytest.mark.parametrize(
    ("address", "want"),
    [
        pytest.param(
            "https://github.com/owner/repo", True, id="https://github.com/owner/repo"
        ),
        pytest.param(
            "http://github.com/owner/repo", True, id="http://github.com/owner/repo"
        ),
        pytest.param(
            "https://www.github.com/owner/repo",
            True,
            id="https://www.github.com/owner/repo",
        ),
        pytest.param(
            "https://gitlab.com/owner/repo", False, id="https://gitlab.com/owner/repo"
        ),
        pytest.param("%zz", False, id="%zz"),
    ],
)
def test_is_can_grab(address: str, want: bool) -> None:
    # Go grabber_test.go:28 — zero-value &GithubGrabber{}; is_can_grab must
    # touch neither field (rows 35/40), so the Go zero value ports as None.
    # SAFETY: Go zero-value construction (grabber_test.go:28); is_can_grab,
    # the only method called here, reads neither client nor fallback, so the
    # Nones are never dereferenced (rows 35/40).
    g = GithubGrabber(client=None, fallback=None)  # type: ignore[arg-type]
    got = g.is_can_grab(Resource(address=address))
    assert got == want


@pytest.mark.parametrize(
    ("address", "want_url", "want_type", "want_accept"),
    [
        pytest.param(
            "https://github.com/owner/repo/blob/main/path/to/file.go",
            "https://raw.githubusercontent.com/owner/repo/main/path/to/file.go",
            "text/plain",
            None,
            id="https://github.com/owner/repo/blob/main/path/to/file.go",
        ),
        pytest.param(
            "https://github.com/owner/repo",
            "https://api.github.com/repos/owner/repo",
            "application/json",
            "application/vnd.github.v3+json",
            id="https://github.com/owner/repo",
        ),
        pytest.param(
            "https://github.com/owner/repo/issues/123",
            "https://api.github.com/repos/owner/repo/issues/123",
            "application/json",
            "application/vnd.github.v3+json",
            id="https://github.com/owner/repo/issues/123",
        ),
        pytest.param(
            "https://github.com/owner/repo/pull/456",
            "https://api.github.com/repos/owner/repo/pulls/456",
            "application/json",
            "application/vnd.github.v3+json",
            id="https://github.com/owner/repo/pull/456",
        ),
    ],
)
def test_grab_routes_github_urls(
    address: str, want_url: str, want_type: str, want_accept: str | None
) -> None:
    # Go grabber_test.go:39-83 — the four routing rows verbatim, t.Run(
    # tt.address) -> id=address (row 33). The double captures the outgoing
    # request and answers a buffered 200 "body" (row 39; the port's fetch
    # reads resp.content so the io.NopCloser dance disappears).
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, content=b"body")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fallback = FakeGrabber()
    g = GithubGrabber(client=client, fallback=fallback)

    got = g.grab(Resource(address=address))

    # Go :69-71 — the rewritten URL the transport actually saw.
    assert str(captured["request"].url) == want_url
    # Go :72-74 STALE ("websearch/1.0" matches nothing) — FF-4 fixes the
    # assertion to the literal the source sends on EVERY fetch (row 34).
    assert captured["request"].headers["user-agent"] == FIREFOX_UA
    # Go :75-77 — Header.Get("Accept") returns "" for the unset header; the
    # port is send()-based (a bare httpx.Request gets NO client defaults,
    # probed), so the unset header is None — exactly Go's distinction. The
    # vnd-header-iff-json-route contract is the source invariant
    # (grabber.go:75-77; row 33).
    assert captured["request"].headers.get("accept") == want_accept
    # Go :78-80 — Parameters.Get("Content-Type") on the SYNTHESIZED type;
    # the port stores it under the lowercased key (row 33; result.py).
    assert got.parameters["content-type"] == want_type
    # Row 33: all four rows route to fetch, never to fallback.
    assert fallback.calls == 0


def test_grab_falls_back_for_unsupported_github_url() -> None:
    # Go grabber_test.go:85-99 — /tree/main is a regex miss, so grab returns
    # g.fallback.Grab(...) as-is: exactly one call, result object identical
    # (grabber.go:65). Result(data=bytes, parameters=dict) mirrors
    # Reader: bytes.NewReader(...) + Parameters: http.Header (row 37).
    fallback = FakeGrabber(result=Result(data=b"fallback", parameters={}))
    g = GithubGrabber(client=httpx.Client(), fallback=fallback)

    got = g.grab(Resource(address="https://github.com/owner/repo/tree/main"))

    assert fallback.calls == 1
    assert got is fallback.result


@pytest.mark.parametrize(
    ("name", "status", "body", "want_err"),
    [
        pytest.param("ok", 200, "plain text", False, id="ok"),
        pytest.param("not-found", 404, "", True, id="not-found"),
    ],
)
def test_fetch(name: str, status: int, body: str, want_err: bool) -> None:
    # Go grabber_test.go:101-140 — httptest.NewServer replaced by the
    # MockTransport double (row 31; C-7): the handler answers tt.status +
    # tt.body, no sockets, no srv.Close.
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    # Go :120 — &GithubGrabber{client: srv.Client()} leaves fallback nil.
    # SAFETY: Go :120 constructs the grabber with a NIL fallback; fetch, the
    # only method called here, never touches it, so the None is never
    # dereferenced (rows 31/40).
    g = GithubGrabber(
        client=httpx.Client(transport=transport),
        fallback=None,  # type: ignore[arg-type]
    )

    if want_err:
        # Go :122-127 — err != nil only; the port pins the byte-exact
        # message (grabber.go:86; APP_ERROR_RE pins "request failed with
        # status"). The class is the §2 typed error (post-parity fix F5,
        # 2026-10-28): match-on-message AND match-on-type.
        with pytest.raises(RequestFailedError, match=rf"^request failed with status {status}$"):
            g.fetch("http://testserver/x", "text/plain")
        return

    # Go :128-137 — the io.ReadAll(got.Reader) dance disappears: Result
    # carries bytes (row 31), so tt.body compares against got.data.
    got = g.fetch("http://testserver/x", "text/plain")
    assert got.data == body.encode()


def test_fetch_returns_client_error() -> None:
    # Go grabber_test.go:142-152 — the transport error must surface
    # UNWRAPPED (grabber.go:79-82 returns it as-is), so errors.Is becomes
    # an identity check; MockTransport propagates handler exceptions
    # untouched (probed), which is exactly the error path (row 32).
    want_err = RuntimeError("boom")

    def handler(request: httpx.Request) -> httpx.Response:
        raise want_err

    # Go :143-146 — &GithubGrabber{client: ...} leaves fallback nil.
    # SAFETY: Go :143-146 constructs the grabber with a NIL fallback; fetch,
    # the only method called here, never touches it, so the None is never
    # dereferenced (rows 32/40).
    g = GithubGrabber(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        fallback=None,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError) as excinfo:
        g.fetch("https://api.github.com/repos/owner/repo", "application/json")
    assert excinfo.value is want_err


class FakeGrabber:
    """mockGrabber double (Go grabber_test.go:160-172), duck-typed — no
    inheritance, structural satisfaction of the ContentGrabber Protocol at
    the fallback= argument (rows 36/37).

    Go returns ``(m.result, nil)`` where result may be nil — the only
    ``(nil, nil)`` success return in the tree; the port's mock returns
    ``self.result`` (may be None), so ``__init__`` takes ``Result | None``
    and ``grab`` asserts it is set before returning it (row 40).
    """

    def __init__(self, result: Result | None = None) -> None:
        self.calls = 0
        self.result = result

    def is_can_grab(self, resource: Resource) -> bool:
        # Go :165-167 — always False.
        return False

    def grab(self, resource: Resource) -> Result:
        # Go :169-172 — count the call, return the canned result; ctx
        # dropped (row 38).
        self.calls += 1
        assert self.result is not None
        return self.result


# PORT STATUS: confidence=high todos=0
