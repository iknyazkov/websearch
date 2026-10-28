"""Parity judge for the websearch MCP server (Go -> Python migration).

Drives two MCP server binaries (the Go original and, later, the Python port)
through their only public surface — newline-delimited JSON-RPC over stdio —
under identical, fully intercepted network conditions, and diffs the results.

Every scenario produces an *observation* per binary:
    { "responses": [...], "proxy_requests": [...] }
Invariants (spec semantics) are asserted on each binary's observation; the
parity diff compares old-vs-new observations after normalization.

Exit status: 0 iff every scenario passes invariants on both binaries AND
old-vs-new observations do not diverge.

Usage (see run.py): harness.Judge(old_bin, new_bin).run()
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import re
import subprocess
import threading

from proxy import JudgeProxy

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

FIREFOX_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
# FF-4 (RULEBOOK §0): the port's Firefox fingerprint is this real current UA.
FF4_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) "
          "Gecko/20100101 Firefox/158.0")
CLIENT_ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8;text/plain")

# PINNED FIXED-SPEC CONTENT (RULEBOOK §0 FIX-FORWARD, FF-5/FF-6). Captured
# empirically from the fixedGo conformance binary (bin/websearch-fixedgo,
# built by fixedgo.py; evidence: amendments-capture.json) — never hand-
# derived. Lengths are Go byte lengths; note S06 is multibyte (41 chars /
# 48 bytes — the byte-vs-char trap is observable here), and S07 embeds the
# goquery selector-list quirk: a <code> nested inside a matched <p> is
# emitted as its own node right after the paragraph (no separator).
PLAINTEXT_TEXT = "héllo wörld — déjà vu ✓ plain text body\n"
PLAINTEXT_LEN = 48
RICH_HTML_TEXT = ('# Rich Fixture Page\n\n> A meta description for the rich '
                  'fixture page\n\n# Main Heading One\n\nThis is the first '
                  'paragraph of the main article content and it is long '
                  'enough to survive.\n\n## Section Heading Two\n\nA paragraph '
                  'with inline_code_marker inside it that stays long enough '
                  'to keep.\n\n`inline_code_marker`List item one is '
                  'sufficiently long to be included in the output text\n\n'
                  'List item two is also sufficiently long to be included as '
                  'well\n\nQuoted material block that is long enough to appear '
                  'in extracted text\n\n### Subsection Heading Three\n\n'
                  '```\ndef fixture_function():\n    return "block code '
                  'content that is long"\n```\n\n#### Minor Heading Four')
RICH_HTML_LEN = 639
CP1251_TEXT = ('# Кодировка Страница\n\n# Главный Заголовок Страницы\n\n'
               'Первый абзац текста на русском языке достаточно длинный для '
               'выборки.\n\nВторой абзац текста тоже достаточно длинный для '
               'проверки декодирования.')
CP1251_LEN = 354
FAILOVER_HTML_TEXT = ('# Failover Local Page\n\n# Local Failover Heading\n\n'
                      'Cloud fetch failed so this local page content is what '
                      'the tool must return here.')
FAILOVER_HTML_LEN = 129

# Divergence markers for the side-aware waivers (below). Old literals map to
# the marker on the OLD side, fixed literals on the NEW side — anything else
# (a port emitting the OLD value, or a third value) stays literal and
# diverges. A waiver can never become a free pass.
M_TITLE_KEY = "<TITLE-KEY>"
M_UA = "<UA-FIXED>"
M_CONTENT = "<FIXED-CONTENT>"
M_AUTH = "<AUTH-EMPTY-KEY>"

# Exact tool descriptions, captured from the reference binary (they are the
# templates in tools/websearch/prompt.go + tools/webfetch/prompt.go with
# agentName="Agent"; only the month-year is volatile). s01 compares these
# byte-for-byte after month-year normalization.
WEBSEARCH_DESCRIPTION = """
- Allows Agent to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks, including links as markdown hyperlinks
- Use this tool for accessing information beyond Agent's knowledge cutoff
- Searches are performed automatically within a single API call

