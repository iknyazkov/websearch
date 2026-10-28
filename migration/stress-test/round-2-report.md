# Stress-test round 2 (re-round) — gate report

2026-10-27. Run `wf_0e907e01-2d5` (script `stress-round2-wf_0e907e01-2d5.js`),
7/7 agents completed, 725,117 tokens, 456 tool calls, ~46 min wall.
Agent returns verbatim: `migration/stress-test/round2/*.json`.

Files: `github/grabber.go` + `grabber_test.go` + `tools/websearch/websearch.go`
(347 Go lines) — fresh files weighted toward the round-1 amendments (§2 `\Z`,
§2 error-model rows, §4 test scope + naming, FF-4 UA). Selection rationale and
scores: `selection.md` §"Round 2".

**Model resolution (DEV-007):** all 7 agents requested `sonnet`, all 7 executed
on **glm-5.3** (workflow progress confirms per-agent). Zero model deviation —
the round-1 inversion is resolved by the empirical mapping, pending the
harness-side fix.

## Bakeoff verdicts — 27 rows

| Verdict | Round 2 | Round 1 |
|---|---|---|
| rulebook right | 23 | 22 |
| native right | **1** | 0 |
| both defensible | 3 | 7 |
| both wrong | 0 | 1 |

The lopsided rulebook win is expected, not suspicious: B is a native baseline,
and this round's files are exactly where the amendments concentrated — B
re-introduced two sanctioned fixes as bugs (FF-2 hardcoded limit, FF-4
unpinned UA), used the **banned MCPServer+pydantic layer**, invented the tool
name/description, and diverged from Go on regex anchors (trailing-newline URLs
route to the API), host-case/port matching, 2xx handling, and byte-exact error
strings. Each of those wins indicts nothing.

