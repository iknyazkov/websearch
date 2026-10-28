#!/usr/bin/env python3
"""Deterministic Go dependency map for the websearch migration (stdlib only).

Parses `import` declarations (single and grouped), keeps in-repo edges only
(module path from go.mod; third-party/std imports are neither edges nor
misses), and emits, all sorted for reproducibility:

  edges.tsv          file<TAB>file         one edge per imported in-repo package
                                          file -> each non-test file of that package
  order.txt          batch lines           one line per Go PACKAGE (the translation
                                          unit), files tab-separated, dependency
                                          packages first (Kahn, sorted tie-break)
  cycles.txt         file-level SCCs       >1 member or self-loop (Go's compiler
                                          forbids package cycles; expected empty —
                                          the check stays because it is cheap)
  package_edges.tsv  pkg<TAB>pkg           the graph condensed to packages
  package_order.txt  one package per line  topological
  package_cycles.txt package-level SCCs    expected empty

A _test.go file is a node: it is real translation work (the port's unit
tests). Its edges go to the non-test files of every package it imports
(including its own directory's package when it is an external _test package);
same-file self-loops are dropped. Dead code (no importers) simply lands in
the first batch — order.txt is a schedule, not a liveness report.

Usage: depmap_go.py [--src DIR] [--out DIR]  (defaults: the source repo,
migration/depmap, resolved relative to this script's parent's parent)
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

MODULE_RE = re.compile(r"^module\s+(\S+)", re.MULTILINE)


def strip_comments(text: str) -> str:
    """Remove // and /* */ comments, preserving string literals."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


IMPORT_SINGLE_RE = re.compile(r'^import\s+"([^"]+)"', re.MULTILINE)
IMPORT_GROUP_RE = re.compile(r"^import\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
IMPORT_LINE_RE = re.compile(r'"([^"]+)"')


def imports_of(text: str) -> list[str]:
    """All import paths in one file (comment-stripped text), in order found."""
    found: list[str] = []
    for match in IMPORT_SINGLE_RE.finditer(text):
        found.append(match.group(1))
    for group in IMPORT_GROUP_RE.finditer(text):
        found.extend(IMPORT_LINE_RE.findall(group.group(1)))
    return found


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path,
                    default=pathlib.Path.home() / "Downloads" / "websearch")
    ap.add_argument("--out", type=pathlib.Path, default=here)
    args = ap.parse_args()
    src: pathlib.Path = args.src.resolve()
    out: pathlib.Path = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    module = MODULE_RE.search((src / "go.mod").read_text(encoding="utf-8"))
    if module is None:
        print("ERROR: no `module` line in go.mod", file=sys.stderr)
        return 1
    module_path = module.group(1)

    files = sorted(p.relative_to(src).as_posix() for p in src.rglob("*.go")
                   if "vendor" not in p.parts)
    # package dir -> {non-test files}, {test files}
    packages: dict[str, dict[str, list[str]]] = {}
    for f in files:
        pkg = str(pathlib.PurePosixPath(f).parent)
        if pkg == ".":
            pkg = "<root>"
        kind = "test" if f.endswith("_test.go") else "prod"
        packages.setdefault(pkg, {"prod": [], "test": []})[kind].append(f)

    def dir_of(import_path: str) -> str | None:
        """In-repo package directory for an import path, else None."""
        if import_path == module_path:
            return "<root>"
        if import_path.startswith(module_path + "/"):
            rel = import_path[len(module_path) + 1:]
            return str(pathlib.PurePosixPath(rel))
        return None

    edges: set[tuple[str, str]] = set()
    unknown_imports: set[str] = set()
    for f in files:
        text = strip_comments((src / f).read_text(encoding="utf-8"))
        for imp in imports_of(text):
            pkg = dir_of(imp)
            if pkg is None:
                continue  # third-party or std: neither edge nor miss
            if pkg not in packages:
                unknown_imports.add(imp)
                continue
            for target in packages[pkg]["prod"]:
                if target != f:
                    edges.add((f, target))

    # file-level graph -> topological batches are built at PACKAGE level (the
    # translation unit). Package A depends on B iff any file of A has an edge
    # to any file of B (A != B).
    pkg_edges: set[tuple[str, str]] = set()
    for a, b in edges:
        pa = str(pathlib.PurePosixPath(a).parent) or "<root>"
        pb = str(pathlib.PurePosixPath(b).parent) or "<root>"
        pa = "<root>" if pa == "." else pa
        pb = "<root>" if pb == "." else pb
        if pa != pb:
            pkg_edges.add((pa, pb))

    def topo(nodes: list[str], dep: dict[str, set[str]]) -> tuple[list[str], list[str]]:
        """Kahn with sorted ready-queue. Returns (ordered, leftover-iff-cyclic)."""
        indeg = {n: 0 for n in nodes}
        dependents: dict[str, list[str]] = {n: [] for n in nodes}
        for a, b in dep:  # a depends on b  =>  edge b -> a
            if a in indeg and b in indeg:
                indeg[a] += 1
                dependents[b].append(a)
        ready = sorted(n for n, d in indeg.items() if d == 0)
        ordered: list[str] = []
        while ready:
            n = ready.pop(0)
            ordered.append(n)
            for m in sorted(dependents[n]):
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
            ready.sort()
        leftover = [n for n in nodes if n not in set(ordered)]
        return ordered, leftover

    pkg_nodes = sorted(packages)
    pkg_order, pkg_leftover = topo(pkg_nodes, pkg_edges)
    cycles: list[str] = []
    if pkg_leftover:
        cycles.append("cyclic packages (unresolvable topological order): "
                      + ", ".join(sorted(pkg_leftover)))

    # file order within each package batch: prod files first (sorted), then
    # test files (sorted) — the tests of a package translate with it.
    order_lines: list[str] = []
    for pkg in pkg_order:
        batch = packages[pkg]["prod"] + packages[pkg]["test"]
        order_lines.append("\t".join(batch))

    (out / "edges.tsv").write_text(
        "".join(f"{a}\t{b}\n" for a, b in sorted(edges)), encoding="utf-8")
    (out / "order.txt").write_text(
        "# one line per Go package (translation unit), dependencies first\n"
        + "\n".join(order_lines) + "\n", encoding="utf-8")
    (out / "cycles.txt").write_text(
        ("\n".join(cycles) + "\n") if cycles else "no cycles\n", encoding="utf-8")
    (out / "package_edges.tsv").write_text(
        "".join(f"{a}\t{b}\n" for a, b in sorted(pkg_edges)), encoding="utf-8")
    (out / "package_order.txt").write_text("\n".join(pkg_order) + "\n", encoding="utf-8")
    (out / "package_cycles.txt").write_text(
        ("\n".join(cycles) + "\n") if cycles else "no cycles\n", encoding="utf-8")

    print(f"files={len(files)} packages={len(pkg_nodes)} edges={len(edges)} "
          f"package_edges={len(pkg_edges)} cycles={'yes' if cycles else 'no'}")
    if unknown_imports:
        print("WARNING: in-repo import paths with no package dir: "
              + ", ".join(sorted(unknown_imports)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
