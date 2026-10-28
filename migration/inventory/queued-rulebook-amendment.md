# Queued rulebook amendments — applied by the HUMAN, never by an agent

Per the standing rules: the rulebook is read-only inside loops; amendments
queue here and the human applies them at an amendment batch. Each entry
names the section it edits and the exact replacement text.

## APPLICATION LOG — 2026-10-27, all entries below APPLIED

The human delegated application to the orchestrator with "do it" at the
round-1 gate (delegation recorded here because the file's own rule says
agents never apply — the instruction overrides it for this batch only).
Applied: A-1..A-15 to `migration/RULEBOOK.md` + `migration/inventory.tsv`,
DEV-005/006/007 to §7. Judgment calls made while applying, all delegated:

- **A-6 vs A-11 reconciliation:** the fixer's A-6 (later, reflects the
  applied+probed F1.5 fix) wins for the websearch WIRE-DECODE row —
  `output.from_response(text: str)` owning a first-value scan. The
  inspector's A-11 spelled `from_response(data: dict)`; its essence (name
  the entry point) is subsumed into the same row edit.
- **A-7 resolution:** `url` everywhere (row 6 changed; row 60 already
  `url`). Go's interface (service.go:6), local twin (local/service.go:19),
  and complex twin all spell `url`; only the cloud concrete says
  `targetURL`. mypy strict Protocol compatibility forces one name; the
  majority Go-verbatim spelling wins. Row 10's guard variable follows.
- **Beyond A-9's letter (logged):** row 49's replacement also records the
  trailing-rune trim semantics (cut at FIRST RuneStart, no completeness
  check, charset.go:80-90) — the fixer implemented it (F2.3, 12/12 probe
  parity) but the queued A-9 text omitted the wording fix; leaving item (4)
  under-worded would invite the round-2 pilot to repeat the bug.
- **A-13 application:** added the naming bullet to §4 (not §2) — §4 is the
  naming section; includes the mypy-Protocol naming exception and the
  guard-style-out-of-scope sentence.


## A-1 — rewrite §1 "Charset decoding" row (from conflict C-1)

Replace the §1 Charset decoding row's Decision and Why with:

| Area | Decision | Why |
|---|---|---|
| Charset decoding | TWO scoped paths. **HTML extractor path** (`html.Handle`): mirror x/net `DetermineEncoding` on the raw body bytes (the declared `Content-Type` parameter NEVER reaches the decoder — `html.Handle` hardcodes `"text/html"`): first 1024 bytes → BOM table (x/net order) → meta prescan (`<meta charset>`, `<meta http-equiv>`; attribute-order-agnostic) → UTF-8-validity heuristic → **windows-1252 default**; decode with `errors="replace"`. **text/plain path** (choice processor): `data.decode("utf-8", errors="replace")` — NO charset detection of any kind (Go: `string(rawBytes)`; processor.go:26-31) | fixedGo's pinned cp1251 decode (judge s08, 354 bytes) comes from meta http-equiv sniffing, not the header param — `charset_1251.html` declares charset only in-document. The plain branch never sniffs: applying the html mechanism there would decode cp1251 bodies Go renders as mojibake. Evidence: `inventory.tsv` rows 1 and 44, `conflicts.md` C-1 + C-12 |

## A-2 — correct §2 "Go regexp" row anchor note (from conflict C-11)

