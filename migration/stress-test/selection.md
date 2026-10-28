# Stress-test file selection (round 1) — 2026-10-27

Criterion (per the skill, not taste): score every manifest unit by
(a) inventory-row count and (b) coverage of the rulebook's riskiest
sections — weighted ×2 for rows touching sections the joint audit found
WRONG-as-written or amended (charset A-1/C-1/C-12, regexp anchors A-2/C-11,
FF-2 composed edge C-4, constructor spec C-2/C-3, FF-4, snippet raw-span,
decode). Then greedy by score with a distinct-section tie-break: a second
file exercising the same rules as the first buys nothing.

## Full scores (rows = inventory rows for the file; hot = rows touching audited/amended sections; score = rows + 2×hot)

| file | rows | hot | score | picked |
|---|---|---|---|---|
| internal/services/webfetch/cloud/service.go | 13 | 4 | 21 | **yes** |
| internal/services/websearch/cloud/service.go | 12 | 4 | 20 | **yes** |
| internal/services/webfetch/local/grabber/github/grabber_test.go | 10 | 3 | 16 | no (test mapping §4; re-round) |
| internal/tools/websearch/websearch.go | 7 | 4 | 15 | no (SDK boundary; fan-out) |
| internal/services/webfetch/local/postprocessor/html/postprocessor.go | 9 | 2 | 13 | **yes** |
| internal/services/webfetch/local/grabber/github/grabber.go | 5 | 3 | 11 | no (regexp A-2; re-round) |
| internal/services/websearch/cloud/service_test.go | 3 | 3 | 9 | no |
| internal/services/network/client.go | 3 | 2 | 7 | no (constructor spec is exercised via the cloud services' rows) |
| (9 further files, score ≤ 6) | | | | no |

## Why these three (distinct-section coverage)

1. **webfetch/cloud/service.go** (:29-127) — top scorer. Exercises: §2 pinned
   byte-exact error strings ("url must not be empty", "base_url must not be
   empty", "web fetch failed: {status}: {body}"), FF-3 conditional
   Authorization, format-default omitempty body, the JoinPath helper (never
   urljoin), decode zero-value semantics, DefaultClient fallback (C-5),
   defer/close recipe, call-by-value unobservability, nil-swallow interplay.
2. **postprocessor.go** (:29-173) — highest DISTINCT-section yield (+7 rule
   groups no other pick covers): §1 charset DetermineEncoding mirror (A-1 —
   the section the audit proved wrong as written), byte-length thresholds,
   bs4 selector translation, unescape-before-trim order, dedup, findMainContent
   priority + body-None fallback, error-swallow-to-"".
3. **websearch/cloud/service.go** (:28-138) — adds the gnarliest single
   function: snippetFromContent raw-span precedence chain (incl. the
   json.Unmarshal(null) no-op), plus results-decode raise (C-6), err-order
   (check-before-use), "search request failed: {status}".

Deliberately deferred: grabber_test.go + github/grabber.go (§4 test mapping,
§2 regexp `$`→`\Z`) — exactly the sections queued for amendment; the re-round
is explicitly weighted toward freshly amended sections, so they land there
with fresh files. (Re-running these three would only prove the patch.)

## Workspaces (all throwaway, deleted at round end)

- Translator A: `/tmp/claude/stress-round1/stress-a/` — full repo copy
  (rulebook + inventory + pyproject present). NOTE: the repo has ZERO
  commits, so the skill's "worktree on a branch that never merges" is
  impossible (`git worktree add` needs a HEAD); an unversioned full copy is
  the equivalent isolation. Initial commit queued as a gate action.
- Translator B: `/tmp/claude/stress-round1/stress-b/` — ONLY the three .go
  files above (442 lines total). Not a checkout; no rulebook on disk to find.
- Pilot: `/tmp/claude/stress-round1/stress-pilot/` — full repo copy,
  production pipeline (implementer → 2 reviewers → fixer).

## Round 2 (re-round) selection — 2026-10-27, after amendments A-1..A-15 + DEV-005/006/007

Fresh files, weighted toward the sections that just changed (re-running
round-1 files would only prove the patch):

1. `internal/services/webfetch/local/grabber/github/grabber.go` (105 ln) →
   `src/websearch/services/webfetch/local/grabber/github/grabber.py`
   — exercises amended §2 regexp (`$`→`\Z`, A-2: three routing regexes),
   §2 exception-class row (A-10), §2 nil-deref row (A-15: `*g.fallback` /
   `*g.client` zero-value), FF-4 UA literal, inventory rows for IsCanGrab
   userinfo-strip / Accept vnd.github.v3+json routing / fallback identity /
   5MB-cap scope (NOT on this path).
2. `internal/services/webfetch/local/grabber/github/grabber_test.go` (172 ln) →
   `grabber_test.py` — exercises amended §4 test-scope exception (A-3:
   MockTransport inline construction), §4 Go-verbatim naming (A-13),
   TEST-FIX-FF4 stale-UA correction, errors.Is→identity, Protocol-structural
   fake.
3. `internal/tools/websearch/websearch.go` (70 ln) →
   `src/websearch/tools/websearch/websearch.py`
   — exercises amended §4 naming (`input` param, noqa'd, A-13), §1 low-level
   SDK + asyncio.to_thread, FF-2a/FF-2b limit semantics, month-year baked at
   registration, byte-exact pinned strings incl. A-14 reason-less status
   line, results-never-None, hand-written schemas.

347 Go lines total. Deliberately NOT re-run: round-1 files (charset
postprocessor, webfetch tool, websearch cloud service) — round 1 already
proved the patch-surface; these three are where the NEW wording must hold.

Model resolution (DEV-007): ALL 7 agents requested on `sonnet` (the tier
that empirically executes as glm-5.3 in this runtime; requested `opus`
remaps to glm-5.3-flash). Reviewers and inspector included — the Model
plan's blast-radius intent (review on largest tier) is honored by the
empirical mapping, not the label.

Pilot delta vs round 1: implementer pre-authorized to create MINIMAL
sibling-stub modules (TODO(port)-flagged) for absent import targets —
round 1's DEV-006 showed missing siblings blocking the §0 referee; deps are
now declared in pyproject and the workspace .venv carries them.

Workspaces (throwaway, deleted at round end):
- A: `/tmp/claude/stress-round2/stress-a/` — full repo copy with the
  AMENDED rulebook + inventory (verified: "TWO scoped paths" present) and a
  working .venv (100 site-packages; httpx/bs4/mcp import verified).
- B: `/tmp/claude/stress-round2/stress-b/` — only the three .go files,
  renamed flat (github_grabber.go, github_grabber_test.go,
  tools_websearch.go). No rulebook on disk to find.
- Pilot: `/tmp/claude/stress-round2/stress-pilot/` — full repo copy,
  amended rules, complete .venv.

Run: workflow `wf_0e907e01-2d5` (script `stress-round2-wf_0e907e01-2d5.js`).
