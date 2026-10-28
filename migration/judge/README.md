# Parity judge

The migration's exit condition. One harness runs the same scenarios against
the **old Go binary** (the executable spec) and the **Python port** through
the identical public surface — newline-delimited JSON-RPC over stdio (MCP) —
and diffs the observations. "Done" means: every scenario passes its
invariants on both sides and the two sides do not diverge.

Built at the judge-setup phase, before any code was translated. Validated
against the original (17/17 clean, flake-stressed) and against 13
deliberately broken mutants (13/13 caught). Amended at Step 1 (DEV-003) for
the rulebook's FIX-FORWARD spec: now **18 scenarios** with side-aware
contracts, a **fixedGo** conformance binary as the executable spec of the
fixed behavior, and the mutation suite rebuilt on the fixed base — see
[Amendments](#amendments-dev-003-the-fix-forward-spec).

## Layout

| File | Role |
|---|---|
| `harness.py` | Scenarios s01–s18 (side-aware), normalizers, MCP stdio client, runner |
| `proxy.py` | Routing intercept proxy (all egress from both binaries) |
| `run.py` | CLI; exit 0 iff the judge passes |
| `mutations.py` | Mutation validation driver (judge-setup + amendment evidence) |
| `fixedgo.py` | Builds the fixedGo conformance binary: all six FIX-FORWARD edits; `--revert k` drops one fix (pinning validation) |
| `capture.py` | Captures fixedGo's observations → `amendments-capture.json` (pinned-value evidence) |
| `probe.py` | Debug tool: dumps raw protocol shapes of any binary |
| `bin/websearch-go` | Reference build of the Go source (old spec) |
| `bin/websearch-fixedgo` | fixedGo build (executable spec of the FIXED behavior) |
| `amendments-capture.json` | Empirical source of every pinned fixed-side value |
| `fixtures/` | Canned upstream bodies |

## Usage

```sh
# determinism self-checks — amended scenarios are side-branched, so each
# binary must be checked against its OWN contract:
make judge-old      # run.py --old bin/websearch-go  --sides old,old
make judge-fixed    # run.py --old bin/websearch-fixedgo --sides new,new

# the real question, once the port exists (NEW = single executable path)
make judge NEW=<port entry>     # run.py --old bin/websearch-go --new <NEW>

# one scenario, full JSON report
uv run python migration/judge/run.py --old ... --filter s07 --out report.json
```

`--sides OLD,SIDE` (default `old,new`) names the spec contract each binary
is judged against — `old` = original spec, `new` = the rulebook FIX-FORWARD
spec. A plain old-vs-old invocation without `--sides old,old` now FAILS the
amended scenarios by design: their invariants assert side-specific
contracts.

`--new` must be a **single executable path** — the harness spawns
`[path]` with no arguments (`MCPClient`). For the port, ship a wrapper
script that execs the server. Each binary gets: `stdin`/`stdout` pipes, the
scenario env (`BASE_ENV` + `HTTPS_PROXY`), and the same MCP session shape
(initialize → notifications/initialized → tools/list → scenario calls).

## Interception model

`HTTPS_PROXY` is the single egress choke point — both implementations honor
it by construction (`internal/services/network/client.go` sets
`http.ProxyURL`, which proxies **all** schemes; the port must do the same
for plain-http too).

- **Plain-http upstreams** (the cloud stubs `search.test` / `fetch.test`,
  local-grab targets like `example.com`) arrive in absolute-form
  (`POST http://fetch.test/web/fetch HTTP/1.1`) and are served from a
  per-scenario route table: full request visibility — method, path, the
  spec-set headers, body — and full response control.
- **https upstreams** are visible only as `CONNECT host:443` records. TLS
  MITM is impossible here: Go-on-darwin rejects env-provided CAs
  (`SSL_CERT_FILE`) in every build variant (proven empirically — cgo,
  `CGO_ENABLED=0`, and a minimal direct-TLS probe). The proxy therefore
  treats both sides identically: acknowledge the CONNECT, then close. The
  resulting transport failure is canonicalized (below), and **which host
  was CONNECTed to** is the observable: that is how GitHub routing is
  judged.

Every proxied request is recorded (host, method, target, selected headers,
body). Scenarios assert on the records; responses come from the route
table. Request parsing is wire-casing-agnostic (Content-Length lookup is
case-insensitive; `Transfer-Encoding: chunked` bodies are decoded) so a
client with lowercase headers (httpx) is recorded as faithfully as Go's
canonical ones. Proxy-internal failures (parse errors, socket faults) FAIL
the scenario — an observation built on missing records must not pass; idle
keep-alive socket timeouts are the one benign exception. `reset()`
quiesces in-flight handler threads between observations so one scenario's
slow request cannot contaminate the next one's records.

Both binaries also get `HTTP_PROXY`/`ALL_PROXY` (lowercase variants too)
pointed at the judge proxy alongside `HTTPS_PROXY`: the Go binary ignores
them (it reads only `HTTPS_PROXY`), but a `trust_env`-style Python client
would otherwise route the plain-http stubs to an outer proxy and the
scenario would see nothing.

## Normalization rules

| Rule | Where | Rationale |
|---|---|---|
| Drop SDK extras (`ttlMs`, `cacheScope`), sort tools | `norm_tools_list` | SDK decoration, not app behavior |
| Month-year → `<MONTH-YEAR>`; keep a `description_has_month_year` flag computed from the RAW text | `norm_tools_list` | WebSearch's description embeds `time.Now()` — time-dependent on both sides. The flag catches a port hardcoding the literal marker instead of a real date |
| Drop `$schema`, sort `required`, sort union type lists | `norm_schema` | Key order is not semantic; everything else compared exactly |
| Transport-error text → `{transport_error: true, text: null}` — only when the text does NOT start with an app-error prefix | `norm_call` + `APP_ERROR_RE` + `TRANSPORT_ERROR_RE` | Runtime error phrasing (Go net/http vs Python httpx/requests) is not spec. `APP_ERROR_RE` pins the app's own error strings (compared exactly, even when they embed upstream bodies); `(?<!unexpected )EOF` keeps Go's upstream-payload decode error out of the transport class |
| Success `text` → `null` whenever structured output is available (directly or by parsing the text) | `norm_call` | On success, `content[0].text` is the SDK's JSON serialization of the structured output — Go `json.Marshal` (compact, HTML-escaped) vs Python `json.dumps` (spaced, `ensure_ascii`) differ by construction. The structured dict — order-insensitive — is the comparison; error text stays exact |
| `content_blocks`: the list of content block TYPES is compared | `norm_call` | A port emitting extra or non-text blocks must diverge even when block 0 matches |
| Side-aware waivers: the OLD literal and the FIXED literal map to the SAME marker | `Scenario.canonicalize(obs, side)` | The rulebook's FIX-FORWARD spec makes old and new deliberately differ in six places. A waiver erases exactly those deltas for the diff — applied **after** invariants (which see the raw observation), so a marker can never satisfy an invariant. Any third value — including the old value emitted by the new side — stays literal and diverges |
| `s06` old-side content → `<FIXED-CONTENT>` | `S06.canonicalize` | The OLD code's plain-text read races its closed body (observed both delivered and empty across runs of the original); the fixed side delivers verbatim and is pinned by invariant, not waived |
| Proxy records: absolute-form → path, JSON bodies parsed, 4 headers kept | `norm_proxy_requests` | Compare routing + deliberate headers; other headers are transport noise |
| `stdio_noise`: non-JSON stdout lines and late/duplicate responses are recorded and compared (normally empty) | `MCPClient` | A port leaking noise onto the protocol stream must diverge |
| Initialize: `serverInfo` compared exactly; `protocolVersion`/`capabilities` dropped | `observe` | serverInfo is app-set (`main.go`); the rest is SDK negotiation |

Error strings **our code produces** — "query must not be empty", "URL must
be fully-formed and start with http:// or https://", "search request
failed: …", "HTTP %d: …" — are compared exactly; they are spec. ("web
fetch failed: …" is also spec but unreachable through the public surface:
the complex service always discards the cloud error and falls back to
local — the port's unit tests cover it.)

## Scenarios

| # | Name | Guards |
|---|---|---|
| s01 | `tools_list` | Tool names; BOTH descriptions byte-for-byte modulo month-year (templates pinned as constants, incl. a `description_has_month_year` real-date check); outputSchema title key side-aware (old `"query"` / fixed `"title"` → marker, FF-1); new side additionally asserts the `limit` input property (FF-2); required arrays; initialize `serverInfo` `{websearch, v1.0.0}` |
| s02 | `websearch_happy_linkup` | 6-result snippet-precedence matrix, KEPT bug-for-bug (snippet wins → `content.text` → raw string → raw JSON echo of a textless object); result title key side-aware (FF-1); POST `/search`, Bearer auth, `Content-Type: application/json`, body `model`/`query`/`max_results: 50` on BOTH sides — the old SDK rejects unknown arguments (`additionalProperties: false`), so the limit contract lives in s18 |
| s03 | `webfetch_cloud_happy` | Cloud fetch success: url echo is the REQUEST url (trap: fixture carries a different one)/title/text/length; POST `/web/fetch`, Bearer, content-type, body `model`/`url`/`format: markdown`; local grabber must NOT fire |
| s04 | `websearch_empty_query` | Exact error text; no network |
| s05 | `webfetch_non_http_url` | Exact error text for `ftp://`, schemeless, AND uppercase `HTTP://` (case-sensitive prefix check); no network |
| s06 | `plaintext_passthrough` | Local grabber request surface (UA side-aware: old Chrome-string / fixed Firefox-158, FF-4; exact Accept header); cloud-first ordering; content side-aware — old canonicalized (closed-body race), fixed side pinned verbatim: the multibyte `plain.txt` text AND its 48-BYTE length (FF-5; byte semantics) |
| s07 | `html_extraction_rich` | Old side: extraction returns `""`/0 (closed body). Fixed side: the FULL extraction output pinned (639 bytes, incl. the goquery nested-`<code>`-inside-`<p>` emission quirk) — FF-5 makes the extraction pipeline live |
| s08 | `html_charset_cp1251` | Old side: `text/html; charset=…` misses the exact-match switch → default branch → `""`. Fixed side: media-type match (FF-6) + live body (FF-5) → the cp1251 page is DECODED, pinned (354 bytes, Russian text) — the old charset gap is now judged |
| s09 | `json_content_empty` | `application/json` → `""` (choice postprocessor's json branch) |
| s10 | `local_http_error` | Local grabber non-200 → exact `HTTP 500: 500 Internal Server Error` (and the cloud error it swallowed) |
| s11 | `github_routing` | CONNECT sequence `raw.githubusercontent.com, api.github.com, api.github.com, api.github.com` for file/repo/issue/pull URLs; no `github.com` CONNECT; all fail as transport errors |
| s12 | `github_fallback` | Regex-miss URL → `github.com` CONNECT (generic grab fallback) |
| s13 | `cloud_failover_to_local` | Cloud 500 → local grab of `example.com`; content side-aware: old `""` (closed body), fixed pinned text+length (FF-5); UA side-aware (FF-4) |
| s14 | `search_http_error` | WebSearch cloud non-2xx → exact `search request failed: 500 Internal Server Error` |
| s15 | `iscangrab_variants` | Host/scheme routing: `http://github.com/o/r` → `api.github.com` (repo regex tolerates http); `www.github.com/o/r` → `www.github.com` (IsCanGrab yes, regex miss → fallback grabs the original URL); `gitlab.com/o/r` → `gitlab.com` (IsCanGrab no → client grabber) |
| s16 | `empty_api_keys` | Empty API keys: webfetch sends NO Authorization (already conditional in the source); websearch side-aware — old `Bearer` (unconditional) / fixed absent (FF-3) — observed in absolute-form headers |
| s17 | `search_empty_results` | Empty results serialize as `[]`, never `null` (the Go SDK erases nil slices, so the old side cannot emit null — this invariant pins the old side; a port emitting null diverges) |
| s18 | `search_limit_honored` | FF-2 wire contract, probed with `{"query": …, "limit": 2}`. New side: success, 6 results, exactly one POST `/search` with `max_results: 2`. Old side: the go-sdk REJECTS the unknown argument (`validating "arguments": … unexpected additional properties ["limit"]`, isError, no traffic) — itself pinned. Each side's whole observation reduces to the same `<LIMIT-CONTRACT>` marker ONLY on an exact shape match; anything else diverges |

## Spec quirks: kept vs fixed forward

The Step-1 rulebook (RULEBOOK.md §0) has ruled on the quirks the judge
documented at setup. **Kept bug-for-bug** — both sides must match the old
binary exactly:

1. **Month-year description** — WebSearch's description embeds
   `time.Now().Format("Jan 2006")` (abbreviated month). Normalized to a
   marker; the whole template compares byte-for-byte (s01) and a real-date
   flag forbids hardcoding the marker.
2. **Snippet precedence** — snippet wins → `content.text` → raw string →
   raw JSON echo of a textless object. s02's six-row matrix pins all four
   branches (the Go test covered only the first).
3. **`"web fetch failed: …"` unreachable** — the complex service always
   discards the cloud error and falls back to local; the string stays spec
   (byte-exact per RULEBOOK §2) but is only exercised in port unit tests.
4. **nil → `[]`** — the Go SDK erases nil slices before the wire; s17
   guards the port side via the divergence check.

**Fixed forward** (FF-1..FF-6): the `"query"` title key, the hardcoded
`Limit: 50`, the unconditional search Authorization, the Chrome-string
Firefox UA, the closed-body read, and the exact Content-Type switch. The
port implements the FIXED behavior; the judge pins both directions of each
delta — see [Amendments](#amendments-dev-003-the-fix-forward-spec). Note
FF-5 (+FF-6) turned two former coverage gaps into judged behavior: charset
decoding and byte-vs-char lengths are now pinned through the public surface
(s06/s07/s08/s13).

## Amendments (DEV-003): the FIX-FORWARD spec

The rulebook's FIX-FORWARD list changes the spec: the port must exhibit
the FIXED behavior, which the original binary does not have. The judge
therefore gained a second spec contract, and its scenario methods became
**side-aware** — `canonicalize(obs, side)` and `invariants(obs, side)`:

- **Invariants see the RAW observation** and assert each side's real
  contract — including the fixed contract on the new side. A waiver never
  becomes a free pass: emit the old value on the new side and the
  invariant fails before any canonicalization.
- **Canonicalization only shapes the old-vs-new diff.** A waiver maps the
  OLD literal and the FIXED literal to the SAME marker; any third value —
  including the old value emitted by the new side — stays literal and
  diverges.

### Waivers and pins

| Fix | Old behavior ↔ Fixed behavior (same marker) | Pinned by |
|---|---|---|
| FF-1 title key | result key `query` ↔ `title` → `<TITLE-KEY>` (outputSchema properties + required, s01; result rows, s02) | s01, s02 |
| FF-2 limit honored | no `limit` input, `max_results: 50` always ↔ schema gains `limit` (int), positive values honored, 50 default → `<LIMIT-CONTRACT>` (whole-observation shape match only) | s01 (schema), s02 (`max_results: 50`), s18 (`limit: 2` → one POST, `max_results: 2`, 6 results; old side: SDK rejects the unknown arg) |
| FF-3 auth symmetry | search sends `Bearer` with empty key ↔ sends nothing → `<AUTH-EMPTY-KEY>` (search host only; webfetch was already conditional) | s16 |
| FF-4 real Firefox UA | Chrome/91 string ↔ `Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0` → `<UA-FIXED>` | s06–s10, s13 |
| FF-5 body before close | plain-text raced/empty, HTML always `""` ↔ body read (5 MB cap) before close → `<FIXED-CONTENT>` | s06 (text + 48 bytes), s07 (639 bytes incl. nested-code quirk), s08, s13 |
| FF-6 media-type match | exact `Content-Type` string switch ↔ match on media type before `;`, lowercased, trimmed → `<FIXED-CONTENT>` | s08 (cp1251 decoded, 354 bytes) |

Every pinned fixed-side value (PLAINTEXT 48, RICH 639, CP1251 354, the
failover text, the FF-4 UA literal) was **captured from the fixedGo
binary** by `capture.py` → `amendments-capture.json` — never hand-derived.

### The fixedGo conformance binary

`fixedgo.py` applies the six fixes as nine exact-match edits (each asserts
count==1) to a copy of the Go source and builds `bin/websearch-fixedgo` —
the executable spec of the fixed behavior, exactly as the original binary
is the spec of the old one. `--revert k` builds the same binary WITHOUT
fix k; used to prove each waiver pins its fix.

### Validation matrix (all green)

1. **Reference self-check** (`make judge-old`, `--sides old,old`): 18/18.
2. **fixedGo self-check** (`make judge-fixed`, `--sides new,new`): 18/18.
3. **Conformance, old vs fixedGo** (default sides): 18/18 — the waivers
   cover exactly the six fix deltas, nothing more.
4. **Revert binaries** — all six CAUGHT, each by its pinning scenarios:
   FF-1 by s01+s02, FF-2 by s01+s18, FF-3 by s16 (invariant: Authorization
   sent with an empty key), FF-4 by s06–s10+s13, FF-5 by s06+s07+s08+s13,
   FF-6 by s08. No spurious failures anywhere else.
5. **Mutation suite rebuilt on the fixed base** — 13/13, see the table in
   Validation evidence.
6. **Stress**: 3× each of runs 1–3, zero flakes.

## Documented coverage gaps

Not observable through the public surface under this interception model;
each goes to the **port's own unit tests** (ported from the Go tests) and to
the rulebook's open questions:

- GitHub grabber request details beyond host: `Accept:
  application/vnd.github.v3+json` header, api path rewrites
  (`/repos/{o}/{r}` → `/repos/{o}/{r}/issues/{n}`, `pull` → `pulls`), the
  github grabber UA — all ride https, invisible at CONNECT level.
  **Port warning:** `grabber_test.go`'s UA assertion ("websearch/1.0") is
  STALE — the source sends the Firefox fingerprint
  (`github/grabber.go:74`). Port the routing table; assert the source's UA.
- `raw.githubusercontent.com` file content and its byte-length echo —
  https upstream, tunnel closes before TLS.
- The 5 MB response cap (`io.LimitReader`) — would need a >5 MB plain-http
  body; not judged.
- Byte-vs-char `content.length` for ARBITRARY pages — the byte semantics
  themselves are now judged on the fixed side (s06: 48, s07: 639, s08:
  354, s13: pinned), but only for the fixture bodies; the port's unit
  tests still own the general case.
- Charset DECODING beyond the cp1251 fixture — s08 pins one windows-1251
  page end-to-end; other charsets/labels (utf-16, missing labels, meta
  sniffing precedence) remain port unit-test territory.
- `"web fetch failed: …"` (cloud fetch non-2xx) — unreachable publicly:
  the complex service discards the cloud error and falls back to local.
- nil-vs-`[]` output serialization — the Go SDK erases nil slices to `[]`
  before the wire, so the old binary cannot emit `null`; s17 guards the
  port side via the divergence check only.
- SDK-negotiated fields (protocolVersion, capabilities, tool metadata like
  `title`/`annotations`) — judged as absent by design (dropped in
  normalization); a rulebook decision if the port's SDK surfaces them.
- Unknown-argument tolerance — the OLD SDK's behavior is now pinned (it
  REJECTS unknown arguments; s18's old branch), and s18's new branch
  requires the port's SDK to accept `limit`. Tolerance for other unknown
  arguments remains the port SDK's behavior to match or the rulebook to
  waive at Step 6.

## Adversarial review (judge-setup step 2)

Two opus reviewers, separate contexts, disjoint batches, read-only:

- **Coverage reviewer** — 16 findings. High: WebSearch's non-2xx error
  string unpinned (→ s14), false claim that s11 covered the byte-length
  trap (→ comments corrected, moved to gaps). Medium: stale `websearch/1.0`
  UA in the Go test (→ port warning), IsCanGrab variants unjudged (→ s15),
  s10 substring compare (→ exact), serverInfo/descriptions unpinned (→
  s01), raw-JSON snippet branch (→ s02 r5), auth asymmetry (→ s16). Low:
  s08's wrong causal story (→ corrected: default branch, not closed-body),
  vacuous-pass risk (→ url-echo + request assertions), content-type header
  unpinned (→ s02/s03), unreachable error string documented (→ README),
  empty-results shape (→ s17), month-year marker hardcoding (→ real-date
  flag).
- **Comparator/mechanics reviewer** — 13 findings. High: `content[0].text`
  compared byte-exactly though it is SDK serialization (→ dropped on
  success when structured output exists — would have wrong-FAILED every
  structured call at Step 6); s06's canonicalize missed the same field
  inside `text` (→ same fix); proxy body collection keyed on exact-case
  `Content-Length` with no chunked support (→ case-insensitive + chunked
  decoding). Medium: proxy errors not gating (→ gate, idle-timeouts
  exempt); inherited `HTTP_PROXY`/`ALL_PROXY` (→ scrubbed/overridden);
  multi-content masked (→ `content_blocks`); mutants counting crashes as
  caught (→ new-side/divergence classification + reference pre-flight).
  Low: silent reader-thread drops (→ `stdio_noise` compared), reset
  contamination window (→ quiesce), invariants raising on odd shapes (→
  guarded, converted to failures), transport-RE gaps + latent
  "unexpected EOF"/body-embedding collisions (→ patterns added;
  `APP_ERROR_RE` prefix gate).

All confirmed findings fixed; both reviewers also verified large clean
lists (per-result matrices, exact error compares, ordering soundness,
mutation construction — in the review records).

## Validation evidence (judge-setup gate)

- **Clean run:** 17/17 old-vs-old (after all review fixes), plus stress
  reruns with zero flakes (6× full suite + 10× s11 pre-review; 5× full
  suite post-review). One tunnel-close race flake was root-caused and the
  transport-error class broadened before this evidence was taken.
- **Mutants:** `mutations.py` pre-flights the reference binary
  (`--sides old,old`), then builds each mutant from the **FIXED source**
  (all six FIX-FORWARD edits via `fixedgo.EDITS`) plus exactly one
  mutation, and runs the judge old-vs-mutant; a mutant counts as caught
  ONLY on a new-side invariant failure or a divergence (a judge crash is
  an ERROR, not a catch). The fixed base is what keeps a catch meaningful:
  the first amendment-era run built mutants from the ORIGINAL source and
  every one of them was "caught" by the same ten scenarios (the six fix
  contracts fail on the new side regardless of the mutation) — a green
  light that fires on anything isolates nothing. On the fixed base only
  the named mutation can diverge. Two anchors are written against the
  fixed tree: m2 mutates the FF-4 UA literal, m4 misspells the FF-1
  `title` tag (the pre-amendment m4, query→title, is now the sanctioned
  spec and would correctly PASS). 13/13 caught:

  | Mutant | Caught by |
  |---|---|
  | m1 snippet precedence flip | s02 |
  | m2 client UA fingerprint altered (FF-4 literal) | s06–s10, s13 |
  | m3 WebFetch URL check dropped | s05 |
  | m4 `"title"` → `"titre"` JSON tag (FF-1 tree) | s01, s02 |
  | m5 choice json branch returns content | s09 |
  | m6 github file regex broken | s11 |
  | m7 complex: no local fallback | s06–s13, s15 |
  | m8 search error string altered | s14 |
  | m9 repo regex http-intolerance | s15 |
  | m10 webfetch auth unconditional | s16 |
  | m11 results dropped from output | s02, s18 (also breaks the limit shape) |
  | m12 description template altered | s01 |
  | m13 month format (Jan → January) | s01 |

## Step 6 contract

A migration is behavior-matched when `make judge NEW=<port>` (=
`run.py --old bin/websearch-go --new <port>`, default sides old,new) exits
0: every invariant holds on the old binary (sanity), on the port
(correctness — against the FIX-FORWARD spec), and no normalized
observation diverges. A flaky rerun is diagnosed, not re-rolled: rerun the
single scenario with `--filter` and read the JSON report before concluding
anything.

The judge stays runnable (and the Go source stays buildable) until that
gate passes.