The §2 regexp row's note currently asserts Go `^`/`$` behave like Python's
without `re.MULTILINE`. That is FALSE for `$`: Python's `$` also matches just
before a trailing newline (probed 2026-10-27 on both engines: the github repo
regex matches `"https://github.com/o/r/\n"` in Python and nils in Go; `\Z`
matches Go's end-of-text semantics exactly). Replace the anchor note with:

> Go `^`/`\Z` are string boundaries like Python's without `re.MULTILINE`.
> Go's `$` is end-of-text ONLY — Python's `$` also matches before a trailing
> `\n`, so translate Go `$` as Python `\Z` (or use `re.fullmatch`). Pattern
> text otherwise translates verbatim.

## A-3 — §4 httpx-construction home: add test-scope caveat (from conflict C-10b)

§4 says `services/network/client.py` is the ONLY place httpx clients are
constructed; five inventory test rows build `httpx.Client(transport=
httpx.MockTransport(…))` inline, so the letter of both cannot be satisfied.
Append to that §4 row:

> Exception: test-local clients over `httpx.MockTransport` may be constructed
> inline in `*_test.py` — the rule exists to centralize the §1 proxy rule for
> production egress, which a mock-transport client never exercises.

Note: §5's delegation to `migration/inventory.tsv` is already in the signed
rulebook — no amendment needed for it.

## DEV-005 (proposed) — reviewer model deviation, first inventory batch

The two skeptic reviewers of the first 20 inventory rows were requested on
`opus` (Model plan) but the workflow runtime executed both on
**glm-5.3-flash** (workflow progress records `model: glm-5.3-flash` for
both agents). Findings quality was high — 13/20 rows contested, every
finding citation- and probe-backed, all 13 accepted and applied — but per
the standing rules an untriggered/defaulted model is a process violation
and belongs in §7. Proposed §7 row:

| ID | Date | Deviation | Sanctioned by |
|---|---|---|---|
| DEV-005 | 2026-10-27 | Inventory skeptic reviewers ran on glm-5.3-flash instead of the planned opus (workflow model override not honored); findings accepted after per-finding source verification | pending human |

## A-4 — add §2 constructs-table row: encoding/json struct-field matching
(from fixer-round findings F1.4/F1.7)

The §2 constructs table has no row for Go struct-field decoding, so the
websearch `snippetFromContent` dict branch (service.go:113-119 unmarshals
the raw content into `struct{ Text string }`) had no sanctioned
translation. Verified against Go source
(encoding/json decode.go:699-703: `byExactName`, then `byFoldedName`) and
probed: keys match CASE-INSENSITIVELY, in document order, last
fold-matching key wins, and a non-string value for a string field fails
the whole decode. Add to the §2 table:

| Go construct | Python translation | Notes |
|---|---|---|
| `json.Unmarshal` into a struct (field-name matching) | iterate `dict.items()` in document order; match `key == "FieldName"` or `key.lower() == "fieldname"`; last match wins | encoding/json decode.go:699-703 folds case (byExactName → byFoldedName); a non-string value where Go's field is `string` fails Go's whole Unmarshal — mirror by treating that decode as failed, not by coercing |

## A-5 — rewrite row 75 (snippetFromContent) Decision wording (from
fixer-round findings F1.4/F1.7)

Row 75 currently spells the dict branch as `parsed.get("text")` with a
truthy test. That is Go-wrong twice: Go's struct decode matches the key
case-insensitively (`{"Text":"hi"}` decodes), and it requires a STRING —
`{"text": true}` errors the whole Unmarshal (falling through to the raw
echo), while Python truthiness would wrongly return `True`. Replace the
row's Decision with:

> dict branch: scan items in document order; a key equal to "text" under
> case-folding wins (last such key wins); return it iff it is a non-empty
> `str` — otherwise fall through. Never a truthiness test.

## A-6 — WIRE-DECODE rows (5, 62): record the json.Decoder first-value
decision (from fixer-round finding F1.5)

Both cloud services decode with `json.NewDecoder(resp.Body).Decode(&v)`,
which reads the FIRST JSON value and IGNORES trailing bytes
(encoding/json stream.go:46): a 200 body of `{"results":[]}garbage`
DECODES SUCCESSFULLY in Go, while `resp.json()`/`json.loads` raise
`Extra data` — a success/failure flip neither row contemplated. Both rows
waive only the error-message TEXT on malformed bodies. Append to both
rows:

> First-value semantics: Go's `json.Decoder.Decode` ignores bytes after
> the first JSON value (stream.go:46). Row 62 (websearch): implemented —
> `output.from_response(text: str)` owns a first-value scan. Row 5
> (webfetch): kept `from_response(data: dict)` + `resp.json()`; the flip
> is publicly unreachable (the complex service swallows every cloud error
> via local fallback) and carries a `TODO(port)`.

## A-7 — align IFACE row 60 vs CTX row 6 on the fetch parameter name
(from fixer-round finding F1.6)

Row 60 (WebFetchService IFACE) pins the Protocol as
`fetch(self, url: str, opts: FetchOpts)`; row 6 (cloud webfetch CTX) pins
the concrete method as `fetch(self, target_url: str, ...)` after Go
(`targetURL`, service.go:31). mypy strict Protocol compatibility requires
matching parameter NAMES, so both letters cannot hold at once. The fixer
round did not pick a side: the Protocol keeps row 60's `url`, the concrete
keeps row 6's `target_url`, and the file carries a `TODO(port)` pointing
here. The human must align the rows (one of the two names must change;
structurally-typed callers are unaffected either way).

## A-8 — correct row 9 (ERR-GUARD) condition spelling (from fixer-round
finding F1.8)

Row 9 spells the second guard `if self._base_url == ""`. The cloud
webfetch service stores its config whole (`self._cfg`, per the NIL-ZERO
row), so the condition as implemented reads `self._cfg.base_url` —
semantically identical (same field, same zero-value test), but the row's
letter names an attribute the port does not have. Replace the row's
condition text with: `if config.base_url == ""` (naming the stored
config's field, implementation-agnostic).

## A-9 — row 49 (html postprocessor): widen the TODO scope (from
fixer-round findings F2.4/F2.5)

