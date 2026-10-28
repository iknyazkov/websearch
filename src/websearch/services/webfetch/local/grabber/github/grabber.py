"""GitHub-aware grabber (Go: github/grabber.go).

Translation sites, all decided by this file's inventory rows (26-30) and
followed verbatim:

- Row 26 (CTX): ``ctx`` threaded Grab -> fetch -> NewRequestWithContext and
  Grab -> fallback.Grab is never read; dropped at every hop (§2
  ``context.Context`` row) — ``grab(self, resource)`` and ``fetch(self,
  fetch_url, content_type)``.
- Rows 27/30 (BYTES + NIL-MAKE): the body is read BEFORE close (FF-5), with
  NO size cap (the 5 MB ``maxBodySize`` is client-grabber-only), and the
  Result carries a FRESH single-entry ``parameters`` dict — upstream
  response headers are discarded, only the synthesized Content-Type
  survives, key lowercased per the Parameters convention.
- Row 28 (NIL-ERR): the three regex nil sites become ``if m :=
  PATTERN.match(url)``; the request-construction and transport error checks
  raise as-is; the Go ``io.ReadAll`` error branch evaporates (resp.read()
  already has the bytes per FF-5 mechanics — no dead read-error branch).
- Row 29 (HTTP-REGEX): IsCanGrab compares the USERINFO-STRIPPED authority
  case-preserved; regexes verbatim except ``$`` -> ``\\Z``; fetch sets UA
  Firefox + Accept vnd.github.v3+json only for json; error ``request
  failed with status {code}``.
"""

import re
from urllib.parse import urlsplit

import httpx

from websearch.services.webfetch.local.grabber.client import fingerprint
from websearch.services.webfetch.local.grabber.grabber import ContentGrabber
from websearch.services.webfetch.local.grabber.resource import Resource
from websearch.services.webfetch.local.grabber.result import Result

# Go const block (grabber.go:16-20) — module constants UPPER per house
# style (fingerprint.FIREFOX_UA, client.grabber.MAX_BODY_SIZE).
TEXT_CONTENT_TYPE = "text/plain"
JSON_CONTENT_TYPE = "application/json"
GITHUB_JSON_CONTENT_TYPE = "application/vnd.github.v3+json"

# Go var block (grabber.go:22-26). Pattern text verbatim EXCEPT Go `$` ->
# Python `\Z` (§2 regexp row; rows 28/29): Go's `$` is end-of-text only
# while Python's `$` also matches before a trailing newline — probed
# against the Go binary: `^https?://github\.com/([^/]+)/([^/]+)/?$` nils
# on "https://github.com/o/r/\n" where Python `$` matches and `\Z` nils;
# on "https://github.com/o/r\n" (no slash) both engines match. `re.match`
# (match-at-start) == Go's unanchored FindStringSubmatch over a
# `^`-anchored pattern (row 28). re.ASCII: Go `\d` is ASCII-only (§2); a
# no-op for the two patterns without ASCII classes.
GITHUB_REPO_REGEX = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/?\Z", re.ASCII)
GITHUB_FILE_REGEX = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", re.ASCII
)
GITHUB_ISSUE_REGEX = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)", re.ASCII
)

# Row 29's mirror of Go url.Parse's unescape validation: a `%` not followed
# by two hex digits is rejected in userinfo/host/path/fragment but NOT in
# the raw query (net/url parse keeps RawQuery raw). Probed: path/fragment
# `%zz` reject, query `?q=%zz` accepts, `%2F` accepts — Go-exact.
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)

# Go net/url rejects ANY ASCII control byte in a URL (stringContainsCTLByte:
# b < ' ' || b == 0x7f, checked on the raw string BEFORE parsing), while
# urlsplit STRIPS \t/\r/\n (bpo-43882) and passes every other control byte
# through — the full-set mirror (post-parity fixes F4+F4b, widened after
# adversarial review, 2026-10-28; probed: \x0b/\x0c/\x7f addresses are
# False like Go, a %09-encoded tab stays True in both engines).
_CTL_BYTE = re.compile(r"[\x00-\x1f\x7f]")


class RequestFailedError(Exception):
    """Typed error for the pinned ``request failed with status {code}``
    string (grabber.go:86, fmt.Errorf) — §2 pinned-string convention
    (row 91): one module-level class per pinned message subject, deriving
    Exception.
    Post-parity fix F5, 2026-10-28; the wire message is byte-exact either
    way — the class only narrows what callers/tests can catch.
    """