CRITICAL REQUIREMENT - You MUST follow this:
  - After answering the user's question, you MUST include a "Sources:" section at the end of your response
  - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: [Title](URL)
  - This is MANDATORY - never skip including sources in your response
  - Example format:

    [Your answer here]

    Sources:
    - [Source Title 1](https://example.com/1)
    - [Source Title 2](https://example.com/2)

Usage notes:
  - Domain filtering is supported to include or block specific websites

IMPORTANT - Use the correct year in search queries:
  - The current month is <MONTH-YEAR>. You MUST use this year when searching for recent information, documentation, or current events.
  - Example: If the user asks for "latest React docs", search for "React documentation" with the current year, NOT last year
\t"""

WEBFETCH_DESCRIPTION = """
- Fetches content from a specified URL and processes it using an AI model
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Processes the content with the prompt using a small, fast model
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

### Usage notes:
- The URL must be a fully-formed valid URL
- HTTP URLs will be automatically upgraded to HTTPS
- This tool is read-only and does not modify any files
- Results may be summarized if the content is very large
- Includes a self-cleaning 15-minute cache for faster responses when repeatedly accessing the same URL
- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).
\t"""

# Transport-failure error text is runtime-shaped (Go's net/http vs Python's
# requests/httpx format failures differently) and is NOT spec. Canonicalized
# to a class; everything else — our own error strings — is compared exactly.
# The tunnel-close race in the CONNECT path surfaces nondeterministically as
# EOF, handshake failure, or a reset mid-read — the `read tcp`/`write tcp`
# forms embed a random local port, which alone would make runs incomparable.
# `(?<!unexpected )EOF` keeps Go's io.ErrUnexpectedEOF ("unexpected EOF" —
# an upstream PAYLOAD decode failure, not transport) out of the class.
TRANSPORT_ERROR_RE = re.compile(
    r"((?<!unexpected )EOF|tls:|proxyconnect|connection refused|Client\.Timeout|"
    r"unsupported protocol|lookup |handshake|SSLError|HTTPSConnectionPool|"
    r"Max retries|bad certificate|RemoteDisconnected|ConnectionReset|"
    r"SSLCertVerificationError|connection reset|broken pipe|read tcp|write tcp|"
    r"i/o timeout|timed out|server disconnected|connect call failed|"
    r"server closed idle connection|context deadline exceeded)", re.IGNORECASE)

# The application's OWN error strings (grep-verified complete against the Go
# source): these are spec and always compare exactly — even when their text
# embeds something a transport pattern would match (e.g. "web fetch failed:"
# embeds the upstream response body). An error that matches NEITHER an app
# prefix nor a transport pattern also compares exactly.
APP_ERROR_RE = re.compile(
    r"^(query must not be empty|URL must be fully-formed|search request failed:|"
    r"web fetch failed:|HTTP \d+:|request failed with status)", re.IGNORECASE)

# Virtual upstream hosts (all egress lands in the judge proxy; cloud stubs are
# plain http — env-configured — so requests are fully visible in absolute-form):
SEARCH_HOST = "search.test"     # WEB_SEARCH_BASE=http://search.test
FETCH_HOST = "fetch.test"       # WEB_FETCH_BASE=http://fetch.test


# --------------------------------------------------------------------------
# MCP stdio client
# --------------------------------------------------------------------------

class MCPClient:
    def __init__(self, binary: str, env: dict[str, str]) -> None:
        self.proc = subprocess.Popen(
            [binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        self._pending: dict[int, queue.Queue] = {}
        self.notifications: list[dict] = []
        self.dropped: list[str] = []  # stdout noise / late responses: judged
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self.dropped.append(f"unparseable: {line[:80]}")
                continue
            msg_id = msg.get("id")
            if msg_id is not None and "result" in msg or msg_id is not None and "error" in msg:
                with self._lock:
                    q = self._pending.pop(msg_id, None)
                if q is not None:
                    q.put(msg)
                else:
                    self.dropped.append(f"late/dupe id {msg_id}")
                continue
            self.notifications.append(msg)  # server->client notifications, kept for debug

    def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        with self._lock:
            self._next_id += 1
            msg_id = self._next_id
            q: queue.Queue = queue.Queue()
            self._pending[msg_id] = q
        request: dict = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            request["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": "judge: timeout"}}

    def notify(self, method: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def initialize(self) -> dict:
        resp = self.call("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "parity-judge", "version": "0.0.0"},
        })
        self.notify("notifications/initialized")
        return resp

    def tools_list(self) -> dict:
        return self.call("tools/list", {})

    def tools_call(self, name: str, arguments: dict) -> dict:
        return self.call("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - teardown fallback: kill it
            self.proc.kill()


# --------------------------------------------------------------------------
# Normalization — the judge's documented tolerance rules.
# Anything not listed here is compared EXACTLY. Add a rule only with a reason
# that holds for both SDKs; every rule weakens the judge, reviewers check them.
# --------------------------------------------------------------------------

MONTH_YEAR_RE = re.compile(r"\b[A-Z][a-z]{2} 20\d{2}\b")


def norm_description(text: str) -> str:
    """WebSearch's description embeds the current month-year; normalize it."""
    return MONTH_YEAR_RE.sub("<MONTH-YEAR>", text)


def norm_schema(node: object) -> object:
    """Normalize a JSON-Schema node across SDK dialects:
    drop $schema; sort `required` (declaration order is cosmetic); sort list
    types (["null","array"] vs ["array","null"]). Everything else compared."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$schema":
                continue
            if key == "required" and isinstance(value, list):
                out[key] = sorted(value)
                continue
            if key == "type" and isinstance(value, list):
                out[key] = sorted(value)
                continue
            out[key] = norm_schema(value)
        return out
    if isinstance(node, list):
        return [norm_schema(item) for item in node]
    return node


def norm_tools_list(resp: dict) -> dict:
    tools = resp.get("result", {}).get("tools", [])
    out = []
    for tool in tools:
        raw_desc = tool.get("description", "")
        out.append({
            "name": tool.get("name"),
            "description": norm_description(raw_desc),
            # A port hardcoding the literal "<MONTH-YEAR>" into its
            # description would normalize equal to the old side; this flag
            # (computed from the RAW text) makes that divergence visible.
            "description_has_month_year": bool(MONTH_YEAR_RE.search(raw_desc)),
            "inputSchema": norm_schema(tool.get("inputSchema")),
            "outputSchema": norm_schema(tool.get("outputSchema")),
        })
    return {"tools": sorted(out, key=lambda t: t["name"])}


def norm_call(resp: dict) -> dict:
    """Normalize one tools/call response: isError flag, error/text payload,
    structured output, and the content-block SHAPE (list of block types —
    catches a port emitting extra or non-text blocks).

    Comparison rules, in order:
      * JSON-RPC error responses are kept as-is (code+message).
      * Error results: an app-owned error string (APP_ERROR_RE) compares
        exactly; otherwise a transport-shaped text (TRANSPORT_ERROR_RE) is
        canonicalized to a class; anything else compares exactly.
      * Success results: `text` is the SDK's JSON SERIALIZATION of the
        structured output (Go json.Marshal vs Python json.dumps differ in
        separators, key order, and escaping — not spec), so it is dropped
        whenever the structured form is available (directly or by parsing
        the text); the structured dict — order-insensitive — is the
        comparison. If no structured form exists, text compares exactly.
    """
    result = resp.get("result", {})
    if "error" in resp and "result" not in resp:
        err = resp["error"]
        return {"jsonrpc_error": {"code": err.get("code"), "message": err.get("message")}}
    is_error = bool(result.get("isError", False))
    content = result.get("content") or []
    blocks = [c.get("type") for c in content]
    text = content[0].get("text") if content else None
    if is_error:
        if text and not APP_ERROR_RE.match(text) and TRANSPORT_ERROR_RE.search(text):
            return {"isError": True, "transport_error": True, "text": None,
                    "structured": None, "content_blocks": blocks}
        return {"isError": True, "text": text, "structured": None,
                "content_blocks": blocks}
    structured = result.get("structuredContent")
    if structured is None:
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        if texts:
            try:
                structured = json.loads(texts[0])
            except (json.JSONDecodeError, TypeError):
                structured = None
    return {
        "isError": False,
        "text": None if structured is not None else text,
        "structured": structured,
        "content_blocks": blocks,
    }


def norm_proxy_requests(requests: list[dict]) -> list[dict]:
    """Reduce recorded proxy traffic to the semantic surface: host, method,
    path (query string kept), the headers the spec sets deliberately."""
    out = []
    for req in requests:
        target = req.get("path") or req.get("target", "")
        if "://" in target:
            target = "/" + target.split("/", 3)[-1] if target.count("/") >= 3 else "/"
        headers = {k: v for k, v in req["headers"].items()}
        entry = {
            "host": req["host"],
            "method": req["method"],
            "path": target,
            "headers": dict(sorted(headers.items())),
        }
        body = req.get("body", "")
        if isinstance(body, (dict, list)):  # already normalized (idempotency)
            entry["body"] = body
        elif body:
            try:
                entry["body"] = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                entry["body"] = body
        out.append(entry)
    return out


# --------------------------------------------------------------------------
# Route handlers
# --------------------------------------------------------------------------

def serve(status: int, content_type: str, body: bytes | str):
    payload = body.encode() if isinstance(body, str) else body

    def handler(method: str, target: str, headers: dict, req_body: bytes):
        return status, {"Content-Type": content_type}, payload

    return handler


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def search_handler(body: bytes):
    def handler(method: str, target: str, headers: dict, req_body: bytes):
        return 200, {"Content-Type": "application/json"}, body

    return handler


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

def _find_calls(obs: dict) -> list[dict]:
    return obs["responses"]


class Scenario:
    def __init__(self, name: str, routes: dict, calls: list[tuple[str, dict]],
                 env: dict | None = None) -> None:
        self.name = name
        self.routes = routes
        self.calls = calls  # list of (tool_name, arguments); ("__tools_list__", {}) lists tools
        self.env = env or {}

    def canonicalize(self, obs: dict, side: str) -> dict:
        """Observer hook, SIDE-AWARE. Applied AFTER this side's invariants
        (which see the RAW observation) and only for the old-vs-new diff;
        `side` is "old" or "new".

        Two documented uses, both audited as potential weakenings:
          * old-code nondeterminism (s06's closed-body race): the OLD side
            maps its known-volatile values to a marker;
          * RULEBOOK FIX-FORWARD waivers: the old side maps its OLD literal
            to a marker, the new side maps the FIXED literal to the SAME
            marker. Any other value on either side stays literal and
            diverges — a waiver never becomes a free pass.
        Default: identity."""
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        """Spec-semantics assertions for the given side. The OLD side must
        satisfy the ORIGINAL spec; the NEW side must satisfy the FIXED spec
        where RULEBOOK FF-1..FF-6 applies (branch on `side`). Return a list
        of failure strings."""
        return []


def waive_client_ua(obs: dict, side: str) -> dict:
    """FF-4 waiver across every recorded client-grabber request: the old
    literal (Chrome/91 string) maps to M_UA on the old side, the fixed
    literal (FF4_UA) on the new side. Applied by every scenario whose
    traffic includes a client-grabber request (s06–s10, s13)."""
    expect = FIREFOX_UA if side == "old" else FF4_UA
    for req in obs.get("proxy_requests", []):
        headers = req.get("headers")
        if isinstance(headers, dict) and headers.get("user-agent") == expect:
            headers["user-agent"] = M_UA
    return obs


BASE_ENV = {
    "WEB_SEARCH_BASE": f"http://{SEARCH_HOST}",
    "WEB_SEARCH_API_KEY": "judge-search-key",
    "WEB_SEARCH_MODEL": "judge-search-model",
    "WEB_FETCH_BASE": f"http://{FETCH_HOST}",
    "WEB_FETCH_API_KEY": "judge-fetch-key",
    "WEB_FETCH_MODEL": "judge-fetch-model",
    "NO_PROXY": "",
    "no_proxy": "",
}


def _text_of(call: dict) -> str:
    return call.get("normalized", {}).get("text") or ""


def _structured_of(call: dict) -> dict:
    return call.get("normalized", {}).get("structured") or {}


SCENARIOS: list[Scenario] = []


def scenario(sc: Scenario) -> Scenario:
    SCENARIOS.append(sc)
    return sc


# S01 — tools/list: names, full descriptions (month-year normalized; the
# entire template compares byte-for-byte), schemas, and the initialize
# handshake's serverInfo (app-set in main.go).
#
# FF-1/FF-2 waiver: the title property key is "query" on the old side and
# "title" on the new side — renamed to M_TITLE_KEY per side, in BOTH the
# items properties and the items required list. The new side's ADDED
# `limit` input property (FF-2) is stripped from the comparison; a new side
# that also altered anything else in either schema still diverges.
class S01(Scenario):
    KEY_OLD, KEY_NEW = "query", "title"

    def __init__(self) -> None:
        super().__init__("s01_tools_list", routes={}, calls=[("__tools_list__", {})])

    def canonicalize(self, obs: dict, side: str) -> dict:
        key = self.KEY_OLD if side == "old" else self.KEY_NEW
        tools = obs["responses"][0]["normalized"]["tools"]
        for tool in tools:
            if tool.get("name") != "WebSearch":
                continue
            items = tool["outputSchema"]["properties"]["results"]["items"]
            props = items.get("properties", {})
            if key in props:
                props[M_TITLE_KEY] = props.pop(key)
            if "required" in items and key in items["required"]:
                items["required"] = [M_TITLE_KEY if k == key else k
                                     for k in items["required"]]
            if side == "new":
                tool["inputSchema"].get("properties", {}).pop("limit", None)
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        info = obs.get("server_info") or {}
        server = (info.get("serverInfo") or {})
        if server.get("name") != "websearch" or server.get("version") != "v1.0.0":
            fails.append(f"serverInfo = {server}")
        tools = _find_calls(obs)[0]["normalized"]["tools"]
        names = [t["name"] for t in tools]
        if sorted(names) != ["WebFetch", "WebSearch"]:
            return [f"tool names = {names}"]
        by_name = {t["name"]: t for t in tools}
        ws = by_name["WebSearch"]
        if ws["description"] != WEBSEARCH_DESCRIPTION:
            fails.append(f"WebSearch description != template: {ws['description'][:120]!r}...")
        if not ws.get("description_has_month_year"):
            fails.append("WebSearch description lacks a real month-year (hardcoded marker?)")
        items = ws["outputSchema"]["properties"]["results"]["items"]
        props = items.get("properties", {})
        key = self.KEY_OLD if side == "old" else self.KEY_NEW
        if key not in props:
            fails.append(f"WebSearch outputSchema lost the '{key}' title property")
        elif props[key].get("description") != "The title of the search result":
            fails.append(f"{key} prop description = {props[key].get('description')!r}")
        if sorted(items.get("required", [])) != sorted(["url", key, "content"]):
            fails.append(f"WebSearch items required = {items.get('required')}")
        if side == "new":
            limit_prop = ws["inputSchema"].get("properties", {}).get("limit")
            if limit_prop != {"type": "integer",
                              "description": "Maximum number of results to return"}:
                fails.append(f"FF-2: inputSchema limit property = {limit_prop!r}")
        if sorted(ws["inputSchema"].get("required", [])) != ["query"]:
            fails.append(f"WebSearch inputSchema required = {ws['inputSchema'].get('required')}")
        wf = by_name["WebFetch"]
        if wf["description"] != WEBFETCH_DESCRIPTION:
            fails.append(f"WebFetch description != template: {wf['description'][:120]!r}...")
        if wf.get("description_has_month_year"):
            fails.append("WebFetch description unexpectedly contains a month-year")
        if sorted(wf["inputSchema"].get("required", [])) != ["url"]:
            fails.append(f"WebFetch inputSchema required = {wf['inputSchema'].get('required')}")
        if sorted(wf["outputSchema"].get("required", [])) != ["content", "title", "url"]:
            fails.append(f"WebFetch outputSchema required = {wf['outputSchema'].get('required')}")
        return fails


scenario(S01())


# S02 — linkup happy path. FF-1 waiver: result rows carry the title under
# "query" (old) / "title" (new) — renamed per side before the diff. The
# snippet-precedence matrix and the full request surface (POST /search,
# Bearer, content-type, body query/model/max_results — 50 here: this call
# passes no limit, so the FF-2 default applies on BOTH sides) are shared.
class S02(Scenario):
    KEY_OLD, KEY_NEW = "query", "title"

    def __init__(self) -> None:
        super().__init__(
            "s02_websearch_happy_linkup",
            routes={SEARCH_HOST: search_handler(fixture("linkup.json"))},
            calls=[("WebSearch", {"query": "latest AI news"})],
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        key = self.KEY_OLD if side == "old" else self.KEY_NEW
        structured = obs["responses"][0]["normalized"].get("structured") or {}
        for row in structured.get("results") or []:
            if key in row:
                row[M_TITLE_KEY] = row.pop(key)
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        call = _find_calls(obs)[0]
        n = call["normalized"]
        if n.get("isError"):
            return [f"unexpected isError: {n.get('text')}"]
        structured = n.get("structured") or {}
        results = structured.get("results") or []
        if len(results) != 6:
            fails.append(f"expected 6 results, got {len(results)}")
            return fails
        r0, r1, r2, r3, r4, r5 = results
        key = self.KEY_OLD if side == "old" else self.KEY_NEW
        # old: bug-for-bug "query" key holds the TITLE; new: FF-1 "title".
        if r0.get(key) != "Result One Title":
            fails.append(f"r0.{key} (title) = {r0.get(key)!r}")
        if r0.get("url") != "https://example.com/one/":
            fails.append(f"r0.url = {r0.get('url')!r}")
        if r0.get("content") != "First snippet text which is long enough to be interesting and present.":
            fails.append("r0.content should prefer the non-empty snippet")
        if r1.get("content") != "Second result content text object wins here":
            fails.append("r1.content should come from content.text when snippet empty")
        if r2.get("content") != "Third result raw string content":
            fails.append("r2.content should be the raw string content")
        if r3.get("content") != "Fourth snippet wins over object":
            fails.append("r3.content should prefer snippet over content object")
        if r4.get("content") != "Fifth snippet, content object missing text":
            fails.append("r4.content should keep snippet when content.text missing")
        if r5.get("content") != '{"format": "text", "length": 0}':
            fails.append(f"r5.content should be the RAW json echo of the textless "
                         f"content object, got {r5.get('content')!r}")
        reqs = norm_proxy_requests(obs["proxy_requests"])
        search_reqs = [r for r in reqs if r["host"] == SEARCH_HOST]
        if not search_reqs:
            fails.append("no request reached the search stub")
        else:
            r = search_reqs[0]
            if r["method"] != "POST" or r["path"] != "/search":
                fails.append(f"search request {r['method']} {r['path']}")
            if r["headers"].get("authorization") != "Bearer judge-search-key":
                fails.append(f"authorization = {r['headers'].get('authorization')!r}")
            if r["headers"].get("content-type") != "application/json":
                fails.append(f"content-type = {r['headers'].get('content-type')!r}")
            body = r.get("body")
            if not isinstance(body, dict) or body.get("query") != "latest AI news" \
                    or body.get("model") != "judge-search-model" or body.get("max_results") != 50:
                fails.append(f"search body = {body}")
        return fails


scenario(S02())

# S03 — cloud webfetch happy path: JSON response shaping through the tool.
class S03(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s03_webfetch_cloud_happy",
            routes={FETCH_HOST: serve(200, "application/json", json.dumps({
                "url": "ignored-by-service", "title": "Cloud Fetch Title",
                "content": {"text": "Cloud fetch processed text", "length": 24},
            }))},
            calls=[("WebFetch", {"url": "https://cloud-target.example/page"})],
        )

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        n = _find_calls(obs)[0]["normalized"]
        if n.get("isError"):
            return [f"unexpected error: {n.get('text')}"]
        structured = n.get("structured") or {}
        if structured.get("url") != "https://cloud-target.example/page":
            fails.append(f"url echo = {structured.get('url')!r}")
        if structured.get("title") != "Cloud Fetch Title":
            fails.append(f"title = {structured.get('title')!r}")
        content = structured.get("content") or {}
        if content.get("text") != "Cloud fetch processed text":
            fails.append(f"text = {content.get('text')!r}")
        if content.get("length") != 24:
            fails.append(f"length = {content.get('length')!r}")
        reqs = norm_proxy_requests(obs["proxy_requests"])
        fetch_reqs = [r for r in reqs if r["host"] == FETCH_HOST]
        if not fetch_reqs:
            fails.append("no request reached the fetch stub")
        else:
            r = fetch_reqs[0]
            if r["method"] != "POST" or r["path"] != "/web/fetch":
                fails.append(f"fetch request {r['method']} {r['path']}")
            if r["headers"].get("authorization") != "Bearer judge-fetch-key":
                fails.append(f"authorization = {r['headers'].get('authorization')!r}")
            if r["headers"].get("content-type") != "application/json":
                fails.append(f"content-type = {r['headers'].get('content-type')!r}")
            body = r.get("body")
            if not isinstance(body, dict) or body.get("url") != "https://cloud-target.example/page" \
                    or body.get("model") != "judge-fetch-model" or body.get("format") != "markdown":
                fails.append(f"fetch body = {body}")
        # cloud-first ordering: the local grabber must NOT have been contacted
        if any(r["host"] == "cloud-target.example" for r in reqs):
            fails.append("local grabber ran despite cloud success")
        return fails


scenario(S03())


# S04 — websearch empty query -> exact error text, no network.
scenario(Scenario(
    "s04_websearch_empty_query",
    routes={},
    calls=[("WebSearch", {"query": ""})],
))


def s04_invariants(obs: dict, side: str) -> list[str]:
    n = _find_calls(obs)[0]["normalized"]
    if not n.get("isError"):
        return [f"expected isError, got {n}"]
    if n.get("text") != "query must not be empty":
        return [f"error text = {n.get('text')!r}"]
    if obs["proxy_requests"]:
        return ["network was touched for an empty query"]
    return []


SCENARIOS[-1].invariants = s04_invariants  # type: ignore[method-assign]

# S05 — webfetch non-http URL -> exact error text, no network.
# Includes an UPPERCASE scheme ("HTTP://…"): the check is a case-sensitive
# strings.HasPrefix, so a normalizing port must still reject it here.
scenario(Scenario(
    "s05_webfetch_non_http_url",
    routes={},
    calls=[("WebFetch", {"url": "ftp://example.com/x"}),
           ("WebFetch", {"url": "example.com/no-scheme"}),
           ("WebFetch", {"url": "HTTP://example.com/upper"})],
))


def s05_invariants(obs: dict, side: str) -> list[str]:
    fails = []
    for call in _find_calls(obs):
        n = call["normalized"]
        if not n.get("isError") or n.get("text") != \
                "URL must be fully-formed and start with http:// or https://":
            fails.append(f"{call['arguments'].get('url')}: {n.get('text')!r}")
    if obs["proxy_requests"]:
        fails.append("network was touched for invalid URLs")
    return fails


SCENARIOS[-1].invariants = s05_invariants  # type: ignore[method-assign]


# S06 — plain-text request surface through the client grabber.
#
# OLD side — DOCUMENTED NONDETERMINISM: the client grabber closes resp.Body
# on return while handing out a lazy reader, so the postprocessor's read
# races the transport's close/drain. Across runs the body was either
# delivered verbatim or read as empty — both observed on the ORIGINAL
# binary. The OLD side's content (text AND length — length is computed from
# the raced text) is canonicalized to a marker.
#
# NEW side — FF-5: delivery is deterministic. Pinned to the fixedGo capture:
# text = PLAINTEXT_TEXT, length = 48 BYTES (the fixture is 41 chars — a port
# computing len(str) diverges here; this is where the byte-vs-char trap
# became judge-observable). UA per side: FIREFOX_UA / FF4_UA (FF-4).
class S06(Scenario):

    def __init__(self) -> None:
        super().__init__(
            "s06_plaintext_passthrough",
            routes={"example.com": serve(200, "text/plain", fixture("plain.txt"))},
            calls=[("WebFetch", {"url": "http://example.com/plain.txt"})],
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        obs = waive_client_ua(obs, side)
        if side == "old":
            # raced delivery: EITHER outcome maps to the shared marker
            for resp in obs["responses"]:
                structured = (resp.get("normalized") or {}).get("structured") or None
                if structured and "content" in structured:
                    text = structured["content"].get("text")
                    if text in (PLAINTEXT_TEXT, ""):
                        structured["content"] = M_CONTENT
        else:
            structured = obs["responses"][0]["normalized"].get("structured") or {}
            if structured.get("content") == {"text": PLAINTEXT_TEXT,
                                             "length": PLAINTEXT_LEN}:
                structured["content"] = M_CONTENT
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        n = _find_calls(obs)[0]["normalized"]
        if n.get("isError"):
            return [f"unexpected error: {n.get('text')}"]
        if side == "new":
            content = (n.get("structured") or {}).get("content") or {}
            if content.get("text") != PLAINTEXT_TEXT:
                fails.append(f"FF-5: plaintext not delivered verbatim: "
                             f"{content.get('text')!r}")
            if content.get("length") != PLAINTEXT_LEN:
                fails.append(f"FF-5/byte-len: length = {content.get('length')!r}, "
                             f"want {PLAINTEXT_LEN} BYTES")
        reqs = norm_proxy_requests(obs["proxy_requests"])
        if not reqs:
            return ["no proxied request"]
        # cloud-first ordering: the cloud fetch stub must be tried before the
        # local grabber fires (fetch.test has no route here -> 404 -> fallback)
        if not any(r["host"] == FETCH_HOST and r["path"] == "/web/fetch" for r in reqs):
            fails.append("cloud fetch service was not tried first")
        local = [r for r in reqs if r["host"] == "example.com"]
        if not local:
            fails.append("local grabber never fetched example.com")
            return fails
        r = local[0]
        if r["method"] != "GET" or r["path"] != "/plain.txt":
            fails.append(f"local request {r['method']} {r['path']}")
        want_ua = FIREFOX_UA if side == "old" else FF4_UA
        if r["headers"].get("user-agent") != want_ua:
            fails.append(f"client grabber UA = {r['headers'].get('user-agent')!r}, "
                         f"want {'FIREFOX_UA' if side == 'old' else 'FF4_UA'}")
        if r["headers"].get("accept") != CLIENT_ACCEPT:
            fails.append(f"client grabber Accept = {r['headers'].get('accept')!r}")
        return fails


scenario(S06())


# S07 — rich HTML extraction through the public surface.
#
# OLD side: the closed-body bug makes extraction return "" for every HTML
# page (charset.NewReader fails on the closed body) — the empty contract.
#
# NEW side (FF-5): extraction runs. Pinned to the fixedGo capture
# (RICH_HTML_TEXT, 639 bytes). The pinned text carries the goquery
# selector-list quirk — the <code> NESTED inside a matched <p> is emitted
# as its own node immediately after the paragraph with no separator
# ("...to keep.\n\n`inline_code_marker`List item one...") — plus the
# min-length filters ("Short." dropped), the "Read more" prefix rule, and
# cleanDocument's removals. A port whose extraction differs in ANY byte
# diverges here.
class S07(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s07_html_extraction_rich",
            routes={"example.com": serve(200, "text/html", fixture("rich.html"))},
            calls=[("WebFetch", {"url": "http://example.com/rich.html"})],
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        obs = waive_client_ua(obs, side)
        structured = obs["responses"][0]["normalized"].get("structured") or {}
        want = ({"text": "", "length": 0} if side == "old"
                else {"text": RICH_HTML_TEXT, "length": RICH_HTML_LEN})
        if structured.get("content") == want:
            structured["content"] = M_CONTENT
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        n = _find_calls(obs)[0]["normalized"]
        if n.get("isError"):
            return [f"unexpected error: {n.get('text')}"]
        structured = n.get("structured") or {}
        content = structured.get("content") or {}
        if side == "old":
            if content.get("text") != "":
                fails.append(f"html extraction should be EMPTY (closed-body bug), got {content.get('text', '')[:80]!r}")
            if content.get("length") != 0:
                fails.append(f"length should be 0, got {content.get('length')}")
        else:
            if content.get("text") != RICH_HTML_TEXT:
                got = content.get("text", "")
                fails.append(f"FF-5: extraction mismatch (len {len(got)} vs "
                             f"{RICH_HTML_LEN}): {got[:120]!r}...")
            if content.get("length") != RICH_HTML_LEN:
                fails.append(f"FF-5: length = {content.get('length')!r}, "
                             f"want {RICH_HTML_LEN}")
        if structured.get("url") != "http://example.com/rich.html":
            fails.append(f"url echo = {structured.get('url')!r}")
        return fails


scenario(S07())

# S08 — windows-1251 charset page.
#
# OLD side: "text/html; charset=…" misses the choice postprocessor's exact
# match -> DEFAULT branch -> "" — decoding never runs.
#
# NEW side (FF-6 + FF-5): the media type matches the html branch, and the
# page DECODES — pinned to the fixedGo capture (CP1251_TEXT, 354 bytes).
# Note for the port: fixedGo decodes via x/net/html/charset's sniffing (the
# fixture carries a <meta http-equiv="Content-Type" content="...windows-
# 1251">); the rulebook's canonical rule is the DECLARED Content-Type
# parameter, which for this fixture agrees with the meta tag.
scenario(Scenario(
    "s08_html_charset_cp1251",
    routes={"example.com": serve(200, "text/html; charset=windows-1251",
                                 fixture("charset_1251.html"))},
    calls=[("WebFetch", {"url": "http://example.com/cp1251.html"})],
))


def s08_canonicalize(obs: dict, side: str) -> dict:
    obs = waive_client_ua(obs, side)
    structured = obs["responses"][0]["normalized"].get("structured") or {}
    want = ({"text": "", "length": 0} if side == "old"
            else {"text": CP1251_TEXT, "length": CP1251_LEN})
    if structured.get("content") == want:
        structured["content"] = M_CONTENT
    return obs


def s08_invariants(obs: dict, side: str) -> list[str]:
    fails = []
    n = _find_calls(obs)[0]["normalized"]
    if n.get("isError"):
        return [f"unexpected error: {n.get('text')}"]
    structured = n.get("structured") or {}
    content = structured.get("content") or {}
    if side == "old":
        if content.get("text") != "":
            fails.append(f"charset page should extract to empty (default branch), got "
                         f"{content.get('text', '')[:60]!r}")
        if content.get("length") != 0:
            fails.append(f"length = {content.get('length')!r}")
    else:
        if content.get("text") != CP1251_TEXT:
            fails.append(f"FF-6: cp1251 decode/extraction mismatch: "
                         f"{content.get('text', '')[:80]!r}")
        if content.get("length") != CP1251_LEN:
            fails.append(f"FF-6: length = {content.get('length')!r}, "
                         f"want {CP1251_LEN} BYTES")
    if structured.get("url") != "http://example.com/cp1251.html":
        fails.append(f"url echo = {structured.get('url')!r}")
    reqs = norm_proxy_requests(obs["proxy_requests"])
    local = [r for r in reqs if r["host"] == "example.com"]
    if not local:
        fails.append("local grabber never fetched the cp1251 page")
    else:
        r = local[0]
        if r["method"] != "GET" or r["path"] != "/cp1251.html":
            fails.append(f"local request {r['method']} {r['path']}")
        want_ua = FIREFOX_UA if side == "old" else FF4_UA
        if r["headers"].get("user-agent") != want_ua:
            fails.append(f"UA = {r['headers'].get('user-agent')!r}")
    return fails


SCENARIOS[-1].canonicalize = s08_canonicalize  # type: ignore[method-assign]
SCENARIOS[-1].invariants = s08_invariants  # type: ignore[method-assign]

# S09 — application/json content -> empty content (choice postprocessor).
scenario(Scenario(
    "s09_json_content_empty",
    routes={"example.com": serve(200, "application/json", b'{"a": 1}')},
    calls=[("WebFetch", {"url": "http://example.com/data.json"})],
))


def s09_invariants(obs: dict, side: str) -> list[str]:
    n = _find_calls(obs)[0]["normalized"]
    if n.get("isError"):
        return [f"unexpected error: {n.get('text')}"]
    structured = n.get("structured") or {}
    content = structured.get("content") or {}
    if content.get("text") != "" or content.get("length") != 0:
        return [f"json content must be empty string, got {content!r}"]
    return []


SCENARIOS[-1].invariants = s09_invariants  # type: ignore[method-assign]
SCENARIOS[-1].canonicalize = waive_client_ua  # type: ignore[method-assign]

# S10 — HTTP 500 from plain grabber -> error surfaced.
scenario(Scenario(
    "s10_local_http_error",
    routes={"example.com": serve(500, "text/html", b"<html>boom</html>")},
    calls=[("WebFetch", {"url": "http://example.com/broken"})],
))


def s10_invariants(obs: dict, side: str) -> list[str]:
    n = _find_calls(obs)[0]["normalized"]
    if not n.get("isError"):
        return [f"expected isError for HTTP 500, got {n}"]
    # Exact contract: client/grabber.go's fmt.Errorf("HTTP %d: %s", code,
    # resp.Status); resp.Status for the proxy's 500 line is
    # "500 Internal Server Error" (proxy.py's reason map).
    if n.get("text") != "HTTP 500: 500 Internal Server Error":
        return [f"error text = {n.get('text')!r}"]
    return []


SCENARIOS[-1].invariants = s10_invariants  # type: ignore[method-assign]
SCENARIOS[-1].canonicalize = waive_client_ua  # type: ignore[method-assign]


# S11 — GitHub URL routing at the CONNECT level.
#
# The rewritten GitHub upstreams (raw.githubusercontent.com, api.github.com)
# are hardcoded https and cannot be TLS-intercepted on this platform (see
# proxy.py), so routing is judged by WHICH HOST each URL connects to:
#   blob  -> raw.githubusercontent.com   (and never github.com itself)
#   repo/issue/pull -> api.github.com    (and never github.com itself)
# The tunnel fails identically for both binaries; the resulting transport
# error is canonicalized (norm_call). The api-side PATH rewrite (pull->pulls)
# and header behavior are NOT publicly observable here — they are pinned by
# the port's own unit tests. WARNING for the port: grabber_test.go's UA
# assertion ("websearch/1.0") is STALE — the source sends the Firefox
# fingerprint UA (github/grabber.go:74, verified). Port the ROUTING TABLE
# from that test; assert the SOURCE's UA, not the test's.
class S11(Scenario):
    def __init__(self) -> None:
        super().__init__("s11_github_routing", routes={}, calls=[
            ("WebFetch", {"url": "https://github.com/owner/repo/blob/main/path/to/file.go"}),
            ("WebFetch", {"url": "https://github.com/owner/repo"}),
            ("WebFetch", {"url": "https://github.com/owner/repo/issues/123"}),
            ("WebFetch", {"url": "https://github.com/owner/repo/pull/456"}),
        ])

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        reqs = norm_proxy_requests(obs["proxy_requests"])
        connects = [r["host"] for r in reqs if r["method"] == "CONNECT"]
        expected = ["raw.githubusercontent.com", "api.github.com",
                    "api.github.com", "api.github.com"]
        if connects != expected:
            fails.append(f"CONNECT sequence {connects}, want {expected}")
        if any(r["host"] == "github.com" for r in reqs):
            fails.append("routable github URL fell back to the plain grabber")
        for i, call in enumerate(_find_calls(obs)):
            n = call["normalized"]
            if not n.get("isError") or not n.get("transport_error"):
                fails.append(f"call {i}: expected canonical transport error, got {n}")
        return fails


scenario(S11())


# S12 — unrouted github URL falls back to the plain client grabber.
#
# Observable signal: a CONNECT to github.com itself (the plain grabber
# fetching the ORIGINAL url). Routed URLs (s11) never touch github.com.
class S12(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s12_github_fallback",
            routes={},
            calls=[("WebFetch", {"url": "https://github.com/owner/repo/tree/main"})],
        )

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        reqs = norm_proxy_requests(obs["proxy_requests"])
        connects = [r["host"] for r in reqs if r["method"] == "CONNECT"]
        if "github.com" not in connects:
            fails.append(f"fallback did not fetch original URL (no CONNECT github.com): {connects}")
        n = _find_calls(obs)[0]["normalized"]
        if not n.get("isError") or not n.get("transport_error"):
            fails.append(f"expected canonical transport error, got {n}")
        return fails


scenario(S12())


# S13 — cloud fetch fails (500) -> complex service falls back to local.
# OLD: empty content (closed-body). NEW (FF-5): pinned extraction of the
# failover fixture (fixedGo capture, 129 bytes).
class S13(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s13_cloud_failover_to_local",
            routes={
                FETCH_HOST: serve(500, "application/json", b'{"error":"cloud down"}'),
                "example.com": serve(200, "text/html", fixture("failover.html")),
            },
            calls=[("WebFetch", {"url": "http://example.com/failover.html"})],
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        obs = waive_client_ua(obs, side)
        structured = obs["responses"][0]["normalized"].get("structured") or {}
        want = ({"text": "", "length": 0} if side == "old"
                else {"text": FAILOVER_HTML_TEXT, "length": FAILOVER_HTML_LEN})
        if structured.get("content") == want:
            structured["content"] = M_CONTENT
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        reqs = norm_proxy_requests(obs["proxy_requests"])
        hosts = [r["host"] for r in reqs]
        if FETCH_HOST not in hosts:
            fails.append("cloud endpoint was not attempted")
        if "example.com" not in hosts:
            fails.append("local fallback did not run")
        n = _find_calls(obs)[0]["normalized"]
        if n.get("isError"):
            fails.append(f"unexpected error: {n.get('text')}")
        else:
            content = (n.get("structured") or {}).get("content") or {}
            if side == "old":
                if content.get("text") != "":
                    fails.append(f"failover html should be empty (closed-body bug), got {content.get('text', '')[:60]!r}")
            else:
                if content.get("text") != FAILOVER_HTML_TEXT:
                    fails.append(f"FF-5: failover extraction mismatch: "
                                 f"{content.get('text', '')[:80]!r}")
                if content.get("length") != FAILOVER_HTML_LEN:
                    fails.append(f"FF-5: length = {content.get('length')!r}, "
                                 f"want {FAILOVER_HTML_LEN}")
        return fails


scenario(S13())


# S14 — WebSearch cloud non-2xx -> the exact app error string.
# websearch/cloud/service.go: fmt.Errorf("search request failed: %s", resp.Status).
scenario(Scenario(
    "s14_search_http_error",
    routes={SEARCH_HOST: serve(500, "application/json", b'{"error":"search down"}')},
    calls=[("WebSearch", {"query": "anything"})],
))


def s14_invariants(obs: dict, side: str) -> list[str]:
    n = _find_calls(obs)[0]["normalized"]
    if not n.get("isError"):
        return [f"expected isError for search 500, got {n}"]
    if n.get("text") != "search request failed: 500 Internal Server Error":
        return [f"error text = {n.get('text')!r}"]
    reqs = norm_proxy_requests(obs["proxy_requests"])
    if not any(r["host"] == SEARCH_HOST and r["path"] == "/search" for r in reqs):
        return ["no request reached the search stub (error not from the 500 path)"]
    return []


SCENARIOS[-1].invariants = s14_invariants  # type: ignore[method-assign]


# S15 — IsCanGrab host matching and regex-miss fallback, at CONNECT level.
#   http://github.com/o/r      -> repo regex tolerates http -> api.github.com
#   https://www.github.com/o/r -> IsCanGrab yes, NO regex matches (they
#                                 anchor github\.com) -> fallback grab ->
#                                 CONNECT www.github.com (the original URL)
#   https://gitlab.com/o/r     -> IsCanGrab no -> client grabber -> CONNECT
#                                 gitlab.com
class S15(Scenario):
    def __init__(self) -> None:
        super().__init__("s15_iscangrab_variants", routes={}, calls=[
            ("WebFetch", {"url": "http://github.com/owner/repo"}),
            ("WebFetch", {"url": "https://www.github.com/owner/repo"}),
            ("WebFetch", {"url": "https://gitlab.com/owner/repo"}),
        ])

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        reqs = norm_proxy_requests(obs["proxy_requests"])
        connects = [r["host"] for r in reqs if r["method"] == "CONNECT"]
        expected = ["api.github.com", "www.github.com", "gitlab.com"]
        if connects != expected:
            fails.append(f"CONNECT sequence {connects}, want {expected}")
        for i, call in enumerate(_find_calls(obs)):
            n = call["normalized"]
            if not n.get("isError") or not n.get("transport_error"):
                fails.append(f"call {i}: expected canonical transport error, got {n}")
        return fails


scenario(S15())


# S16 — Authorization with EMPTY API keys.
#   OLD: websearch sends "Authorization: Bearer " UNCONDITIONALLY (records
#        as "Bearer"); webfetch omits it. The asymmetry is OLD-side spec.
#   NEW (FF-3): BOTH omit the header when the key is empty.
# The webfetch side is identical on both sides and compares exactly; the
# websearch side is waived per side (old literal / new absence -> M_AUTH).
class S16(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s16_empty_api_keys",
            routes={
                SEARCH_HOST: serve(200, "application/json", b'{"results": []}'),
                FETCH_HOST: serve(200, "application/json", json.dumps({
                    "url": "x", "title": "T", "content": {"text": "B", "length": 1},
                })),
            },
            calls=[("WebFetch", {"url": "https://target.example/page"}),
                   ("WebSearch", {"query": "anything"})],
            env={"WEB_SEARCH_API_KEY": "", "WEB_FETCH_API_KEY": ""},
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        for req in obs.get("proxy_requests", []):
            if req.get("host") != SEARCH_HOST:
                continue
            headers = req.get("headers", {})
            if side == "old" and headers.get("authorization") == "Bearer":
                headers["authorization"] = M_AUTH
            elif side == "new" and "authorization" not in headers:
                headers["authorization"] = M_AUTH
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        fails = []
        for i, call in enumerate(_find_calls(obs)):
            if call["normalized"].get("isError"):
                fails.append(f"call {i} unexpected error: {call['normalized'].get('text')}")
        reqs = norm_proxy_requests(obs["proxy_requests"])
        fetch = [r for r in reqs if r["host"] == FETCH_HOST]
        search = [r for r in reqs if r["host"] == SEARCH_HOST]
        if not fetch:
            fails.append("cloud fetch was not attempted")
        elif "authorization" in fetch[0]["headers"]:
            fails.append(f"webfetch sent Authorization with an empty key: "
                         f"{fetch[0]['headers']['authorization']!r}")
        if not search:
            fails.append("cloud search was not attempted")
        elif side == "old":
            if search[0]["headers"].get("authorization") != "Bearer":
                fails.append(f"websearch Authorization with empty key = "
                             f"{search[0]['headers'].get('authorization')!r}, want 'Bearer'")
        else:
            if "authorization" in search[0]["headers"]:
                fails.append(f"FF-3: websearch sent Authorization with an "
                             f"empty key: {search[0]['headers']['authorization']!r}")
        return fails


scenario(S16())


# S17 — empty search results must serialize as [] (not null): the Go output
# builds a non-nil slice. A port emitting None/null diverges.
scenario(Scenario(
    "s17_search_empty_results",
    routes={SEARCH_HOST: search_handler(b'{"results": []}')},
    calls=[("WebSearch", {"query": "nothing"})],
))


def s17_invariants(obs: dict, side: str) -> list[str]:
    n = _find_calls(obs)[0]["normalized"]
    if n.get("isError"):
        return [f"unexpected error: {n.get('text')}"]
    structured = n.get("structured") or {}
    if structured.get("results") != []:
        return [f"results = {structured.get('results')!r}, want []"]
    return []


SCENARIOS[-1].invariants = s17_invariants  # type: ignore[method-assign]


# S18 — FF-2: the limit argument is honored (50 stays the default, pinned
# by s02, which passes no limit).
#
# This scenario is ENTIRELY side-branched: the OLD binary's SDK REJECTS the
# unknown `limit` argument outright ("unexpected additional properties" —
# additionalProperties:false) with no network; the NEW side accepts it and
# must reach the stub with max_results == 2 and return the 6-row fixture.
# The old-vs-new diff is therefore waived WHOLESALE by reducing each side's
# observation to a side literal — but ONLY when the observation matches its
# side's expected shape exactly; any deviation (wrong limit, wrong method,
# extra traffic, wrong result count) stays literal and diverges against the
# other side's marker. stdio_noise and server_info remain compared.
class S18(Scenario):
    def __init__(self) -> None:
        super().__init__(
            "s18_search_limit_honored",
            routes={SEARCH_HOST: search_handler(fixture("linkup.json"))},
            calls=[("WebSearch", {"query": "limit probe", "limit": 2})],
        )

    def canonicalize(self, obs: dict, side: str) -> dict:
        if side == "old":
            n = obs["responses"][0]["normalized"]
            ok = bool(n.get("isError")) and not obs["proxy_requests"]
            marker = "<LIMIT-CONTRACT>"
        else:
            n = obs["responses"][0]["normalized"]
            results = (n.get("structured") or {}).get("results")
            reqs = obs["proxy_requests"]
            ok = (not n.get("isError") and len(results or []) == 6
                  and len(reqs) == 1
                  and reqs[0].get("host") == SEARCH_HOST
                  and reqs[0].get("method") == "POST"
                  and reqs[0].get("path") == "/search"
                  and (reqs[0].get("body") or {}).get("max_results") == 2)
            marker = "<LIMIT-CONTRACT>"
        if ok:
            obs["responses"] = [{"normalized": marker}]
            obs["proxy_requests"] = []
        return obs

    def invariants(self, obs: dict, side: str) -> list[str]:
        n = _find_calls(obs)[0]["normalized"]
        if side == "old":
            if not n.get("isError"):
                return ["old side: expected the SDK to reject the unknown "
                        "'limit' argument"]
            if obs["proxy_requests"]:
                return ["old side: network touched despite argument rejection"]
            return []
        if n.get("isError"):
            return [f"unexpected error: {n.get('text')}"]
        structured = n.get("structured") or {}
        results = structured.get("results") or []
        if len(results) != 6:
            return [f"expected 6 results, got {len(results)}"]
        reqs = norm_proxy_requests(obs["proxy_requests"])
        search_reqs = [r for r in reqs if r["host"] == SEARCH_HOST]
        if not search_reqs:
            return ["no request reached the search stub"]
        body = search_reqs[0].get("body")
        if not isinstance(body, dict) or body.get("max_results") != 2:
            return [f"FF-2: max_results = {body.get('max_results')!r} if dict "
                    f"else {body!r}, want 2"]
        return []


scenario(S18())


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def observe(binary: str, sc: Scenario, proxy: JudgeProxy) -> dict:
    proxy.reset(sc.routes)
    env = dict(os.environ)
    env.update(BASE_ENV)
    env.update({
        "HTTPS_PROXY": proxy.url,
        "https_proxy": proxy.url,
        # Scrub/override any proxy vars inherited from the invoking shell: a
        # trust_env-style Python client would otherwise route plain-http
        # stubs to the OUTER proxy (the Go binary ignores these — it reads
        # only HTTPS_PROXY — so setting them is harmless for the old side).
        "HTTP_PROXY": proxy.url,
        "http_proxy": proxy.url,
        "ALL_PROXY": proxy.url,
        "all_proxy": proxy.url,
    })
    env.update(sc.env)
    client = MCPClient(binary, env)
    responses = []
    try:
        init = client.initialize()
        init_result = init.get("result", {}) or {}
        server_info = {
            "serverInfo": init_result.get("serverInfo"),  # app-set: exact spec
            # protocolVersion/capabilities are SDK-negotiated decoration —
            # not compared (dropped here), documented in the README.
        }
        for tool, args in sc.calls:
            raw = client.tools_list() if tool == "__tools_list__" else client.tools_call(tool, args)
            if tool == "__tools_list__":
                normalized = norm_tools_list(raw)
            else:
                normalized = norm_call(raw)
            responses.append({"call": tool, "arguments": args, "normalized": normalized})
    finally:
        client.close()
    return {
        "server_info": server_info,
        "responses": responses,
        "proxy_requests": norm_proxy_requests(proxy.requests()),
        "stdio_noise": list(client.dropped),  # normally empty; compared
    }


class Judge:
    def __init__(self, old_bin: str, new_bin: str | None = None,
                 scenarios: list[Scenario] | None = None,
                 sides: tuple[str, str] = ("old", "new")) -> None:
        self.old_bin = old_bin
        self.new_bin = new_bin or old_bin
        self.scenarios = scenarios if scenarios is not None else SCENARIOS
        # Which spec contract each binary is judged against ("old"/"new").
        # ("old","old") = determinism self-check of the reference; ("new",
        # "new") = self-check of a fixed-spec binary (e.g. websearch-fixedgo);
        # the default judges old-vs-port against their respective contracts.
        self.sides = sides
        self.proxy = JudgeProxy()

    def run(self) -> dict:
        report = {"scenarios": [], "passed": 0, "failed": 0}

        def guarded_invariants(sc: Scenario, obs: dict, side: str) -> list[str]:
            # An unexpected response shape must surface as a readable
            # failure, not a judge crash (exit stays non-zero either way).
            try:
                return sc.invariants(obs, side)
            except Exception as exc:  # noqa: BLE001 - converted to a failure
                return [f"invariant raised {type(exc).__name__}: {exc}"]

        for sc in self.scenarios:
            entry = {"name": sc.name, "old_invariant_failures": [],
                     "new_invariant_failures": [], "diverged": False, "diff": None}
            side_old, side_new = self.sides
            # Invariants see the RAW observation; canonicalize only shapes
            # the old-vs-new diff (so a waiver can never satisfy an
            # invariant, and an invariant never sees a marker).
            old_raw = observe(self.old_bin, sc, self.proxy)
            entry["old_invariant_failures"] = guarded_invariants(sc, old_raw, side_old)
            new_raw = observe(self.new_bin, sc, self.proxy)
            entry["new_invariant_failures"] = guarded_invariants(sc, new_raw, side_new)
            old_obs = sc.canonicalize(old_raw, side_old)
            new_obs = sc.canonicalize(new_raw, side_new)
            if old_obs != new_obs:
                entry["diverged"] = True
                entry["diff"] = first_diffs(old_obs, new_obs)
            with self.proxy._lock:
                proxy_errors = list(self.proxy.errors)
                self.proxy.errors = []
                self.proxy.idle_timeouts = []
            if proxy_errors:
                # The proxy itself misbehaved (parse failure, socket error):
                # the observation is untrustworthy — fail the scenario rather
                # than risk a pass built on missing records.
                entry["proxy_errors"] = proxy_errors
                entry["old_invariant_failures"] = \
                    entry["old_invariant_failures"] + \
                    [f"proxy error: {e}" for e in proxy_errors]
            ok = not entry["old_invariant_failures"] and not entry["new_invariant_failures"] \
                and not entry["diverged"]
            entry["ok"] = ok
            report["passed" if ok else "failed"] += 1
            report["scenarios"].append(entry)
        self.proxy.stop()
        return report


def first_diffs(old: dict, new: dict, limit: int = 5) -> list[str]:
    diffs: list[str] = []

    def walk(a: object, b: object, path: str) -> None:
        if len(diffs) >= limit:
            return
        if type(a) is not type(b):
            diffs.append(f"{path}: {a!r} != {b!r}")
            return
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    diffs.append(f"{path}.{key}: {a.get(key, '<missing>')!r} != {b.get(key, '<missing>')!r}")
                else:
                    walk(a[key], b[key], f"{path}.{key}")
        elif isinstance(a, list):
            if len(a) != len(b):
                diffs.append(f"{path}: list lengths {len(a)} != {len(b)}")
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        elif a != b:
            diffs.append(f"{path}: {a!r} != {b!r}")

    walk(old, new, "$")
    return diffs
