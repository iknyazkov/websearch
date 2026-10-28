#!/usr/bin/env python3
"""Diff a skeptic reviewer's ROW evidence against the generated dependency map.

Input: a text file containing reviewer rows `<file>\t<import path>\tL<line>`
(any other lines are ignored). Each row is expanded with the SAME rule the
depmap script uses — an import edge goes to every non-test file of the
imported package — and the resulting (file, target) pairs are diffed against
edges.tsv in BOTH directions:

  MISSED    edges.tsv has them, the reviewer's source-derived rows do not
            (script invented an edge, or expanded wrong)
  INVENTED  the reviewer found them in the source, edges.tsv lacks them
            (script missed an import)

Exit 0 iff no differences. Discrepancies are printed for source-checking —
only a discrepancy confirmed against the Go source is a script bug.

Usage: review_diff.py ROWS_FILE [--src DIR] [--map-dir DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", type=pathlib.Path)
    ap.add_argument("--src", type=pathlib.Path,
                    default=pathlib.Path.home() / "Downloads" / "websearch")
    ap.add_argument("--map-dir", type=pathlib.Path, default=HERE)
    args = ap.parse_args()
    src: pathlib.Path = args.src.resolve()

    # package dir -> non-test files (same enumeration as depmap_go.py)
    packages: dict[str, list[str]] = {}
    for p in src.rglob("*.go"):
        if "vendor" in p.parts:
            continue
        rel = p.relative_to(src).as_posix()
        if rel.endswith("_test.go"):
            continue
        pkg = str(pathlib.PurePosixPath(rel).parent)
        pkg = "<root>" if pkg == "." else pkg
        packages.setdefault(pkg, []).append(rel)

    module = ""
    for line in (src / "go.mod").read_text(encoding="utf-8").splitlines():
        if line.startswith("module "):
            module = line.split()[1]
            break

    def dir_of(import_path: str) -> str | None:
        if import_path == module:
            return "<root>"
        if import_path.startswith(module + "/"):
            rel = import_path[len(module) + 1:]
            return str(pathlib.PurePosixPath(rel))
        return None

    reviewer_edges: set[tuple[str, str]] = set()
    rows = 0
    for line in args.rows.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        f, imp = parts[0].strip(), parts[1].strip()
        pkg = dir_of(imp)
        if pkg is None:
            print(f"NOTE: row not under module (kept for audit): {f} -> {imp}")
            continue
        if pkg not in packages:
            print(f"BAD-ROW: {f} -> {imp}: no such package dir")
            return 2
        rows += 1
        for target in packages[pkg]:
            if target != f:
                reviewer_edges.add((f, target))

    map_edges = set()
    for line in (args.map_dir / "edges.tsv").read_text(encoding="utf-8").splitlines():
        a, b = line.split("\t")
        map_edges.add((a, b))

    missed = sorted(map_edges - reviewer_edges)
    invented = sorted(reviewer_edges - map_edges)

    # Only flag differences on files the reviewer was assigned (their rows
    # only cover their sample; edges of unassigned files are out of scope).
    assigned = {f for f, _ in reviewer_edges}
    missed = [(a, b) for a, b in missed if a in assigned]

    print(f"rows={rows} expanded_edges={len(reviewer_edges)} "
          f"assigned_files={len(assigned)}")
    # NOTE: files the reviewer reported as CLEAN (zero in-repo imports) appear
    # in no row and therefore contribute no edges here; check them separately
    # against edges.tsv (their map rows must be empty).
    print(f"MISSED_BY_REVIEWER (in map, not in rows): {len(missed)}")
    for a, b in missed:
        print(f"  {a} -> {b}")
    print(f"INVENTED_BY_SCRIPT-MISS (in rows, not in map): {len(invented)}")
    for a, b in invented:
        print(f"  {a} -> {b}")
    return 0 if not missed and not invented else 1


if __name__ == "__main__":
    sys.exit(main())