class GithubGrabber:
    """Grabber routing github.com URLs to the raw/api endpoints.

    Go struct ``GithubGrabber{client *http.Client; fallback
    grabber.ContentGrabber}`` (grabber.go:28-31) — both fields always set
    by the constructor, so non-Optional here (§2's Optional+deref-assert
    shape is for fields that can be nil after zero-value construction;
    these cannot).
    """

    def __init__(self, client: httpx.Client, fallback: ContentGrabber) -> None:
        self.client = client
        self.fallback = fallback

    def is_can_grab(self, resource: Resource) -> bool:
        # Go grabber.go:33-39 — url.Parse error -> False, else Host ==
        # "github.com" | "www.github.com" (row 29's faithful mirror).
        address = resource.address

        # (1) Percent-escape rejection: scan exactly the regions Go's
        # unescape validates — everything before the first `#` MINUS the
        # raw query after the first `?`, PLUS the fragment.
        before_fragment, _, fragment = address.partition("#")
        before_query, _, _raw_query = before_fragment.partition("?")
        if _INVALID_PERCENT_ESCAPE.search(
            before_query
        ) or _INVALID_PERCENT_ESCAPE.search(fragment):
            return False

        # (2) Host comparison on the USERINFO-STRIPPED authority,
        # case-preserved, port INCLUDED (Go url.Host excludes userinfo,
        # keeps port and case, and parseAuthority splits at the LAST `@` —
        # rpartition("@") is its exact mirror; probed: urlsplit("https://
        # user:pass@github.com/o/r").netloc.rpartition("@")[-1] ==
        # "github.com" -> True, while "github.com:443" and "GITHUB.com"
        # stay False like Go). urlsplit raises ValueError on
        # bracket-unmatched netlocs — Go's parseHost error ("missing '['
        # in host") — caught as a parse failure.
        try:
            parts = urlsplit(address)
        except ValueError:
            return False
        _, _, hostport = parts.netloc.rpartition("@")
        # Control chars: Go url.Parse rejects the WHOLE URL on any ASCII
        # control byte ("net/url: invalid control character in URL") while
        # urlsplit strips \t/\r/\n and passes the rest — guard BEFORE the
        # host check so a control-laced address is False like Go
        # (post-parity fixes F4+F4b, 2026-10-28; row 29 residual).
        if _CTL_BYTE.search(address):
            return False
        return hostport in ("github.com", "www.github.com")

    def grab(self, resource: Resource) -> Result:
        # Go grabber.go:41-66. ctx dropped (row 26); (*Result, error)
        # collapses to Result-or-raise (§2). Branch ORDER is load-bearing:
        # file, then repo, then issue, then fallback.
        url_str = resource.address

        if matches := GITHUB_FILE_REGEX.match(url_str):
            owner, repo, ref, path = (
                matches.group(1),
                matches.group(2),
                matches.group(3),
                matches.group(4),
            )
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
            return self.fetch(raw_url, TEXT_CONTENT_TYPE)

        if matches := GITHUB_REPO_REGEX.match(url_str):
            owner, repo = matches.group(1), matches.group(2)
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            return self.fetch(api_url, JSON_CONTENT_TYPE)

        if matches := GITHUB_ISSUE_REGEX.match(url_str):
            owner, repo, typ, num = (
                matches.group(1),
                matches.group(2),
                matches.group(3),
                matches.group(4),
            )
            if typ == "pull":
                typ = "pulls"
            api_url = f"https://api.github.com/repos/{owner}/{repo}/{typ}/{num}"
            return self.fetch(api_url, JSON_CONTENT_TYPE)

        return self.fallback.grab(resource)

    def fetch(self, fetch_url: str, content_type: str) -> Result:
        # Go grabber.go:68-101. ctx dropped (row 26). Request-construction
        # failure (Go :69-72) raises from httpx.Request itself, as-is, no
        # wrapping (row 28: transport-class, unjudged).
        request = httpx.Request("GET", fetch_url)
        # Go grabber.go:74: client.Firefox.Value() — FF-4 pins the Firefox
        # literal; fingerprint.py homes the constant and this file reads it
        # directly (fingerprint row 21's decided convention).
        request.headers["User-Agent"] = fingerprint.FIREFOX_UA
        # Go grabber.go:75-77 — Accept set ONLY on the json branches (repo
        # and issue pass jsonContentType; the file branch gets no Accept).
        if content_type == JSON_CONTENT_TYPE:
            request.headers["Accept"] = GITHUB_JSON_CONTENT_TYPE

        # send(stream=True) keeps the Go Do (:79) / defer Close (:83) /
        # read (:89) order visible in this file with FF-5's
        # read-BEFORE-close ordering (row 27); on the status-error path the
        # body is never read (Go returns before ReadAll) and the finally
        # still closes.
        resp = self.client.send(request, stream=True)
        try:
            # Go grabber.go:85-87 — judge-pinned message (APP_ERROR_RE pins
            # "request failed with status"); ValueError is the codebase
            # raise type for app errors (rows 10/47), only the message is
            # pinned. The Go io.ReadAll error branch (:89-92) evaporates:
            # resp.read() already has the bytes (row 28).
            if resp.status_code != httpx.codes.OK:
                raise RequestFailedError(f"request failed with status {resp.status_code}")

            # Spec-matching quirk (closed post-parity 2026-10-28,
            # document-and-close): the github path has NO size cap — Go's
            # io.ReadAll(resp.Body) at grabber.go:89 is unbounded (the 5 MB
            # maxBodySize exists ONLY in client/grabber.go:13). Repro: a
            # >5 MB raw.githubusercontent.com/api.github.com body is read
            # whole into memory here (and truncated at 5 MB by the client
            # grabber); kept bug-for-bug per row 27.
            data = resp.read()
        finally:
            resp.close()

        # Go grabber.go:94-96 — a FRESH header holding EXACTLY ONE entry:
        # the upstream response headers are discarded entirely, only the
        # synthesized Content-Type survives. Key lowercased per the
        # Parameters convention (row 30; the choice processor looks it up
        # via parameters.get("content-type")); the value is the verbatim
        # literal chosen in grab ("text/plain" file branch,
        # "application/json" repo/issue branches), NOT pre-parsed (media-
        # type parsing is the choice processor's job, FF-6 row).
        parameters = {"content-type": content_type}

        return Result(data=data, parameters=parameters)


# Initialization


def new_grabber(client: httpx.Client, fallback: ContentGrabber) -> ContentGrabber:
    # Go grabber.go:103-105 — constructor return type is the only explicit
    # interface declaration; satisfaction stays structural.
    return GithubGrabber(client=client, fallback=fallback)


# PORT STATUS: confidence=high todos=0
