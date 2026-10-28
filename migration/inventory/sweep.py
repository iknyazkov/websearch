"""Gap-site sweep for the Go→Python migration (Step 1, gap-inventory).

Deterministically enumerates every SOURCE SITE where a Go→Python gap
category appears, across the 31 manifest units (dropped logger/markdown
excluded by construction — the manifest is the unit list). Emits one row
per (category, file, line) to migration/inventory/sites.tsv. That file is
the definition of done for the inventory: every site on it must have a
row in migration/inventory.tsv before the step closes.

Categories (classification vocabulary for inventory.tsv):
  BYTES       byte-vs-str boundary (len(), []byte, readers, charset)
  NIL         nil-able values flowing (nil literals, make(), append-to-nil)
  ERR         error construction/propagation (fmt.Errorf, errors.New, checks)
  IFACE       interface declarations (→ typing.Protocol)
  CTX         context.Context params (→ dropped per RULEBOOK §2)
  DEFER       defer sites (→ try/finally, FF-5 ordering)
  WIRE        JSON struct tags / Marshal / Unmarshal (→ explicit dicts)
  REGEX       regexp.MustCompile sites
  TIME        time formatting sites
  SELECTOR    goquery selector/iteration sites (→ bs4/soupsieve)
  HTTP        Go http client semantics (Status, headers, proxy, client)
  CONC        goroutines/channels/locks (expected: none — logger dropped)

Usage: uv run python migration/inventory/sweep.py [--src DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent

PATTERNS: list[tuple[str, str]] = [
    ("BYTES", r"\blen\(|\[\]byte|io\.ReadAll|io\.LimitReader|charset\.NewReader|"
              r"bytes\.NewReader|strings\.NewReader|utf8\."),
    ("NIL", r"\bnil\b|\bmake\("),
    ("ERR", r"fmt\.Errorf|errors\.New|err != nil|!= nil \{"),
    ("IFACE", r"type \w+ interface \{"),
    ("CTX", r"context\.Context"),
    ("DEFER", r"\bdefer "),
    ("WIRE", r'json:"|json\.Marshal|json\.Unmarshal|jsonschema:'),
    ("REGEX", r"regexp\.MustCompile"),
    ("TIME", r"time\.Now\(|\.Format\("),
    ("SELECTOR", r"\.Find\(|\.Each\(|goquery"),
    ("HTTP", r"http\.NewRequest|resp\.Status\b|\.StatusCode|Header\.Set\(|"
             r"http\.Client|ProxyURL|Transport\b|\.Get\(\"|\.Do\("),
    ("CONC", r"\bgo func|\bchan |\bsync\.|\.Lock\(|\.WaitGroup"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/Users/iknyazkov/Downloads/websearch")
    ap.add_argument("--manifest", default=str(HERE.parent / "manifest.tsv"))
    ap.add_argument("--out", default=str(HERE / "sites.tsv"))
    args = ap.parse_args()
    src = pathlib.Path(args.src)

    units = [line.split("\t")[0] for line in
             pathlib.Path(args.manifest).read_text().splitlines()[1:]
             if line.strip()]

    rows: list[tuple[str, str, int, str]] = []
    for rel in sorted(units):
        path = src / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for cat, pat in PATTERNS:
                if re.search(pat, line):
                    rows.append((cat, rel, lineno, line.strip()[:100]))
                    break  # one category per line: the first (highest-priority) match

    rows.sort(key=lambda r: (r[1], r[2], r[0]))
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("category\tfile\tline\tmatched\n")
        for cat, rel, lineno, text in rows:
            fh.write(f"{cat}\t{rel}\t{lineno}\t{text}\n")
    print(f"wrote {args.out}: {len(rows)} sites in {len(units)} units")
    by_cat: dict[str, int] = {}
    for cat, _, _, _ in rows:
        by_cat[cat] = by_cat.get(cat, 0) + 1
    for cat, _ in PATTERNS:
        print(f"  {cat:9s} {by_cat.get(cat, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