Row 49's TODO list under-scopes the charset-prescan gaps the fixer round
closed. Three items verified against x/net source and now implemented
(charset.go, token.go:849/1042-1055):

1. A Lookup failure of a `<meta>` charset label does NOT abort the
   prescan (charset.go:194-209) — scanning continues to the next tag;
   the old port returned None.
2. The prescan must be tokenizer-shaped: markup declarations, comments,
   end tags, and the raw-text element set (script, style, textarea,
   title, iframe, noembed, noframes, noscript, xmp, plaintext — the
   plaintext start tag ENDS the prescan) change what is reachable.
3. Label equivalence is WHATWG, not `codecs`: `_lookup` returns the input
   label on success (NOT `codecs.lookup(label).name` — the canonical
   name would break downstream BOM-strip spellings like "utf-16le");

   still TODO(port): the utf-16-prefix label remap (charset.go:205-208)
   remains unimplemented (unreachable in fixtures); and the
   WHATWG-encoding label table is a superset of Python codecs aliases —
   a label valid only in WHATWG will raise `LookupError` where Go would
   decode.

Replace row 49's TODO text with the three-item list above (item 3
retaining its own remaining-TODO markers).

## DEV-006 (proposed) — §7 row: implementer round shipped units that
could not pass the §0 referee

The implementer round shipped 3 units under review
(webfetch/websearch cloud service.py) whose §0 referee
(`make lint typecheck`) could not have passed: the pyproject declared
`dependencies = []` (httpx import) and 8 sibling units the batch imports
were absent (webfetch/service.py, websearch/service.py, both
cloud/parameters.py, both cloud/output.py, network/client.py,
webfetch/local/postprocessor/postprocessor.py) — while §6 trailers
claimed confidence=high/medium and §7 carried no entry. The fixer round
declared the §1 deps (uv.lock regeneration deferred to the human —
builds are denied in-loop), created the sibling units plus URL-JOIN
matrix tests (rows 8/68), and applied the parity fixes; the referee
remains unrun in this sandbox (denied), so every touched trailer now
reads confidence=low pending a human referee run at the gate. Proposed
§7 row:

| ID | Date | Deviation | Sanctioned by |
|---|---|---|---|
| DEV-006 | 2026-10-27 | Implementer round shipped cloud service units with §1 deps undeclared and 8 imported sibling units absent, so the §0 referee could not run, while trailers claimed confidence=high/medium; fixer round declared deps, created the units + URL-JOIN tests, downgraded trailers to confidence=low pending the gate referee run; uv.lock regeneration deferred (builds denied in-loop) | pending human |

## Round-1 bakeoff additions (diff inspector, 2026-10-27)

