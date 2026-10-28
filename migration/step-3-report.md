# Step 3 — translation fan-out gate report

2026-10-28. Runs: `wf_4c721b38-bb9` (full topology, killed mid-L1 by human
trim) + `wf_41cbd335-5a1` (implementer-only finish, 9/9 agents, 614,424 tok
final attempt + 188,809 tok rate-limited first attempt).

**Burndown: 31/31 manifest units translated** — every target file on disk with
an honest §6 trailer. Whole-tree referee **PASS**: `ruff check .` +
`mypy . --strict` green on 50 source files (receipt in gate transcript).
LOC: 1762 Go → 4144 Python (rulebook §2/§4 citation comments and docstrings
account for the ratio; ~1.35× code-only would be typical, the rest is the
mandated inline citation style).

## Topology change (human directive, 2026-10-28)

User trim mid-step: "implementers only" for the remaining 9 units —
reviewer/arbiter/fixer stages dropped after 22 units had completed the full
4-agent pipeline. Recorded here as the standing decision; not a deviation
(rulebook topology was signed off at feasibility, the human owns changes to
it). Savings: ~30–40 agents → 9; ~1.3–1.5M → 0.80M tokens.

## What the full topology bought (22 units, killed run journal)

- 60 reviewer results (30 units × 2), **32 findings**, 35/60 reviews clean
  (the zero-finding reviews are concentrated in DTO/constant units — the
  overhead the trim removes)
- 32 fixer cycles: **20 applied / 26 skipped**, every finding dispositioned
- **No orphaned findings**: forensics confirm no unit had reviewer findings
  without a completed fixer (`jobs/d7f7407a/tmp/forensics.py`)

## The 9 impl-only units (residual risk list)

`html/postprocessor.py`, `tools/webfetch/webfetch.py`, `tools/websearch/websearch.py`,
`grabber/github/grabber.py`, `postprocessor/choice/processor.py`,
`websearch/cloud/service_test.py`, `grabber/github/grabber_test.py`,
`webfetch/local/service.py`, `main.py` — translated + file-scoped referee
each, **no adversarial pass**. Mitigations that did fire: file referee
(caught the broken `html/postprocessor.py` partial: F821 `html_unescape` +
dead placeholder line 300 — re-run overwrote it), whole-tree referee at this
gate (2 fixes, below), Step-5 smoke, and the 18-scenario judge in Step 6.

## Gate fixes (orchestrator, both verified by whole-tree referee)

1. `services/webfetch/cloud/service.py`: added missing
   `from dataclasses import dataclass` (2× name-defined + 1 call-arg; the
   defect that made `main.py`'s implementer report referee_passed=false —
   diagnosed by that agent with proof, correctly not touched by it).
2. Same file: `# noqa: A001` comments were one line off (RUF100 + A001 pair);
   moved to the rebind at the `format = "markdown"` line.

## Runtime smoke (by the `main.py` implementer, real stdio subprocess)

`initialize` → serverInfo `{"name": "websearch", "version": "v1.0.0"}` (s01
pin, byte-exact); `tools/list` → `['WebSearch', 'WebFetch']` in registration
order — **A-20 chain-wrap registration confirmed working on the real SDK
boundary**; clean exit 0 on stdin EOF.

## Marker census (post-parity Step 7 sweep list)

TODO(port) 24 · PERF(port) 1 · BUG(port) 3 (one is the sanctioned unbounded
read in `grabber.py` row 27) — trailers: 30 high, 1 medium (`websearch.py`).

## Next-step estimate (Steps 5–6; Step 4 dissolved into 3 by the in-loop referee)

- **Step 5** (hello-world + smoke): `main.py` already smoke-tested through
  real stdio; remaining is the packaged entry point + judge-harness smoke vs
  the new server. ~30–60 min wall, ~15 min active attention, ≤0.3M tokens.
- **Step 6** (judge parity, 18 scenarios): runs are cheap, divergence-fixing
  is the variable — est. 1–4 h wall, ~1 h active attention, 0.5–2M tokens.
  Note: `make` stays deny-ruled; judge executes via direct harness
  invocation or handed to the human at gates.

## Gate asks (human)

1. Sign off Step 3 → Step 5 starts.
2. Initial commit still pending (zero commits on master) — suggested:
   `git add -A && git commit -m "Step 3: full Go->Python translation, 31/31 units, referee green"`.
