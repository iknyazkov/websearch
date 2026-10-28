# Translation Rulebook — Go → Python

> **The meta-rule: if two agents could answer a question differently, the
> answer goes in this file.** This document is read by every implementer,
> reviewer, and fixer before they touch code. It is read-only inside any loop —
> amendments are queued for the human and applied between batches.

Read this whole document before writing any code.

Source of truth: `/Users/iknyazkov/Downloads/websearch` (Go, read-only, module
`github.com/Stampoo/websearch`). Target: `src/websearch/` in this repo
(uv + Make). The old code is the spec except where §0's FIX-FORWARD list says
otherwise. Parity is judged by `migration/judge/` (17 scenarios; see its
README for the interception model and normalization rules).

## 0. Scope and posture

- This is a **structure-preserving** migration: same architecture, same data
  structures, same file boundaries unless a rule below says otherwise. You are
  translating, not improving — except for the sanctioned fixes below, which
  are part of parity, not improvements smuggled in.
- **The referee runs in-loop.** Every translated unit must pass
  `make lint typecheck` (ruff + mypy strict, ≈2–5 s combined) before it counts
  as drafted. This is the promoted cheap referee (feasibility prediction);
  Step 4 dissolves into Step 3. Drafts do not need to *run*, but they must
  *typecheck*.
- First pass optimizes for **correct translation**, not performance. Known
  slow-but-faithful translations are fine: mark them `PERF(port):` with one
  line on what the fast version would be, and move on.

### FIX-FORWARD list — sanctioned 2026-10-26 (human decision at rulebook gate)