Three inspector entries duplicate fixer entries and are FOLDED, not
repeated: inspector #1 reinforces A-1 (land it before fan-out — the bakeoff
showed a literal §1 reader emitting mojibake on the s08 cp1251 fixture);
inspector #3's "name the content record type" addition folds into A-5
(human may append: "the content record is the plain 3-tuple `(present,
parsed_value, raw_span)`"); inspector #5's label-aliasing question (WHATWG
maps iso-8859-1 → windows-1252; Python codecs yields true latin-1) folds
into A-9 item 3.

## A-10 — §2 error-model row: pin the exception-class convention

No row names the websearch typed-error class; both translators invented
one (A: `CloudWebSearchError(Exception)` with an inline RULEBOOK-SILENT
admission; B: `WebSearchError(RuntimeError)`). Unobservable to the judge
(message strings are compared, not classes) — exactly the
two-agents-answer-differently case. Add to §2's canonical mapping:

| Go construct | Python translation | Notes |
|---|---|---|
| `errors.New` surfaced through a pinned message string | module-level class named for the pinned message subject, deriving `Exception` | webfetch twin pinned by row 16 (`CloudWebFetchError(Exception)`); websearch twin: `CloudWebSearchError(Exception)` — add the name to inventory row 73 |

## A-11 — inventory row 61: name the websearch output entry point

Row 61 assigns the results-decode to output.py but names no function, while
the webfetch twin (row 5) names `from_response`. A had to assume the
twin-symmetric contract and flagged it RULEBOOK-SILENT. Append to row 61:
`output.from_response(data: dict)` is the module-level owner, raising per
C-6 (non-list non-null `results` raises; missing/null → []).

## A-12 — inventory row 50: pin the no-`<body>` branch

Row 50 pins the priority list and best-div scan but not the no-`<body>`
branch — unreachable in Go (x/net `html.Parse` always synthesizes `<body>`;
bs4+html.parser does not). Probed: on a body-less fragment with two
200+-byte divs, A (soup object as main-content) emits both divs while B
(whole-document root) narrows to one. Prescribe one stand-in (A's
soup-as-main-content carried a TODO(port); B chose silently) and mark the
branch Go-unreachable.

## A-13 — §2/§4: naming rule for Go-verbatim identifiers

A kept Go's `input` parameter with `noqa: A002`; B renamed to
`search_input`; no authority decides. Add: Go parameter/field names that
are legal Python stay VERBATIM (noqa'd when they shadow a builtin, e.g.
`search(self, input: Input)`); renames are not sanctioned. Optionally also
state that zero-guard style (`== ""` vs `not x`) is out of scope so
reviewers stop flagging it.

## A-14 — §2 pinned-strings row: reason-less status line

The round's single both-wrong row (latent, judge-unreachable): Go renders
`resp.Status` for a bare `HTTP/1.1 500` as `500` with no trailing space;
`f"{code} {reason_phrase}"` yields `500 ` (httpx, empty reason) or
`500 None` (requests). Prescribe `f"{code} {reason}".rstrip()` or an
explicit empty-reason fallback in the pinned error strings.

## A-15 — §2 canonical table: new row for nil-impossible deref sites

Rows 10/11/64 require a non-Optional client after `new()` but spell no
mechanism; A chose assert-as-deref-mirror (RULEBOOK-SILENT), B sidestepped
by defaulting `Config.http_client` to a constructed Session — silently
deleting Go's nil-zero Config state and the reason `New()` exists. Add:

| Go construct | Python translation | Notes |
|---|---|---|
| field deref that cannot be nil after `New()` (e.g. `*s.cfg.HTTPClient`) | keep the field `Optional` in the dataclass; mirror the deref with an adjacent `assert … is not None` + comment | NEVER default the Config field to a constructed client — that erases the nil-zero semantics rows 10/11/64 pin |

## DEV-007 (proposed) — §7 row: stress-test round 1 model overrides not honored (2nd occurrence)

Requested vs executed (workflow progress records): opus → glm-5.3-flash
for BOTH pilot reviewers AND the diff inspector; sonnet → glm-5.3 for both
translators, the pilot implementer, and the fixer. Same opus→flash
inversion as DEV-005 — second occurrence, so per standing rule 6 it moves
upstream: the tier mapping belongs to the workflow runtime, and the Model
plan's blast-radius rationale (reviewers/inspector on the LARGEST tier)
inverts under it. This needs the human's decision before the translation
fan-out, not a third retry. Proposed §7 row:

| ID | Date | Deviation | Sanctioned by |
|---|---|---|---|
| DEV-007 | 2026-10-27 | Stress-test round 1: all 7 workflow agents remapped by the runtime — requested opus ran as glm-5.3-flash (2 reviewers + diff inspector), requested sonnet as glm-5.3 (2 translators, implementer, fixer); 2nd occurrence of the opus→flash inversion (cf. DEV-005), escalated per standing rule 6 | pending human |

## ROUND-2 APPLICATION LOG — 2026-10-27, all round-2 entries below APPLIED

The human delegated application at the round-2 gate: "Make commit, i'm ok
with it. And make next turn" — read as approving the queue (including the
stop-early entries, which the gate report characterized as additive, not
re-litigations) and proceeding to Step 3. Applied: fixer A-16..A-20 +
DEV-008, inspector #1..#7 (with folds), to `RULEBOOK.md` +
`inventory.tsv` (rows cited below are FILE LINE numbers). Judgment calls,
all delegated:

- **Inspector #3 (chain-wrap vs dispatch table): CHAIN-WRAP pinned**
  (A-20.1 as queued). Structure-preserving: each tool unit keeps its
  Go-mirroring register() and composes on the shared Server, exactly as
  `mcp.AddTool` accumulates; a main.py dispatch table would move wiring
  INTO a redesign the rulebook's §0 posture forbids. The inspector's
  recommendation is recorded here; if the fan-out shows composition bugs,
  the table is the fallback amendment.
- **Webfetch twin rows (85/86) edited too** — A-20's own letter ("REQUIRE
  the webfetch tool twin to adopt it"); both carried the dead decorator
  spelling and the bare-raise envelope.
- **A-16 fold beyond the letter:** line 35's "%zz → empty netloc" phrase
  updated to "invalid escape" so the test row doesn't contradict the
  amended HTTP-REGEX row (same mechanism change the fixer's G2 made).
- **L91 evidence-column cross-reference** ("low-level @call_tool")
  updated to the new registration spelling — stale pointer, same fold.
- **Inspector #5 applied to §4 naming bullet** (not §2): extends A-13,
  which lives in §4; method names now covered by the case-split.
- Inspector #2/#3/#4 folded into the §1 MCP row + rows 90/91/92 rewrite
  (single coherent A-20 edit); #6 into A-16; #1 into the §2 pinned-strings
  list (6th string); #7 into rows 33/39.

## Round-2 additions (stress-pilot fixer, 2026-10-27)

From the round-2 adversarial review of github/grabber{,_test}.py and
tools/websearch/{websearch,input,output}.py. Every code-side fix is already
applied in the pilot tree; the entries below fix the rulebook/inventory
letters that were wrong or silent. No same-site reviewer disagreement
existed (the two reviewers covered disjoint files).

## A-16 — row 29 (HTTP-REGEX): urlsplit DOES raise; escape validation is
Go-verdict-relevant (reviewer findings G1/G2)

Row 29 claims `"%zz" needs no special case (urlsplit does not raise; empty
netloc → false ...)` and scopes its TODO to ASCII control chars only. Two
false/under-scoped claims, both verified against Go stdlib source
(GOROOT/src/net/url/url.go:114 EscapeError via setPath/setFragment/
parseAuthority; :557 "missing ']' in host" via parseHost):

1. `urlsplit("https://[github.com/o/r")` RAISES `ValueError('Invalid IPv6
   URL')` — Go's url.Parse errors ("missing ']' in host") and IsCanGrab
   returns false (grabber.go:34-37), so the crash diverges on an input the
   http(s):// prefix guard passes.
2. urlsplit never validates percent-escapes, so
   `is_can_grab("https://github.com/o/%2")` returned True while Go's
   setPath unescape rejects it — the port then fetched
   `api.github.com/repos/o/%2` where Go routes the ORIGINAL url to the
   fallback client grabber: a different URL fetched end-to-end.

Fixer implemented both verdicts in grabber.py (try/except ValueError →
False; escape-validity scan over exactly the regions Go unescapes —
before-first-`#` minus raw-query-after-first-`?`, plus the fragment —
Parse cuts `#` first, parse cuts `?`, the query stays raw), with a
TODO(port) pointing here. Replace the row's `"%zz" needs no special case
(urlsplit does not raise; ...)` clause and widen its TODO scope:

> urlsplit raises ValueError on bracket-unmatched netlocs — catch it and
> return False (Go: parseHost "missing ']' in host"). Go url.Parse also
> rejects invalid percent-escapes in userinfo/host/path/fragment (NOT the
> raw query) via unescape — mirror with a `%(?![0-9A-Fa-f]{2})` scan over
> those regions; "%zz" is now the escape-rejection case (empty netloc is
> no longer the mechanism). TODO(port) residual: ASCII control chars
> (urlsplit strips \t/\r/\n, Go rejects) remains unjudged.

Optional (human call): sanction extra parametrize rows
(`https://github.com/o/%2` -> False, `https://[github.com/o/r` -> False,
`https://github.com/o/r/issues/١٢٣` fallback) — row 35 currently pins the
five Go rows verbatim, so the fixer added none.

