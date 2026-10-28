# Step 7 — Post-parity burndown report

Date: 2026-10-28. Gate: **STOPPED for human sign-off.** Nothing is committed;
the working tree (vs `b4b664c`) is the whole of Step 7: 14 files,
+150/−90 after review fixes.

## Marker collection receipt

Mechanical grep (`grep -rn "BUG(port)\|TODO(port)\|PERF(port)" src/ --include="*.py"`)
at step open: **27 markers** across 14 files — 6 fix-now + 21 document-and-close.
Post-close grep: **0 markers**. All 31 `# PORT STATUS:` trailers now read
`todos=0` (websearch.py bumped `confidence=medium → high`: its two flagged
unknowns are exactly what this step resolved).

## Classification table

| # | File:site | Class | One-line reasoning |
|---|---|---|---|
| F1 | network/client.py redirect cap | **fix now** | Go caps at 10 requests; httpx default 20 diverges |
| F2 | grabber/client/grabber.py body cap | **fix now** | read-then-slice buffers unbounded; io.LimitReader is streamed |
| F3 | grabber/client/grabber.py headers | **fix now** | items() comma-joins repeated headers; Go Header.Get = first |
| F4 | grabber/github/grabber.py control chars | **fix now** | urlsplit strips \t\r\n (bpo-43882); Go rejects the URL |
| F5 | grabber/github/grabber.py error type | **fix now** | §2 row 91 typed-exception convention |
| F6 | webfetch/cloud/service.py status line | **fix now** | reason-less Go status renders bare "500", no trailing space |
| C1 | tools/webfetch.py:105 unknown-tool | close | go-sdk text undecided by inventory; twins identical; unreachable |
| C2 | tools/websearch.py:171 unknown-tool | close | same as C1 |
| C3 | tools/websearch.py:200 twin envelope | close (STALE) | recorded divergence false: both twins decode inside try — verified |
| C4 | network/client.py:79 scheme-less proxy | close | no httpx API mounts it; judge-invisible; degrade-to-direct kept |
| C5 | network/client.py:88 fallbackDial | close | httpx has no dial hook; judge proxy is IP literal |
| C6 | websearch/cloud/service.py:117 urlsplit | close | row 68 decided; env-supplied base only |
| C7 | websearch/cloud/output.py:210 lenient parse | close | row 62 formula pinned; fixtures well-formed |
| C8 | webfetch/local/service.py:93 byte length | close | port matches Go bytes; quirk is Go's own |
| C9 | grabber/result.py:43 flattening | close | resolved BY F3 (producer now first-value) |
| C10 | postprocessor/choice/processor.py:55 U+FFFD | close | diverges only on invalid-UTF-8; no fixture |
| C11 | postprocessor/html:173 body-less docs | close | Go-unreachable branch; kept |
| C12 | postprocessor/html:296 WHATWG superset | close | unreachable in fixtures |
| C13 | postprocessor/html:376 utf-16 remap | close | implemented faithfully; unreachable |
| C14 | grabber/github/grabber.py:190 no cap | close | Go's io.ReadAll is unbounded too (spec quirk) |
| C15 | webfetch/cloud/service.py:180 kept error | close | §0 kept-quirk; unreachable publicly |
| C16 | webfetch/cloud/service.py:184 status line | close | folded into F6's edit |
| C17 | webfetch/cloud/service.py:188 U+FFFD | close | folded into F6's edit |
| C18 | webfetch/cloud/service.py:219 urlsplit | close | row 8 decided; env base only |
| C19 | webfetch/cloud/service.py:254 Config-by-value | close | rows 11/12 spell in-place form |
| C20 | webfetch/cloud/output.py:92 strictness | close | row 5 formula pinned; fixtures well-formed |
| C21 | webfetch/cloud/output.py:108 first value | close | A-6 decided; unreachable via complex-service swallow |
| C22 | webfetch/cloud/output.py:114 body shape | close | twin precedent (row 62); unjudged |

