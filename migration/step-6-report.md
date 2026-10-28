# Steps 5–6 — smoke + judge parity gate report

2026-10-28T14:17Z. All runs direct (no subagents).

## Step 5 — smoke

- **Packaged entry**: `migration/judge/bin/websearch-py` wrapper (venv python,
  `-m websearch.main`), spawned exactly as the judge spawns it. Handshake +
  `tools/list` through real stdio: serverInfo `{"name": "websearch",
  "version": "v1.0.0"}` byte-exact, tools `['WebSearch', 'WebFetch']`,
  clean exit 0 on EOF. SMOKE PASS.
- **Translated unit tests**: `pytest src -q` → **14 passed** in 0.07 s
  (github grabber routing/fallback + websearch cloud decode suites).

## Step 6 — parity judge (the exit condition)

`run.py --old bin/websearch-go --new bin/websearch-py`, full report:
`migration/judge/parity-2026-10-28.json`.

**First pass: 4/18.** Every failure was ONE divergence class: Go's net/http
implicit default `User-Agent: Go-http-client/1.1` on requests that set no UA
vs the port's bare `httpx.Request` (no defaults reach a bare request — the
same httpx merge semantics round 2 probed). Affected sites: both cloud
`make_request`s (they Set only Content-Type/Authorization). The Firefox-UA
grabbers (FF-4) all matched — s11 failed only on its plain (even-indexed)
requests.

**No inventory row covered the implicit default** — a genuine gap the judge
was built to catch. Fix: explicit `User-Agent: Go-http-client/1.1` header at
both cloud sites (comments cite net/http `Request.write defaultUserAgent`
and the scenario receipts). Queued as amendment **A-21** for the rulebook.

**Second pass: 18/18, exit 0.**

## Final receipts

- Parity judge: **18/18** (`parity-2026-10-28.json`)
- Inherited suite: **14/14**
- Whole-tree referee: **ruff PASS + mypy --strict PASS, 49 files**
- Marker census for post-parity: TODO(port) 24 · PERF(port) 1 · BUG(port) 3
  (one is the sanctioned unbounded read, grabber row 27)

## Commit surface (human commits)

Product: `src/`, `pyproject.toml`, `uv.lock`, `Makefile`, `README.md`,
`.gitignore` (caches ignored; `.claude/` now ignored as process scaffolding
— remove that line if you want the guardrails in-repo).
`migration/` is process evidence: the judge (`run.py`, `harness.py`,
`fixtures/`, `proxy.py`, `capture.py`) + parity JSON are the exit-condition
receipts and stay runnable; `migration/judge/bin/*` are prebuilt binaries
(rebuildable from the Go source — commit or exclude per taste).
Deleted as trash: `tests/test_placeholder.py` (pass-only scaffold).

## Next

Step 7 (post-parity): sweep the 28 markers, classify fix-now vs
document-and-close — on your sign-off.