## A-17 — §2 RE2 row: char-class semantics are NOT verbatim (reviewer
finding G3)

The row pins "pattern text translated verbatim except Go `$` → Python
`\Z`" and asserts "All in-repo patterns are RE2-safe" — true of the
pattern TEXT, silent on char-class SEMANTICS: Go `\d` is exactly `[0-9]`
(regexp/syntax/perl_groups.go: code1 = {0x30, 0x39}), Python `\d` for str
patterns matches any Unicode Nd digit (probed: the github issue regex
matches `issues/١٢٣` without the flag; Go nils and falls back to the
client grabber — a different URL fetched). Fixer applied `re.ASCII` to
`_GITHUB_ISSUE_RE` (the only `\d`/`\w`/`\s` class among the three
patterns). Append to the §2 regexp row's note:

> Go `\d`/`\w`/`\s`/`\b` are ASCII-only classes (regexp/syntax/
> perl_groups.go); Python's are Unicode for str patterns — compile any
> pattern using them with `re.ASCII` (a no-op when the pattern contains
> none, so applying it selectively per pattern is fine).

## A-18 — row 36 (TEST-FILE): drop ContentGrabber from the spelled import
list (reviewer finding G4, cosmetic)

Row 36 spells `from websearch.services.webfetch.local.grabber.grabber
import ContentGrabber` among the test file's imports, but the port never
uses the name (duck-typed fakes are checked structurally at the
`fallback=` argument) and importing it would trip ruff F401. The file
documents the omission in its docstring. Remove ContentGrabber from the
row's spelled list so the row and the file stop disagreeing.