**The one native-right row:** `urlsplit` raises `ValueError('Invalid IPv6
URL')` on bracket-unmatched netlocs where Go's `url.Parse` errors and
`IsCanGrab` returns `false` — the row-29-faithful port CRASHES on a reachable
input (`https://[github.com/o/r` passes the tool's prefix guard). Folded into
A-16 (inspector #6).

**Both-defensible (3):** multi-tool handler composition, structured/text
content-block shape, `month_year` naming — all three are actually the SAME
root cause: the pinned mcp 2.3.0 API differs from what §1/rows 90-92 were
written against (see below).

## The round's big finding — §1 prescribed an SDK API that does not exist

Four independent contexts converged: translator-A (RULEBOOK-SILENT flag),
reviewer-2 (finding W5), the fixer (A-20), the inspector (entries #2/#3/#4).
`mcp.server.Server` in pinned mcp 2.3.0 has **no `@list_tools`/`@call_tool`
decorators** (probed: `hasattr` false); registration is
`add_request_handler(...)`, which **REPLACES** any prior handler for a method
— Go's `mcp.AddTool` accumulates. Consequences queued:

- **A-20.1** — §1 + rows 90/91/92 must prescribe the chain-wrap registration
  shape (or a main.py dispatch table — inspector #3 recommends the table);
  the webfetch tool twin must adopt the same shape or silently clobbers
  websearch's registration.
- **A-20.2 / inspector #4** — row 91's "bare raise" primary is WRONG on this
  SDK: a raising low-level handler becomes a JSON-RPC error response, never
  the `isError` tool result the judge compares; and go-sdk FILLS Content with
  a serialized-JSON TextContent block on success (every pinned capture shows
  `content_blocks ["text"]`) — the port must hand-build both. Reviewer-2's W1
  (the one real parity breaker in the batch) and the fixer's applied fix
  implement exactly this.
- **A-20.3** — null-valued KNOWN arguments (`{"limit": null}`) are a no-op in
  Go's encoding/json but flipped success→TypeError in the port; fixer applied
  None→zero-value coercion, row 90 records the decision.
- **DEV-008** — §7 entry for the unsatisfiable prescription itself.

## Pilot adherence

Implementer followed the rulebook to high fidelity on every judge-pinned
surface (reviewer-2 verified byte-level: TEMPLATE, both schemas, FF-2b limit,
month-year-once, byte-exact error strings, results-never-None). Deviations:
5 findings (2 silent, 3 documented only in-code) — W1 envelope, W2 bare `dict`
annotations failing mypy strict while trailers claimed confidence=high (the
DEV-006 failure mode recurring in miniature), W3 unknown-tool code+message
divergent from the readable go-sdk source, W4 the null-arg gap, W5 the §1
prescription. Reviewer-1's batch: G1 the ValueError crash, G2 invalid
percent-escapes flipping the grab/fallback verdict (`https://github.com/o/%2`
was FETCHED where Go routes it to fallback — different URL end-to-end), G3
Unicode `\d` in the issue regex (Go `\d` is `[0-9]` exactly; Python matches
`issues/١٢٣` — fixed with `re.ASCII`, A-17 queued), G4/G5 row inconsistencies.

**Fixer: 11/11 findings confirmed and applied, 0 skipped, 0 contested** (the
reviewers covered disjoint files). Every citation verified against Go source,
go-sdk v1.7.0 (module cache), Go 1.27.1 stdlib, inventory rows, and probes
through the real SDK boundary. Trailers match marker counts post-fix.

Sibling-stub pre-authorization worked as intended: round 1's DEV-006 pattern
(missing siblings) reduced to stubs the fixer could actually check. Residuals
for the human:

1. `make lint` remains unrunnable in-loop (mypy denied by design) — the gate
   referee run still applies.
2. Two PRE-EXISTING ruff conflicts, unflagged by reviewers: BLE001 on the
   row-91-prescribed broad except, and RUF100 on §4's prescribed `# noqa:
   A002` (pyproject doesn't enable flake8-builtins A-rules). One amendment
   line each, or enable A002 in pyproject — human's call.
3. A's units import sibling modules absent from both bakeoff workspaces —
   expected (they're other manifest units), noted by the inspector as the
   DEV-006 pattern recurring; trailers' confidence=high is unverifiable
   in-workspace by design.

## Amendment queue — round 2 adds 13 entries (NOT applied)

Per the standing rules these are the human's to apply — the round-1 "do it"
delegation covered that batch only. Queued in
`migration/inventory/queued-rulebook-amendment.md`:

**Fixer:** A-16 (row 29: urlsplit raises + escape-validation scope), A-17 (§2
regexp row: `re.ASCII` for `\d`/`\w`/`\s` classes), A-18 (row 36: drop
unused ContentGrabber import from spelled list), A-19 (rows 35/37: align
`is_can_grab` to row 41), A-20 (§1 + rows 90/91/92: chain-wrap registration,
envelope TextContent, null-known-arg decision), DEV-008 (§7).

**Inspector:** 7 entries (verbatim in queue + `round2/diff-inspector.json`).

### STOP-EARLY SIGNAL — sections re-amended

Five of seven inspector entries touch sections/rows amended in **round 1**:

| Entry | Section | Round-1 touch |
|---|---|---|
| #1 | §2 error-model pinned-strings list | A-10/A-14 amended this row |
| #2, #3 | §1 MCP server row | A-1 amended §1 (different row, same section) |
| #5 | §4 naming rule | A-13 CREATED it |
| #6 | row 29 (github grabber) | rewritten in round 1 for `\Z` |
| #7 | rows 33/39 (test rows) | MockTransport mapping spelled in round 1 |

Per the skill's stop-early rule this needs a **human decision, not a third
wording**. Read on the entries: none re-litigates round-1 wording — they are
additive (a 6th pinned string; a case-split A-13 lacked) or newly-probed
facts the round-1 amendments couldn't have known (the mcp 2.3.0 pin, the
urlsplit/Godivergence probes, the httpx header-merge scope). The signal is
that §1/§2/§4 are still the churn surface — the SDK-surface entries (#2/#3/#4
+ A-20) are the root cause, and landing them should quiet the section.

## Round-over-round delta

| Measure | Round 1 | Round 2 |
|---|---|---|
| Inspector rows | 30 | 27 |
| native-right rows | 0 | 1 |
| both-wrong rows | 1 | 0 |
| B judge-catchable errors | 4 | ~8 (incl. 2 FF regressions, banned SDK layer) |
| Pilot findings applied/skipped | 11/0 | 11/0 |
| Pilot process failures | DEV-006 (deps + 8 siblings) | none new (2 ruff config residuals) |
| Model deviations | DEV-007 (opus→flash ×3) | **zero** |
| Queued entries | 15 amendments + DEV-006/007 | 6 amendments + DEV-008 (fixer) + 7 (inspector) |
| New rule-level bugs found | — | §1 SDK prescription unsatisfiable (biggest of both rounds) |

## Deletion receipts

`rm -rf` on all three workspaces; `ls` confirms:
`/tmp/claude/stress-round2/{stress-a,stress-b,stress-pilot}` → "No such file
or directory"; the round2 root itself removed (only a stray `.ruff_cache`
remained, also removed). Nothing translated in round 2 ships.

## Gate actions (human)

1. **Apply or delegate** the round-2 queue: A-16..A-20, inspector #1..#7
   (folds noted in the queue file), DEV-008 to §7. Decide the stop-early
   entries on their merits — they are additive, not re-litigations.
2. Decide inspector #3's shape question: per-tool chain-wrap (A-20.1 as
   queued) vs main.py dispatch table (inspector's recommendation).
3. Rule on the two ruff config conflicts (BLE001 / RUF100-A002).
4. **Initial git commit** — still pending since round 1; worktree isolation
   for the fan-out assumes it.
5. Optional per A-16: sanction extra parametrize rows for the new
   escape/bracket/Unicode-digit behaviors (row 35 currently pins the five Go
   rows verbatim).
6. Sign off → Step 3 translation fan-out (31 manifest units) via
   `queue_runner.mjs`.

## Next-step estimate (translation fan-out, 31 units)

Per-unit cost from this round's pipeline: ~45k implementer + ~60k review +
~42k fix ≈ 150k tokens/unit → **~4.5–6M tokens** total. Wall-clock at
pipeline parallelism ~8: **~4–7 h**; active human attention: **~45–60 min**
(gates + referee runs). Assumes A-20 lands first — the SDK registration shape
is load-bearing for both tool units and main.py wiring.
