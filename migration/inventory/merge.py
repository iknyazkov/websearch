"""Merge inventory shards into migration/inventory.tsv (gap-inventory, fan-out close).

Reads the seed rows (inventory.tsv) plus every migration/inventory.*.tsv
shard (written by the fan-out workers next to inventory.tsv), validates the 7-column shape, dedupes on (file, symbol,
source_construct) — seed rows win over shards, earlier shards win over
later ones — sorts deterministically, and rewrites migration/inventory.tsv.
Prints a mechanical receipt: per-shard counts, dropped duplicates, and the
merged wc -l. The count IS the audit (Run 2 lesson: narrated totals don't
reconcile).

Usage: uv run python migration/inventory/merge.py [--dry-run]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE.parent / "inventory.tsv"
COLUMNS = ["file", "symbol", "source_construct", "classification",
           "target_translation", "evidence", "status"]
SHARDS = ["ctx", "wire", "http", "nil", "iface-bytes", "tests"]


def load(path: pathlib.Path) -> tuple[list[list[str]], list[str]]:
    """Return (rows, errors) — rows with exactly COLUMNS fields."""
    rows: list[list[str]] = []
    errors: list[str] = []
    if not path.exists():
        return rows, [f"{path.name}: missing"]
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        if lineno == 1 and line.split("\t", 2)[:2] == COLUMNS[:2]:
            continue  # header
        fields = line.split("\t")
        if len(fields) != len(COLUMNS):
            errors.append(f"{path.name}:{lineno}: {len(fields)} fields != {len(COLUMNS)}")
            continue
        rows.append(fields)
    return rows, errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = [("seed", MAIN)] + [(n, HERE.parent / f"inventory.{n}.tsv") for n in SHARDS]

    errors: list[str] = []
    final: dict[tuple[str, str, str], tuple[list[str], str]] = {}
    dropped: list[str] = []
    receipt: list[str] = []

    for name, path in sources:
        rows, errs = load(path)
        errors += [f"[{name}] {e}" for e in errs]
        added = 0
        for f in rows:
            key = (f[0], f[1], f[2])
            if key in final:
                dropped.append(f"{key[0]} | {key[1][:60]} (dup of {final[key][1]})")
                continue
            final[key] = (f, name)
            added += 1
        receipt.append(f"{name}\t{len(rows)} rows\t{added} new")

    if errors:
        print("=== VALIDATION ERRORS (merge aborted) ===")
        for e in errors:
            print(f"  {e}")
        return 1

    merged = sorted(final.values(), key=lambda v: (v[0][0], v[0][1], v[0][2]))
    for line in receipt:
        print(line)
    if dropped:
        print(f"duplicates dropped: {len(dropped)}")
        for d in dropped:
            print(f"  {d}")
    if args.dry_run:
        print(f"[dry-run] would write {MAIN}: {len(merged)} rows + header")
    else:
        body = "\n".join("\t".join(f) for f, _ in merged) + "\n"
        MAIN.write_text("\t".join(COLUMNS) + "\n" + body, encoding="utf-8")
        print(f"wrote {MAIN}")
    print(f"merged total: {len(merged)} rows (wc -l = {len(merged) + 1})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