## A-19 — rows 35/37 vs 41: is_cangrab/is_can_grab spelling conflict
(reviewer finding G5, ambiguity)

Row 37 (TEST-FAKE) literally spells the mock method `def is_cangrab(...)`
and row 35 names the test `test_is_cangrab`, while row 41 (IFACE) spells
the Protocol method `is_can_grab` — and row 37 ITSELF requires the mock
to "structurally satisfy the port's ContentGrabber Protocol ... so mypy
strict accepts it as the fallback= argument", which forces `is_can_grab`
(Protocol compatibility compares method names; §4's mypy naming note).
Rows 35/37 must be amended to `is_can_grab` (keep the Go test-function
name `test_is_cangrab` if desired — it names the Go test, not a Protocol
method). The pilot file already follows row 41; no code change.

## A-20 — §1 MCP server row + rows 90/91/92: the decorator prescription is
unsatisfiable under the pinned SDK; envelope + null-arg scope (reviewer
findings W1/W4/W5)

Three coupled defects, all verified against the pinned mcp 2.3.0 (uv.lock)
and go-sdk v1.7.0 (module cache):

1. §1 mandates "LOW-LEVEL Server with @list_tools/@call_tool handlers"
   and rows 90/91/92 prescribe "low-level Server @call_tool handler" —
   mcp 2.3.0 HAS no such decorators (probed: no Server.list_tools/
   call_tool attrs) and `add_request_handler` REPLACES any prior handler
   for a method. The only §1-compliant shape is chain-wrapping the
   previously-registered handler (as the pilot's websearch.py does, with
   a TODO(port)); the sanctioned alternatives (FastMCP, auto-schema) are
   banned. Amend §1 + rows 90/91/92 to prescribe the chain-wrap
   registration shape, and REQUIRE the webfetch tool twin to adopt it
   (per-tool registration must compose on one server).
2. Row 91's "the port returns just the dict" envelope claim was written
   for a decorator-SDK envelope. Under the hand-built envelope the wire
   must mirror Go's: go-sdk server.go:427-437 FILLS Content with a
   serialized-JSON TextContent block when the handler returned nil
   Content with non-nil output (websearch.go:27 returns exactly that) —
   every pinned success capture has content_blocks ["text"] (s02/s16/
   s18) and the judge compares block types (README norm_call; harness.py
   strict equality). The Python SDK adds no fallback (probed). The pilot
   now appends `TextContent(json.dumps(output))` alongside
   structuredContent; the serialization itself is non-spec (norm_call
   drops it when structuredContent exists). Amend row 91's wire-contract
   clause accordingly.
3. Rows 90/91 are silent on null-valued KNOWN arguments: Go's SDK
   unmarshals arguments via encoding/json (server.go:368-376
   internaljson.Unmarshal) where null into a string/int field is a NO-OP
   ({"limit": null} → 0 → 50; {"query": null} → "" → "query must not be
   empty"), while the raw-dict port saw None and flipped success into a
   TypeError isError result. The pilot now coerces None → zero value
   with a TODO(port); amend row 90 to record the decision.

## DEV-008 (proposed) — §7 row: round-2 rulebook prescribed an SDK
mechanism that does not exist

§1 and inventory rows 90/91/92 prescribed `@list_tools`/`@call_tool`
decorators on `mcp.server.Server`; the pinned mcp 2.3.0 has no such API
(probed in-round), so the letter was unsatisfiable while the sanctioned
alternatives were banned. The implementer chose the chain-wrap
registration route and marked it TODO(port) in-code; the fixer verified
the probe, queued A-20, and left the TODO in place — but per §7 "a
deviation nobody logged is a deviation nobody approved" the prescription
failure itself needs a log entry. Proposed §7 row:

| ID | Date | Deviation | Sanctioned by |
|---|---|---|---|
| DEV-008 | 2026-10-27 | Stress-test round 2: §1 + inventory rows 90/91/92 prescribed @list_tools/@call_tool decorators that do not exist in the pinned mcp 2.3.0 (add_request_handler replaces instead); the implementer's chain-wrap shape was the only compliant route, marked TODO(port) in-code; amendment A-20 queued at the round-2 fixer | pending human |


## Round-2 additions (diff inspector, 2026-10-27) — verbatim from its return value
Seven entries; entries #1, #5, #6, #7 (and #2/#3 as §1) touch sections/rows
amended in round 1 — the stop-early signal the round was watching for.
Folds vs the fixer block above: inspector #2/#3/#4 overlap A-20 (same probe
evidence); inspector #6 overlaps A-16 (same ValueError/escape findings);
inspector #5 EXTENDS A-13 rather than conflicting with it.

### Inspector entry #1

**Section:** RULEBOOK §2, error-model row pinned-strings list (2nd touch of a round-1-amended row — A-10/A-14 amended this row in round 1: STOP SIGNAL for the human)

**Change:** Add `request failed with status {code}` to the pinned byte-exact string list; it is the only app error string the judge pins that the list omits.

**Evidence:** grabber.go:86 produces it; judge APP_ERROR_RE (migration/judge/harness.py:149-151) includes 'request failed with status' as an exact-compare app prefix; §2's list has 5 strings, none of them this one — A had to cite inventory rows 27/29/31 instead of the rulebook for a string the rulebook claims to enumerate completely.

### Inspector entry #2

**Section:** RULEBOOK §1, MCP server row (2nd touch of §1 — round 1 A-1 amended §1's charset row; different row, same section: say so explicitly)

**Change:** Replace '@list_tools/@call_tool handlers' with the pinned SDK's actual registration API: constructor kwargs on_list_tools/on_call_tool or Server.add_request_handler('tools/list'|'tools/call', params_type, handler). The decorator API named in the row does not exist in mcp 2.3.0.

**Evidence:** Probed against the repo venv (mcp 2.3.0): hasattr(Server,'list_tools') and hasattr(Server,'call_tool') are both False; mcp/server/lowlevel/server.py:308-360 shows on_* constructor kwargs and add_request_handler (line 484) as the registration surface. An implementer following §1 verbatim hunts for a nonexistent API — B bailed to the banned MCPServer layer partly on this.

### Inspector entry #3

**Section:** RULEBOOK §1 MCP row + inventory rows 90/91 — multi-tool handler composition (again §1: bundle with the previous entry's flag)

**Change:** Decide how TWO register() calls share the low-level Server's single tools/list + tools/call slot: either main.py owns one dispatch table (recommended — composition lives at the wiring site, not inside each tool unit) or the rulebook pins A's compose-with-previous-handler convention as mandatory for every tool unit.

**Evidence:** add_request_handler REPLACES any existing handler for the same method (probed: docstring 'Replaces any existing handler for the same method', lowlevel/server.py:484-507), so register_web_search then register_web_fetch silently drops the first tool; Go's mcp.AddTool accumulates. A marked it RULEBOOK-SILENT and composed with previous handlers; nothing obliges the webfetch twin to compose identically — order-dependent clobbering is one uncoordinated unit away.

### Inspector entry #4

**Section:** Inventory row 91 (NIL-SDK, tools/websearch Register handler closure) — promote the contingency to the decision

**Change:** Rewrite row 91's primary: on the sanctioned low-level Server the call_tool handler MUST catch the app exception and build CallToolResult(is_error=True, content=[TextContent(text=str(exc))]) itself; a bare raise is WRONG (it becomes a JSON-RPC error response, never the isError tool-result text the judge compares).

**Evidence:** mcp 2.3.0 source: jsonrpc_dispatcher.py:771-782 — a raising request handler produces ErrorData/JSONRPCError, never an isError CallToolResult; and on the banned MCPServer layer a non-ToolError crash is decorated to 'Error executing tool <name>' with 'nothing from the original' reaching the client (mcpserver/exceptions.py:61-71). Row 91's primary (bare raise) and its MCPServer assumption both fail; A already shipped the corrected form with a probe note and TODO(port).

### Inspector entry #5

**Section:** RULEBOOK §4 naming rule (2nd touch of §4 naming — round-1 A-13 created it: STOP SIGNAL for the human)

**Change:** Extend A-13 with the case-split it lacks: single-identifier Go names stay verbatim (input, search); MULTI-WORD Go identifiers snake_case mechanically (IsCanGrab → is_cangrab, getMonthYear → get_month_year, webSearchService → web_search_service). As written ('names that are legal Python stay VERBATIM') the rule mandates camelCase webSearchService — no translator obeys that, and method names are entirely uncovered.

**Evidence:** B chose can_grab and month_year free of any rule; only inventory row 41 pins is_cangrab, for one file. BOTH translators snake_cased the webSearchService parameter this round despite the round-1 verbatim rule — the rule and observed practice already disagree.

### Inspector entry #6

**Section:** Inventory row 29 (github/grabber.go IsCanGrab host check) — add the ValueError guard (2nd touch of the round-1-amended github-grabber rows: the row was rewritten in round 1 for \Z; say so explicitly)

**Change:** Amend the pinned host-check form to wrap urlsplit in try/except ValueError → return False: Go's url.Parse ERROR path maps to False, and urlsplit RAISES ValueError('Invalid IPv6 URL') on malformed bracket hosts — the row's current form crashes where Go returns false.

**Evidence:** Probed: urlsplit('https://[::1/o/r') raises ValueError; Go url.Parse errors on the same input ('missing ] in host') → IsCanGrab returns false; the URL passes the tool's HasPrefix guard (webfetch.go:39-41), so the crash is reachable. A's port (row-faithful) propagates the exception; B's try/except is the correct mirror.

### Inspector entry #7

**Section:** Inventory rows 33 + 39 (TestGrabRoutesGithubURLs Accept assertion; roundTripFunc caveat) — correct the httpx header-merge rationale (2nd touch of the round-1-amended test rows: the MockTransport mapping was spelled there in round 1)

**Change:** Scope the 'httpx merges the client default accept */* into the request' caveat to client.get()/build_request() only: a bare httpx.Request sent via client.send() receives NO default headers, so the Go assertion Header.Get('Accept') == '' IS expressible in a send()-based port as request.headers.get('accept') is None. The prescribed assertion form (≠ vnd.github) still passes either way; only the rationale is false for A's construction.

**Evidence:** Probed with httpx 0.28.1 MockTransport: request built as httpx.Request(...)+client.send() arrives at the transport with accept = None; client.get() arrives with accept = '*/*'. A's own grabber_test comment (lines 112-115) repeats the wrong rationale about its own send()-based port; the wire-faithful consequence (no Accept header on the file route, exactly like Go) is currently undocumented anywhere.

## A-21 (queued 2026-10-28T14:17Z, Step-6 judge finding; in-code fix applied at gate)

Rule: any ported request whose Go twin sets NO User-Agent must carry the explicit header "User-Agent: Go-http-client/1.1" — Go net/http stamps this default at write time (net/http Request.write defaultUserAgent); httpx bare requests (httpx.Request + client.send) receive NO client defaults, so the default must be ported explicitly at each such site. Sites: websearch/cloud/service.py make_request (Go service.go:75-93), webfetch/cloud/service.py make_request (Go service.go:82-101). Gap: no prior row covered the implicit default; judge s02/s03 first-pass divergences (parity-2026-10-28.json pre-fix run) exposed it. Found by: Step-6 parity judge; applied in-code by orchestrator; rulebook wording is the human's to apply (suggest §1 httpx row or §2).

## A-22 (queued 2026-10-28T15:20Z, Step-7 post-parity burndown + adversarial review findings 1/5/7)

Four items; wording is the human's to apply.

**(a) Recurring document-and-close patterns — three classes each closed with
near-identical wording in 2 files; per the post-parity skill this recurrence is
a rulebook indictment, so each deserves one canonical row instead of two
scattered per-file judgments:**

1. U+FFFD granularity (Go string(bytes) substitutes per invalid BYTE; Python
   errors="replace" substitutes per maximal bad SUBSEQUENCE) — sites:
   webfetch/cloud/service.py (error-body decode), postprocessor/choice/processor.py
   (plain-text branch). Diverges only on invalid-UTF-8 input; no fixture has any.
2. url.Parse-vs-urlsplit strictness on env-supplied base URLs (Go rejects control
   chars / invalid %-escapes, urlsplit accepts; error class transport-normalized
   either way) — sites: webfetch/cloud/service.py _join_url_path (row 8),
   websearch/cloud/service.py _join_url_path (row 68). Judge never sets a base.
3. Lenient-decode edges (Go encoding/json fails the WHOLE decode on a mistyped
   field / non-object body / trailing bytes; the ports' .get-based parse accepts)
   — sites: webfetch/cloud/output.py (row 5 + A-6), websearch/cloud/output.py
   (row 62). Fixtures only send well-formed bodies.

**(b) F1b redirect accounting (review finding 1):** Go defaultCheckRedirect errors
once 10 requests exist → exactly 10 requests on an infinite chain; httpx raises
only when len(history) > max_redirects → the byte-exact pin is max_redirects=9,
NOT 10 (probed both engines, 2026-10-28). Candidate §1 httpx-construction row so
the next port doesn't re-derive it.

**(c) Stale rulebook cross-references:** §0 kept-quirks table and §3 cite marker
sites that Step 7 retired (e.g. local/service.py "BUG(port): Go byte semantics",
github/grabber.py unbounded-read BUG). The behaviors are unchanged and now
documented inline as closed quirks; the rulebook's marker-site citations need a
post-burndown sweep (human's edit).

**(d) Typed-exception asymmetry (review finding 7, observation):** github
grabber's pinned "request failed with status {code}" now raises RequestFailedError
(§2 row 91 convention) while the client grabber's pinned "HTTP %d: %s" still
raises bare ValueError — same construct, two conventions. Extending the typed
class to the client grabber would be a NEW behavior-adjacent change beyond
Step-7's classified markers, so it was NOT applied; human decides (a one-class
change + parity re-run if wanted).