Six defects are FIXED in the port. Each fix is part of parity: the judge is
amended to assert the fixed behavior (new-side assertion + field-scoped
waiver of the old side's known divergence). Everything NOT on this list ports
bug-for-bug.

| ID | Fix | New spec | Judge amendment |
|---|---|---|---|
| FF-1 | `"query"` JSON key | `SearchHit.Title` serializes as `"title"` in results AND the outputSchema property is `title` | s01 schema property, s02 result keys — assert `"title"` on the new side; the `query` divergence is waived for that field |
| FF-2 | hardcoded `Limit: 50` | the request's `limit` argument is honored; 50 is the default only when absent | s02 passes `limit: 2` and asserts `max_results: 2` reaches the request body |
| FF-3 | auth asymmetry | NO `Authorization` header when the API key is empty — both tools | s16: websearch side asserts header absent (webfetch side already does) |
| FF-4 | stale UA fingerprint | the `Firefox` constant is a real current Firefox UA, pinned exactly: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0` | s06: UA pinned to the literal above on the new side |
| FF-5 | closed-body bug | the response body is read (capped, §2) BEFORE the response is closed; HTML extraction actually runs; plain-text delivery is deterministic | s06 drops the `<closed-body-race>` canonicalization and asserts delivered text; s07/s13 assert the pinned extracted text of their fixtures |
| FF-6 | exact-match Content-Type | match on the media type only — parse before `;`, lowercase, strip whitespace (`text/html; charset=windows-1251` matches the `text/html` branch); charset pages decode per §2 | s08 asserts the decoded cp1251 fixture text |

The FIX-FORWARD edits are not `BUG(port):` sites — they are the spec. The
judge amendments land immediately after this rulebook is signed off, BEFORE
the gap inventory (several amendments create new inventory surface, e.g.
charset decoding under FF-6).

### Kept bug-for-bug (markers required, judge unchanged)

| Quirk | Marker site |
|---|---|
| Month-year embedded in WebSearch's description (`%b %Y`, live `now()`) | `tools/websearch/prompt.py` — live behavior, not a defect; judge normalizes it |
| `content.length` counts UTF-8 BYTES (`len(s.encode())`), never chars | `services/webfetch/local/service.py` — `BUG(port): Go byte semantics` |
| Snippet precedence: snippet wins → `content.text` → raw string → raw JSON echo | `services/websearch/cloud/service.py` — design choice, kept |
| `"web fetch failed: …"` error string (publicly unreachable — complex service always falls back to local) | `services/webfetch/cloud/service.py` — translate it anyway; unit tests cover it |

### Dead code — dropped (sanctioned 2026-10-26)

`internal/services/logger` (4 files) and `internal/services/webfetch/local/
postprocessor/markdown` (1 file) have zero importers (adversarially verified,
`migration/depmap/review-record.md`) and are unobservable through the public
surface. They are NOT ported; `migration/manifest.tsv` reflects this (31
units). This is the only exception to §4's one-file-one-target rule.

## 1. Ecosystem adoption — what we use and what we ban

| Area | Decision | Why |
|---|---|---|
| MCP server | **official `mcp` Python SDK, LOW-LEVEL `Server`** (`mcp.server.Server`; registration via `on_list_tools`/`on_call_tool` constructor kwargs or `add_request_handler("tools/list"\|"tools/call", params_type=…, handler=…)` — the pinned mcp 2.3.0 has NO `@list_tools`/`@call_tool` decorators, probed round 2). `add_request_handler` REPLACES any prior handler for a method, so every tool unit's register() must CHAIN-WRAP the previously-registered handler (compose, never clobber) — Go's `mcp.AddTool` accumulates and both tools must coexist on one Server. FastMCP and any auto-schema-from-type-hints mechanism are **BANNED** | Schema shapes are byte-spec (judge s01); Go's jsonschema-go generation has no faithful Python counterpart — §4 says hand-written schema dicts. FastMCP would invent its own. Round-2 bakeoff: the decorator wording sent an implementer hunting a nonexistent API and gave the native baseline cover to bail to the banned MCPServer layer |
| Async model | asyncio ONLY in the server layer (the SDK is async). The service layer stays SYNCHRONOUS (mirrors Go). Handlers call services via `asyncio.to_thread` | Go services are plain sync functions; keeping them sync preserves structure and makes them unit-testable without an event loop |
| HTTP client | **httpx** (`httpx.Client`, sync). `trust_env=False`, always; the proxy is read from the `HTTPS_PROXY` env var by hand (in `services/network/client.py`) and passed as `proxy=…` — it proxies ALL schemes, exactly like Go's `http.ProxyURL` | The judge's entire interception model depends on all-scheme proxying through one env var; `trust_env=True` would honor `HTTP_PROXY`/`ALL_PROXY` the Go binary ignores |
| HTML parsing | **BeautifulSoup4** with the stdlib `html.parser` backend; selectors via `select`/`select_one` (soupsieve CSS) | goquery is CSS-selector-based over x/net/html; lxml is banned (extra native dep, different tree semantics) |
| Charset decoding | TWO scoped paths. **HTML extractor path** (`html.Handle`): mirror x/net `DetermineEncoding` on the raw body bytes (the declared `Content-Type` parameter NEVER reaches the decoder — `html.Handle` hardcodes `"text/html"`): first 1024 bytes → BOM table (x/net order) → meta prescan (`<meta charset>`, `<meta http-equiv>`; attribute-order-agnostic) → UTF-8-validity heuristic → **windows-1252 default**; decode with `errors="replace"`. **text/plain path** (choice processor): `data.decode("utf-8", errors="replace")` — NO charset detection of any kind (Go: `string(rawBytes)`; processor.go:26-31) | fixedGo's pinned cp1251 decode (judge s08, 354 bytes) comes from meta http-equiv sniffing, not the header param — `charset_1251.html` declares charset only in-document. The plain branch never sniffs: applying the html mechanism there would decode cp1251 bodies Go renders as mojibake. Evidence: `inventory.tsv` rows 1 and 44, `conflicts.md` C-1 + C-12 |
| String/bytes policy | `str` everywhere internally; `bytes` only at the HTTP boundary, decoded immediately per the charset rule. Any Go `len(string)` that crosses the wire → `len(s.encode("utf-8"))` | Go strings are bytes; Python's are text. FF-5/FF-6 make real page content flow — the boundary must be explicit |
| Third-party deps | runtime: `mcp`, `httpx`, `beautifulsoup4`. dev: `pytest`, `ruff`, `mypy` (already scaffolded). Everything else **BANNED** without an amendment here — no `requests`, `aiohttp`, `lxml`, `pydantic` models for wire shapes | A 36-file server needs three deps; every extra one is drift surface |
| Error model | exceptions, typed per §2 — no return-code tuples | §2 |

## 2. Constructs with no equivalent — one canonical mapping each

Every Go construct Python lacks (or translates ambiguously) gets exactly one
translation, listed here. An implementer who invents a second mapping for a
listed construct is violating a rule; a reviewer who sees an unlisted
construct flags it for this table.

| Source construct | Canonical target translation | Notes / evidence |
|---|---|---|
| `error` return values | raise a typed exception; the wire-visible message is the **byte-exact** Go format output | The judge compares app error strings exactly. The pinned strings: `query must not be empty` · `URL must be fully-formed and start with http:// or https://` · `search request failed: {status}` · `web fetch failed: {status}: {body}` · `request failed with status {code}` (github grabber, grabber.go:86) · `HTTP {code}: {status}` (status = Go's `resp.Status`, e.g. `500 Internal Server Error`). Reason-less status lines: Go renders a bare `HTTP/1.1 500` as `500` with NO trailing space; Python `f"{code} {reason}"` yields `500 ` (httpx, empty reason) or `500 None` (requests) — strip the trailing space or fall back explicitly |
| `errors.New` surfaced through a pinned message string | module-level class named for the pinned message subject, deriving `Exception` | webfetch twin: `CloudWebFetchError(Exception)` (inventory row 16); websearch twin: `CloudWebSearchError(Exception)` (inventory row 74). Never `RuntimeError`, never invented second names — two agents answering differently is the failure this row prevents |
| multiple returns `(T, error)` | single return; raise on error | |
| `defer` | `try/finally` | httpx responses close via context manager — but FF-5 ordering applies: read BEFORE close |
| `io.LimitReader(body, 5<<20)` | `resp.content` is already fully read by httpx; enforce the cap explicitly: take at most `5*1024*1024` bytes | The 5 MB cap is spec (client/grabber.go) |
| interfaces (`WebFetchService`, grabber/postprocessor interfaces) | `typing.Protocol` with the same method sets; implementations register exactly where Go's do | |
| field deref that cannot be nil after `New()` (e.g. `*s.cfg.HTTPClient`) | keep the field `Optional` in the dataclass; mirror the deref with an adjacent `assert … is not None` + comment | NEVER default the Config field to a constructed client — that erases the nil-zero semantics the `New()` fallback exists for (inventory rows 10/11/64). The assert is the deref-panic analogue; `python -O` degrades it to an AttributeError inside the client call, never a silent wrong client |
| `nil` slice over the wire | `[]`, never `None` | s17; the Go SDK erased nils to `[]` — the port must never emit `null` for a list field |
| `time.Now().Format("Jan 2006")` | `datetime.now().strftime("%b %Y")` | Abbreviated month — live behavior, kept |
| Go regexp (RE2) | Python `re`, pattern text translated verbatim except Go `$` → Python `\Z` | All in-repo patterns are RE2-safe. Go `^`/`\Z` are string boundaries like Python's without `re.MULTILINE`. Go's `$` is end-of-text ONLY — Python's `$` also matches before a trailing `\n`, so translate Go `$` as Python `\Z` (or use `re.fullmatch`). Pattern text otherwise translates verbatim. Go `\d`/`\w`/`\s`/`\b` are ASCII-only classes (regexp/syntax/perl_groups.go); Python's are Unicode for str patterns — compile any pattern using them with `re.ASCII` (a no-op when the pattern contains none) |
| `string(bodyBytes)` | decode per the §1 charset rule | |
| struct JSON tags (incl. the fixed `title`) | build output dicts explicitly at the wire boundary — no dataclass `asdict`, no pydantic | Explicit construction makes key names (FF-1) and shapes impossible to drift |
| `json.Unmarshal` into a struct (field-name matching) | iterate `dict.items()` in document order; match `key == "FieldName"` or `key.lower() == "fieldname"`; last match wins | encoding/json decode.go:699-703 folds case (byExactName → byFoldedName); a non-string value where Go's field is `string` fails Go's whole Unmarshal — mirror by treating that decode as failed, not by coercing |
| jsonschema-go tag generation | hand-written schema dicts in the tool's input/output modules | Byte-shaped to the judge's pinned s01 schema (minus SDK noise, which is normalized anyway) |
| `context.Context` params | drop them from ported signatures | No ported site observes cancellation mid-flight; if one appears, it goes to the inventory, not an ad-hoc design |
| goroutines/channels | not needed — logger (the only user) is dropped; the mcp SDK owns server concurrency | If a site surprisingly needs background work: `TODO(port):`, inventory row, stop |
| Go map iteration (random order) | never emit a dict where the source emitted a sorted/ordered structure; build lists explicitly | |
| `http.ProxyURL` all-scheme proxying | `httpx.Client(proxy=<HTTPS_PROXY value>, trust_env=False)` | §1, network/client.py |

**The BUG rule:** source behavior that is itself defective and NOT on the
FIX-FORWARD list is reproduced bug-for-bug and marked `BUG(port):` with a
repro. Behavior matching (Step 6) asserts the defective output; the
FIX-FORWARD list above is the exhaustive set of sanctioned exceptions — fixes
beyond it ship only as flagged post-parity changes.

**The UNKNOWN rule:** when neither this table nor the inventory decides a
case, translate to the most conservative representation Python offers, mark
it `TODO(port):` with the open question, and keep moving. UNKNOWN is an
answer; a stalled batch is not.

## 3. The sanctioned escape hatch

Python has no `unsafe`; the pressure valves are type-system suppressions, and
they carry the same visibility rules:

- `# type: ignore[<code>]` is allowed ONLY with an adjacent
  `# SAFETY: <why this is sound>` line — never to silence an error the port
  could fix. Expected legitimate uses: mcp-SDK boundary types, soupsieve
  return shapes.
- `cast(...)`/`Any` only at the SDK boundary, each with a `# SAFETY:` line.
- Deferred decisions carry greppable markers: `TODO(port):`, `PERF(port):`,
  `BUG(port):` (plus `SAFETY:` on every suppression). These markers are the
  queue for later steps — the format is load-bearing, do not vary it.

## 4. Naming and output paths

Done-ness is detected by output files existing on disk, so these rules are
what make the whole run resumable. They are not style preferences.

- `internal/<path>.go` → `src/websearch/<path>.py`; `main.go` →
  `src/websearch/main.py`. One source file, one target file — the single
  exception is the §0 dead-code drop.
- Each Go package directory → a Python package (`__init__.py`, kept EMPTY —
  no implicit re-exports). A Go file `foo.go` in that directory → module
  `foo.py`.
- Same-package cross-file references (Go's shared package namespace): import
  the sibling module and qualify — `from websearch.services.websearch.cloud
  import output` then `output.Output`. Never relative imports (`from .`),
  never star imports: two different packages both named `cloud` exist, and
  absolute qualified paths are the only unambiguous mirror of Go's import
  paths (depmap review finding 2/7).
- Test files: `*_test.go` → `*_test.py` **in place**, next to the module.
  `*_test.py` is a pytest default collection pattern; the 1:1 mapping keeps
  the manifest the single source of done-ness. The stale Go UA assertion in
  `grabber_test.go` is corrected in the port (judge README, coverage gaps).
- Shared types live in the module that owns them in Go (`output.py` owns
  `Output`); no central types module, no copies.
- Home module for the HTTP client: `services/network/client.py` — the ONLY
  place httpx clients are constructed and the proxy rule (§1) is applied.
  Exception: test-local clients over `httpx.MockTransport` may be
  constructed inline in `*_test.py` — the rule exists to centralize the §1
  proxy rule for production egress, which a mock-transport client never
  exercises.
- Go parameter/field/method names that are legal Python stay VERBATIM —
  noqa'd when they shadow a builtin (e.g. `search(self, input: Input)`
  mirrors Go's `Search(ctx, input Input)`); renames are not sanctioned.
  Case-split: single-identifier Go names stay verbatim (`input`,
  `search`); MULTI-WORD Go identifiers snake_case mechanically
  (`IsCanGrab` → `is_can_grab`, `getMonthYear` → `get_month_year`,
  `webSearchService` → `web_search_service`). One
  forced exception: mypy strict Protocol compatibility compares
  positional-or-keyword parameter NAMES, so when Go's interface and its
  implementations spell a parameter differently, the majority Go spelling
  wins everywhere (webfetch `fetch`: `url`). Zero-guard style
  (`== ""` vs `not x` on a str) is out of scope — not a finding.

## 5. The gap inventory

Decisions about a specific call site (which charset branch, which guard kind,
which quirk applies) are **not made by implementers**. They are looked up:
`migration/inventory.tsv`, one row per site. If your site isn't in the
inventory, that's an inventory bug — flag it, apply the UNKNOWN rule, keep
moving.

## 6. Per-file obligations

Every translated file ends with a status trailer:

```
# PORT STATUS: confidence=[high|medium|low] todos=[N]
```

Reviewers check the trailer against the file's actual `TODO(port)` count —
a trailer that undercounts is a finding.

## 7. Deviation log

Every departure from the documented process gets one line here — skipped
passes, waived checks, untriggered defaults. ID'd `DEV-001` style: ID, date,
what was skipped or waived, who sanctioned it. Written at gates, by the human
or with the human's sign-off. A deviation nobody logged is a deviation nobody
approved.

| ID | Date | Deviation | Sanctioned by |
|---|---|---|---|
| DEV-001 | 2026-10-26 | Depmap adversarial-review sampling adapted: reviewer A 18+2 files, reviewer B 18 files + repo-wide reverse checks (full 36-file coverage, 2-file intentional overlap) instead of literal disjoint 20+20 — impossible over 36 files | Human, Step-1 gate |
| DEV-002 | 2026-10-26 | Dead packages `logger` + `markdown` dropped; manifest 36→31 units | Human, rulebook gate |
| DEV-003 | 2026-10-26 | Six fix-forward quirks sanctioned (FF-1…FF-6); judge amendments to follow before gap inventory | Human, rulebook gate |
| DEV-004 | 2026-10-26 | Step 4 dissolved into Step 3: mypy strict + ruff promoted as in-loop referee; human removes the denies from settings.json at the kickoff gate | Human, rulebook gate |
| DEV-005 | 2026-10-27 | Inventory skeptic reviewers (first 20-row batch) ran on glm-5.3-flash instead of the planned opus — workflow model override not honored; findings accepted after per-finding source verification | Human, round-1 gate |
| DEV-006 | 2026-10-27 | Stress-test pilot round 1: implementer shipped units with §1 deps undeclared and 8 imported sibling units absent, so the §0 referee could not run while trailers claimed confidence=high/medium; fixer declared deps, created the units + URL-JOIN tests, downgraded trailers to confidence=low; uv.lock regen deferred (builds denied in-loop) | Human, round-1 gate |
| DEV-007 | 2026-10-27 | Stress-test round 1: all 7 workflow agents remapped by the runtime — requested opus ran as glm-5.3-flash (both reviewers + diff inspector), requested sonnet as glm-5.3 (translators, implementer, fixer); 2nd occurrence of the opus→flash inversion (cf. DEV-005). Round-2 resolution: request the tier that empirically maps to glm-5.3 for ALL agents (reviewers included), pending a harness-side fix | Human, round-1 gate ("do it") |
| DEV-008 | 2026-10-27 | Stress-test round 2: §1 + inventory rows 90/91/92 prescribed @list_tools/@call_tool decorators that do not exist in the pinned mcp 2.3.0 (add_request_handler replaces instead); the implementer's chain-wrap shape was the only compliant route, marked TODO(port) in-code; amendment A-20 queued at the round-2 fixer | Human, round-2 gate |
