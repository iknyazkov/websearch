# Inventory ↔ rulebook conflicts

Joint-audit format (the audit phase extends this file): each conflict names
the rule, the row, and the concrete translation that goes wrong. Fixes are
applied on the INVENTORY side immediately; rulebook changes are QUEUED for
the human — never applied by an agent.

## C-1 — RULEBOOK §1 "Charset decoding" row contradicts the fixedGo spec

- **Rule:** RULEBOOK §1, Charset decoding row — "declared charset from the
  `Content-Type` parameter; if absent, UTF-8 … we do NOT [sniff meta]".
- **Row:** `inventory.tsv` row 1 —
  `internal/services/webfetch/local/postprocessor/html/postprocessor.go` ·
  `extractRelevantText` · BYTES-CHARSET.
- **What goes wrong concretely:** the declared Content-Type parameter never
  reaches the decoder. `HTMLPostprocessor.Handle` calls
  `extractRelevantText(reader, "text/html")` with a HARDCODED content-type
  string (postprocessor.go:29), and `charset.NewReader` receives only that.
  Decoding is therefore decided by x/net's `DetermineEncoding` on the body
  bytes: BOM → meta prescan (`<meta charset>`, `<meta http-equiv>`) →
  UTF-8-validity heuristic → windows-1252 default. Following the rulebook
  row as written, the port would decode `charset_1251.html` as UTF-8 (the
  judge scenario's response header param aside, the rule says param-first,
  no sniff) and emit mojibake/U+FFFD soup — diverging from the pinned
  fixedGo output `CP1251_TEXT` (354 bytes, judge s08,
  `amendments-capture.json`). The fixture declares its charset ONLY via
  `<meta http-equiv="Content-Type" content="text/html; charset=
  windows-1251">`, so meta-sniffing is load-bearing for the pinned spec.
- **Inventory-side action (applied):** row 1 specifies the faithful
  DetermineEncoding mirror; implementers follow the row, not §1.
- **Queued rulebook amendment:** `queued-rulebook-amendment.md` A-1
  rewrites the §1 charset row to match the source mechanism.

## Joint audit (2026-10-27) — 18 findings by 2 auditors, consolidated to 10 conflicts

Both auditors read all 95 rows (journal: wf_dc1c39f3-21a). Fixes marked
"applied" are inventory-side; rulebook changes are QUEUED, never applied by an
agent. Severity shown is the auditors' worst.

### C-1 (pre-existing) — see above.

### C-2 — shared-client constructor missing timeout=None [divergence, applied]
- **Rule:** §0 "Everything NOT on this list ports bug-for-bug" (a 5 s deadline
  is new behavior). **Rows:** network/client.go owner row (HTTP-DNS) vs the
  ctx-shard row for the same file.
- **What went wrong:** the owner row spelled `httpx.Client(proxy=…,
  trust_env=False)` with no timeout; the ctx shard found httpx defaults to a
  5 s deadline (probed: `Timeout(timeout=5.0)`) that Go never attaches
  (client.go:12-15; the only timer, the 2 s dialer, dies with dropped
  fallbackDial). Any upstream slower than 5 s would error in the port.
- **Action (applied):** owner row now carries the SINGLE CONSTRUCTOR SPEC
  `httpx.Client(proxy=…, trust_env=False, timeout=None,
  follow_redirects=True)`.

### C-3 — shared-client constructor missing follow_redirects=True [divergence, applied]
- **Rule:** §0 bug-for-bug (redirect-following is not on the FIX-FORWARD
  list). **Rows:** the two owner rows for network/client.go vs the http
  shard's non-2xx rows (webfetch :18 / websearch DEFER-CLOSE), which mandated
  the flag "at shared-client construction" but the flag never reached the
  owner rows.
- **What went wrong:** httpx defaults `follow_redirects=False` (probed;
  302 returned as final response) while Go's client follows up to 10
  redirects (probed with the same transport shape as client.go:12-15). A 3xx
  with Location would wrongly raise "search request failed: 302 …" /
  "web fetch failed: 302: …".
- **Action (applied):** folded into the owner row's constructor spec (with
  C-2). max_redirects=10 noted as TODO(port), unjudged.

### C-4 — FF-2 composed-edge contradicted the executable spec [divergence, applied]
- **Rule:** §0 FF-2 — "50 is the default only when absent". **Row:** nil
  shard, tools/websearch handler (Input construction) — claimed "request
  limit 0 → max_results 0 → key omitted; negative → key present", i.e. a
  verbatim pass-through. fixedGo FF-2b (`limit := 50; if input.Limit > 0`)
  sends 50 for 0/negative. Contradicted the wire shard's input row on the
  same handler site.
- **Action (applied):** row corrected to FF-2b semantics (0 or negative →
  50).

