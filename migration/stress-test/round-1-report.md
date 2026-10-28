# Stress-test round 1 — gate report (2026-10-27)

Step 2, round 1 of the re-round loop. 7 agents (workflow `wf_ea7fac3e-904`),
67 min wall-clock, 684,226 subagent tokens. Nothing translated here ships —
only the rule changes below survive. Per the skill this report shows the
amendment queue and the adherence findings, not the translations; all three
workspaces are deleted (receipt below), the 7 structured agent returns are
preserved verbatim under `round1/`.

## Bakeoff verdict (translator A rulebook-faithful vs translator B native-baseline)

30 difference rows judged by the diff inspector (full verdicts:
`round1/diff-inspector.json`):

| verdict | count |
|---|---|
| rulebook right | 22 |
| both defensible | 7 |
| both wrong | 1 |
| native right | 0 |

Zero native-right is not reflexive rule-worship: B (which never saw the
rulebook) made **four judge-catchable behavior errors** a free-hand port
would have replicated across the whole fan-out —

1. FF-3 regression: unconditional `Authorization: Bearer ` header on an
   empty API key (websearch) — judge s16 asserts the header absent.
2. Invented sentinel: returns the string `"Content was not found"` where
   Go's `ContentWasNotFound` is `""` — wire-visible on every empty
   extraction.
3. Char-length instead of byte-length thresholds (drops non-ASCII content
   near minCodeLen/minInlineCode/minTextLen boundaries).
4. First-`<title>`-only emission where goquery concatenates ALL matches.

