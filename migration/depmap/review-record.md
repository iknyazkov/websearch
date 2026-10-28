# Dependency-map adversarial review (Step 1)

One round, both reviewers clean in both directions — no script bugs, no
regeneration. Evidence files: `review_a_rows.tsv`, `review_b_rows.tsv`
(source-derived ground truth; neither reviewer saw the map), diffed with
`review_diff.py` (self-tested symmetric against `edges.tsv` first).

## Sampling

- Assignment seed 20261026; random draws from non-overlapping topological
  halves, plus split adversarial categories per the skill.
- Reviewer A (opus, separate context): all 18 half-1 files (services core:
  logger, network, cloud, complex, grabber pipeline) + the 2 highest-fan-out
  half-2 files (`main.go`, `websearch/cloud/service.go`) — 20 files.
- Reviewer B (opus, separate context): all 18 half-2 files (tools, tests,
  dead-code candidates) + 3 repo-wide reverse checks — 18 files.
- Coverage: all 36 files reviewed; exactly 2 files double-covered, with
  identical independent reports.
- Model plan conformance: reviewers opus, as signed off at feasibility.

## Results

| Reviewer | Rows | Expanded edges | Missed by map | Invented by map | CLEAN files w/ map edges |
|---|---|---|---|---|---|
| A | 14 | 31 | 0 | 0 | 0 of 13 |
| B | 20 | 33 | 0 | 0 | 0 of 10 |

Cross-checks that independently agreed:
- B's tree-wide count of 26 in-repo import statements == the 26 (file,
  package) rows `edges.tsv` expands from.
- Dead-code claim (R1): `internal/services/logger` and
  `internal/services/webfetch/local/postprocessor/markdown` have zero
  importers — confirmed by exhaustive grep including tests; no
  plugin/cgo/reflect/go:generate mechanisms exist.
- Exclusion surface (R2): no vendor/, no generated files, no build tags,
  no testdata — a plain `**/*.go` walk needs no special-casing.
- Test semantics (R3): both `_test.go` files are INTERNAL test packages
  (`package github`, `package cloud`), so no self-import rows;
  `grabber_test.go`'s real import of the parent `grabber` package is in
  the map; `service_test.go` has no in-repo imports.

## Findings and dispositions (no confirmed discrepancies)

| # | Finding (both reviewers, merged) | Disposition |
|---|---|---|
| 1 | Aliased imports in `main.go` (`webfetchcloud`, `complex` shadowing the builtin, `websearchcloud`) | Script keys on full import paths inside `import` blocks; aliases never parsed. No change |
| 2 | `package cloud` declared by two different packages; basename collision | Same as 1 — directory, not package name, is the identity. No change |
| 3 | Single-line `import "ctx"` form used in-repo | Handled: `IMPORT_SINGLE_RE` (depmap_go.py:77). No change |
| 4 | `github.com`/URL string literals in `grabber.go`/`grabber_test.go` could fool a host-grep parser | Script scans only `import` blocks; literals never read. No change |
| 5 | `grabber_test.go` is `package github`, not `github_test` — an auto-added test self-import would be wrong | Script adds no such edge (parses imports only); map has none. No change |
| 6 | `main.go` does NOT import the `webfetch` interface package; tools packages import it instead | Matches the map exactly. No change |
| 7 | Same-name package import (`tools/webfetch` importing `services/webfetch` unaliased) is a symbol-resolution trap | Not a dependency-mapping concern (import paths disambiguate); noted for the rulebook's §4 naming to avoid the same trap in Python |
| 8 | markdown is an out-edge-bearing orphan (imports postprocessor, no importers); logger has no edges either way | Matches order.txt placement. Dead-code decision → rulebook §0, human's call |