### C-5 — DefaultClient fallback was a bare client, not the env-proxy mirror [ambiguity, applied]
- **Rule:** §1 (proxy by hand, trust_env=False always) + Go semantics
  (http.DefaultClient → DefaultTransport → ProxyFromEnvironment honors env
  proxies). **Rows:** nil shard's two cloud-New rows spelled
  `default_http_client() → httpx.Client(timeout=None, trust_env=False)` with
  no proxy, vs the http shard's NIL-DEFAULT row which explicitly forbade the
  bare form.
- **Action (applied):** both New rows now fall back to
  `network.new_client(os.environ.get("HTTPS_PROXY", ""))` — the same
  env-proxy-honoring constructor main.py uses (production-dead either way).

### C-6 — two rows decided the same results-decode oppositely [divergence, applied]
- **Rule:** §0 bug-for-bug — Go's Decode errors on a mistyped `results`
  field and Search returns that error (service.go:103-107). **Rows:** wire
  shard (lenient: `if it is a list else []`) vs nil shard (raise on
  non-list).
- **Action (applied):** wire row aligned to RAISE on a non-list, non-null
  `results` — matching the nil row and Go. (Missing/null → [] unchanged.)

### C-7 — two rows prescribed incompatible TestFetch builds [ambiguity, applied]
- **Row:** tests shard (MockTransport, "not needed here" for sockets) vs nil
  shard item 6 (local HTTP-server fixture) for the same
  grabber_test.go:114-118 site.
- **Action (applied):** nil row defers to the tests shard's MockTransport
  decision (deterministic, no sockets).

### C-8 — Resource constructed as dict in one row, dataclass in another [cosmetic, applied]
- **Action (applied):** nil row now spells `Resource(address=url)` per the
  iface row (mypy strict catches a dict anyway — referee-safe, but the sheet
  should not disagree with itself).

### C-9 — month-year value had two prescribed mechanisms [ambiguity, applied]
- **Rule:** §2 canonical mapping `datetime.now().strftime("%b %Y")`. **Rows:**
  wire shard's prompt-template row mandated an explicit English-month table;
  ctx shard's getMonthYear row mandated the canonical strftime and demoted
  the table to a contingency. Behaviorally identical under C locale (both
  auditors re-probed; one also exposed a mis-transcribed probe transcript in
  the ctx row — corrected earlier in the shard review).
- **Action (applied):** wire row now defers to the §2 canonical mapping; the
  table remains a recorded contingency in the TIME row (add only if any
  setlocale ever appears).

### C-10 — §4 mislabel + §4/§1 overbreadth vs test rows [cosmetic, SPLIT: applied / queued]
- **Part a (applied):** the tests row claimed name-imports are "per §4" —
  §4's example form is module-qualified. Row reworded: name-imports are a
  sanctioned deviation; §4's rationale (two cloud packages → absolute
  imports) still holds.
- **Part b (queued, amendment A-3):** §4 says client.py is the ONLY place
  httpx clients are constructed, while five test rows build
  `httpx.Client(transport=MockTransport…)` inline — impossible to satisfy
  both as written. Amendment adds a test-scope caveat.
- **Part c (recorded only):** §1 "trust_env=False, always" vs bare test
  clients — probed harmless (httpx: `allow_env_proxies = trust_env and
  transport is None`; a MockTransport client never consults env proxies, and
  the bare test client makes no request). No row edit; noted here for the
  human.

### C-11 — §2 regexp anchor note is factually wrong [divergence, queued as A-2]
- **Rule:** §2 regexp row asserts Go `^`/`$` ≡ Python's without MULTILINE.
  False for `$`: Python's also matches before a trailing `\n` (probed on
  both engines: the repo regex matches "https://github.com/o/r/\n" in
  Python, nils in Go; `\Z` matches Go exactly). The inventory rows prescribe
  `$` → `\Z` (faithful); the rulebook forbids it as an unlisted second
  mapping and its note tells implementers the verbatim form is safe.
- **Action (queued):** amendment A-2 corrects the §2 anchor note. Inventory
  rows stand as the faithful translation.

### C-12 — §1 charset row is wrong for BOTH branches (C-1 generalizes) [ambiguity, A-1 extended]
- **Rule:** §1 charset row (param-first, no sniff). **Row:** choice
  processor plain branch — `string(rawBytes)`, i.e. raw bytes to string, NO
  charset detection of any kind; the row's `decode("utf-8",
  errors="replace")` is the faithful translation.
- **What went wrong:** C-1 covered the html path only. A-1's replacement
  text as written describes the html-path DetermineEncoding mirror; applied
  verbatim it could be read to push DetermineEncoding onto the plain branch,
  which Go never does (processor.go:26-31).
- **Action (queued):** A-1's replacement text now scopes both paths — html
  extractor = DetermineEncoding mirror; text/plain = utf-8 errors="replace"
  with NO detection. Inventory row 44 unchanged (already correct).