Marker accounting reconciles: 26 grep hits removed in-tree (C16/C17 were folded
into one edit) + 1 stale correction = the 27 classified.

## Per-fix parity proofs

Every fix shipped individually: file-scoped `ruff check` + `mypy` green, then
full judge re-run. Probes beyond the judge:

- **F1** — judge 18/18 (judge-invisible: no scenario redirects).
- **F2** — probe: 5 MB cap exact (bytes 5242880..5242890 → 5242880 bytes),
  small body whole; judge 18/18.
- **F3** — probe: repeated header keeps `"first"` (old code: `"first, second"`
  comma-join); comma-valued `accept: "a, b"` passes verbatim; judge 18/18.
- **F4** — probe: `\n`/`\t` addresses → False; `%09` stays True; judge 18/18
  (s15 is_can_grab variants).
- **F5** — tests narrowed to `pytest.raises(RequestFailedError, match=...)`,
  14/14; wire message byte-identical; judge 18/18.
- **F6** — probe: `httpx.Response(599).reason_phrase == ""` → renders `"599"`;
  known-code path renders `"500 Internal Server Error"`; judge 18/18.

## Adversarial review (1 reviewer over the whole Step-7 diff)

**Deviation, logged:** the skill prescribes reviewers per flagged change; the
human's standing trim ("implementers only" topology precedent) was applied by
analogy — ONE adversarial reviewer (model 'sonnet' → glm-5.3) over the whole
diff. It earned its keep: **5 confirmed findings**, 4 of them mine:

1. **F1 off-by-one (CONFIRMED-DEFECT → fixed as F1b):** Go issues 10 requests
   on an infinite redirect chain; httpx@`max_redirects=10` issues 11 (raises
   only when `len(history) > max_redirects`). Exact pin is **9**. Probed on
   both engines by the reviewer. Fixed: both constructions now `max_redirects=9`,
   comment corrected with the accounting.
2. **F4 incomplete (CONFIRMED-DEFECT → fixed as F4b):** the guard covered only
   the three bytes urlsplit strips; Go rejects EVERY byte < 0x20 and 0x7f.
   Reviewer probed `\x0b/\x0c/\x7f` → True where Go says False. Fixed:
   module-level `_CTL_BYTE = re.compile(r"[\x00-\x1f\x7f]")`; all reviewer
   probe cases now Go-exact (re-probed post-fix).
3. **result.py docstring contradicted F3 (CONFIRMED → fixed):** class docstring
   still taught the deleted `items()` comprehension. Rewritten to the
   multi_items()+setdefault producer.
4. **Dangling citation (CONFIRMED → fixed):** `stream.go:46` exists nowhere in
   the source tree or module cache; replaced with encoding/json Decode + the
   real call site (cloud/service.go:113).
5. **Process (CONFIRMED → queued):** recurring close patterns must queue a
   rulebook amendment; none had been. Queued as **A-22** (see below), covering
   the three recurring classes, the F1b redirect-accounting rule, stale §0/§3
   marker citations, and the typed-exception asymmetry.

Clean verdicts (reviewer's own): F2, F3, F6 verified clean with independent
probes; F5 wire-identical; all closes code-clean (diff contains no uncommented
line outside F1–F6); markers/trailers honest; 10 citation pairs spot-checked
against the Go source.

## Final proofs (after review fixes)

- `ruff check .` — All checks passed
- `mypy .` — no issues in 49 source files
- `pytest -q` — 14 passed
- Parity judge — **18/18, exit 0** — receipt: `migration/judge/parity-step7-final.json`
- Marker grep — 0

## Amendment queue

**A-22** appended to `migration/inventory/queued-rulebook-amendment.md`
(recurring patterns a/b/c/d + F1b rule + stale citations + ValueError
asymmetry). Rulebook itself untouched, per standing rule 1.

## Commit surface (yours)

`git add -A && git commit` — suggested message:
`Step 7 post-parity: 6 fixes + 21 closes, review-hardened (F1b/F4b), judge 18/18, markers 0`