B's charset handling (bs4 `UnicodeDammit`) passes the judge fixtures only by
coinciding with the pinned x/net mirror on them — luck, not mechanism. The
one both-wrong row (reason-less status line rendering, `500 ` / `500 None`
vs Go's `500`) is latent and judge-unreachable → amendment A-14.

## Pilot run (production pipeline: implementer → 2 adversarial reviewers → fixer)

**Adherence answer:** at the SITE level, yes — unusually faithful; every
checked site traces to a named inventory row and the Go source (guard order
and byte-exact strings, FF-3 at both sites, URL-JOIN pinned matrix 14/14,
DEFER-CLOSE, NIL-ZERO/C-5 fallback wiring, omitempty body construction,
no ctx params, no relative/star imports, no unmarked suppressions, honest
§6 trailers). The failures were PROCESS-level (both reviewers, findings in
`round1/pilot-reviewer-{1,2}.json`):

- §1 runtime deps undeclared (`dependencies = []` in pyproject) and 8
  manifest sibling units absent → the batch was unimportable and the §0
  `make lint` referee could not have run, while trailers claimed
  confidence=high/medium → **DEV-006** queued.
- Two silent Go-semantics gaps the inventory never decides: encoding/json
  case-insensitive struct-field matching (`{"Text":"hi"}` decodes in Go) —
  reviewer probed and the fixer implemented fold-matching, 18/18 parity;
  `json.Decoder.Decode` first-value semantics (trailing garbage succeeds in
  Go, raises in Python) — fixer split per the two WIRE-DECODE rows →
  amendments A-4/A-6.
- Charset divergences on inputs row 49 under-worded: trailing-rune trim
  (Go cuts at the FIRST RuneStart, no completeness check — probed
  divergence on ASCII+trailing-`é`), regex-vs-tokenizer prescan (comments,
  RCDATA `<title>`, whitespace-before-`=`), unknown-label abort (Go
  continues scanning) → fixer implemented all three bug-for-bug; A-9 widens
  the row's TODO scope.
- One latent cross-row conflict adopted silently: Protocol `url` (row 60)
  vs concrete `target_url` (row 6) — mypy strict Protocol checks compare
  positional-or-keyword param NAMES → fixer made it loud (TODO(port)) and
  queued A-7 for the human to align the rows.

**Fixer:** 11 findings applied, 0 skipped as unconfirmed or contested (the
two reviewers agreed on every overlapping finding); 2 inventory-wording
defects routed to the amendment queue instead of code. Full report:
`round1/pilot-fixer.json`.

## Amendment queue (now the gate's work-list)

`migration/inventory/queued-rulebook-amendment.md` — 15 amendments + 3
deviations, all pending the human:

- Pre-existing from Step 1: **A-1** (§1 charset two-path rewrite),
  **A-2** (§2 `$`→`\Z` anchor fix), **A-3** (§4 test-scope httpx caveat),
  **DEV-005**.
- From the pilot fixer: **A-4** (§2 json struct-field matching row),
  **A-5** (row 75 wording), **A-6** (WIRE-DECODE first-value decision),
  **A-7** (row 60 vs row 6 param name), **A-8** (row 9 spelling),
  **A-9** (row 49 TODO scope), **DEV-006**.
- From the diff inspector: **A-10** (exception-class convention),
  **A-11** (row 61 entry point), **A-12** (row 50 no-body branch),
  **A-13** (Go-verbatim naming rule), **A-14** (reason-less status line),
  **A-15** (nil-impossible deref mechanism), **DEV-007**.
- Folded (not duplicated): inspector reinforcements of A-1/A-5/A-9 are
  cross-referenced inside the file.

Five of the inspector's nine entries came straight from translator A's
inline RULEBOOK-SILENT/TODO admissions — the flag-don't-invent instruction
worked end to end.

## Model plan deviation (needs a decision before fan-out)

All 7 agents were remapped by the workflow runtime (progress records):
requested **opus** ran as **glm-5.3-flash** (both reviewers + the diff
inspector); requested **sonnet** ran as **glm-5.3** (translators,
implementer, fixer). Second occurrence of the opus→flash inversion
(DEV-005 was the first) → escalated per standing rule 6 as **DEV-007**.
Findings quality was high throughout, but the Model plan's blast-radius
rationale (reviewers on the largest tier) inverts under this mapping — the
human should decide how to request the intended tiers (or sanction the
substitution) before Step 3.

## Workspace deletions — confirmed

```
rm -rf /tmp/claude/stress-round1/{stress-a,stress-b,stress-pilot}
ls /tmp/claude/stress-round1/  →  empty (total 0)
```

A's copy, B's scratch, and the pilot copy are gone; the repo itself was
never touched by any stress-test agent (all work happened under /tmp).

## Gate actions (the human's, in order)

1. Decide the model-tier question (DEV-005/DEV-007).
2. Apply the amendment queue A-1..A-15 to `migration/RULEBOOK.md` /
   `inventory.tsv`, and add DEV-005..007 to §7.
3. Make the repo's **initial git commit** (zero commits still breaks
   worktree isolation and queue-runner assumptions).
4. Declare the §1 runtime deps in the REAL repo (`mcp`, `httpx`,
   `beautifulsoup4`; pyproject still says `dependencies = []`) and run
   `uv sync` — otherwise every fan-out unit hits the same §0 referee
   failure the pilot hit (the lesson of DEV-006).
5. Commit `migration/` (stress-test report + queue included).
6. Re-paste the stress-test prompt for the **re-round**: fresh files
   weighted toward the amended sections — `github/grabber.go` +
   `grabber_test.go` (§2 regexp `$`→`\Z`, §4 test mapping) are the
   deferred picks — plus the pilot against the amended rules.

## Estimated duration — Step 3 (translation fan-out)

Manifest: 31 units. Pilot per-unit timings: implementer ≈ 6 min/file
(17.8 min / 3 files), reviewer pair ≈ 18–21.5 min per batch (parallel),
fixer ≈ 9 min/file (27.1 min / 3 files) → **~35 min per unit-chain**.
With workflow concurrency ≈ 10 and the topological order running in waves
(~5–7 effective layers for this graph):

- **Wall-clock: ~3–5 h** for the full 31-unit fan-out.
- **Active attention: ~30–45 min** (kickoff, burndown checks, end gate).
- Token band at pilot rates: ~3–5 M subagent tokens total.

## Cost log

Row appended to `migration/cost-log.tsv` (step 2, 67 min, 684,226 tokens,
7 subagents).
