"""Build the FIXED-GO conformance binary for the judge amendments (DEV-003).

The rulebook's FIX-FORWARD list (FF-1..FF-6, migration/RULEBOOK.md §0) changes
the spec: the port must exhibit the FIXED behavior, which the original binary
does not have. This script applies the six fixes to a COPY of the Go source
and builds it — that binary is the executable spec of the fixed behavior,
exactly as the original binary is the spec of the old one.

The amended judge is then validated two ways:
  * old vs fixedGo must pass 17/17 — the side-aware waivers must cover
    exactly the six fix deltas, nothing more;
  * `--revert k` builds fixedGo WITHOUT fix k — the judge must CATCH each
    one (every fix is pinned, no waiver is a free pass).

Each edit asserts its old text occurs exactly once (count==1) so a drifted
source fails loudly instead of producing a silently-wrong binary.

Usage: fixedgo.py [--src DIR] [--out BIN] [--revert 1|2|3|4|5|6]
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

FF4_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) "
          "Gecko/20100101 Firefox/158.0")

# (fix-id, file, old, new) — order matters only for imports; ids are stable.
EDITS: list[tuple[str, str, str, str]] = [
    # FF-1: SearchHit.Title serializes as "title" (schema tag follows).
    ("1", "internal/tools/websearch/output.go",
     'json:"query"', 'json:"title"'),
    # FF-2a: the tool input gains a limit field.
    ("2", "internal/tools/websearch/input.go",
     '\tQuery string `json:"query" jsonschema:"The search query to use"`\n}',
     '\tQuery string `json:"query" jsonschema:"The search query to use"`\n'
     '\tLimit int    `json:"limit,omitempty" jsonschema:"Maximum number of '
     'results to return"`\n}'),
    # FF-2b: honor a positive limit; 50 stays the default.
    ("2", "internal/tools/websearch/websearch.go",
     "\twebSearchInput := websearch.Input{\n\t\tQuery: input.Query,\n"
     "\t\tLimit: 50,\n\t}",
     "\tlimit := 50\n\tif input.Limit > 0 {\n\t\tlimit = input.Limit\n\t}\n\n"
     "\twebSearchInput := websearch.Input{\n\t\tQuery: input.Query,\n"
     "\t\tLimit: limit,\n\t}"),
    # FF-3: no Authorization header when the search API key is empty.
    ("3", "internal/services/websearch/cloud/service.go",
     '\trequest.Header.Set("Content-Type", "application/json")\n'
     '\trequest.Header.Set("Authorization", "Bearer "+apiKey)',
     '\trequest.Header.Set("Content-Type", "application/json")\n'
     "\tif apiKey != \"\" {\n"
     '\t\trequest.Header.Set("Authorization", "Bearer "+apiKey)\n\t}'),
    # FF-4: the Firefox fingerprint is a real current Firefox UA.
    ("4", "internal/services/webfetch/local/grabber/client/fingerprint.go",
     'Firefox Fingerprint = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
     'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 '
     'Safari/537.36"',
     f'Firefox Fingerprint = "{FF4_UA}"'),
    # FF-5: read the (capped) body BEFORE the response is closed.
    ("5", "internal/services/webfetch/local/grabber/client/grabber.go",
     '\treturn &grabber.Result{\n\t\tReader:     io.LimitReader(resp.Body, '
     'maxBodySize),\n\t\tParameters: resp.Header,\n\t}, nil',
     '\tbody, err := io.ReadAll(io.LimitReader(resp.Body, maxBodySize))\n'
     '\tif err != nil {\n\t\treturn nil, err\n\t}\n\n'
     '\treturn &grabber.Result{\n\t\tReader:     bytes.NewReader(body),\n'
     '\t\tParameters: resp.Header,\n\t}, nil'),
    ("5", "internal/services/webfetch/local/grabber/client/grabber.go",
     '\t"context"\n\t"fmt"\n\t"io"\n', '\t"bytes"\n\t"context"\n\t"fmt"\n\t"io"\n'),
    # FF-6: match Content-Type on the media type only (parse before ";").
    ("6", "internal/services/webfetch/local/postprocessor/choice/processor.go",
     '\tcontentType := parameters.Get("Content-Type")\n\tswitch contentType {',
     '\tcontentType := parameters.Get("Content-Type")\n'
     "\tif i := strings.IndexByte(contentType, ';'); i >= 0 {\n"
     "\t\tcontentType = contentType[:i]\n\t}\n"
     "\tcontentType = strings.ToLower(strings.TrimSpace(contentType))\n"
     "\tswitch contentType {"),
    ("6", "internal/services/webfetch/local/postprocessor/choice/processor.go",
     '\t"io"\n\t"net/http"\n', '\t"io"\n\t"net/http"\n\t"strings"\n'),
]


def build(src: pathlib.Path, out: pathlib.Path, revert: str | None) -> int:
    work = pathlib.Path(__import__("tempfile").gettempdir()) / "judge-fixedgo"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(src, work)
    applied = 0
    for fix_id, relpath, old, new in EDITS:
        if revert == fix_id:
            continue
        target = work / relpath
        text = target.read_text()
        if text.count(old) != 1:
            print(f"[ERROR] FF-{fix_id} {relpath}: pattern count "
                  f"{text.count(old)} != 1")
            return 1
        target.write_text(text.replace(old, new, 1))
        applied += 1
    proc = subprocess.run(["go", "build", "-o", str(out), "."], cwd=work,
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        print(f"[ERROR] go build failed:\n{proc.stderr}")
        return 1
    label = f"fixedGo (FF-{revert} REVERTED)" if revert else "fixedGo (all fixes)"
    print(f"built {label}: {out} ({applied} edits applied)")
    return 0


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path,
                    default=pathlib.Path.home() / "Downloads" / "websearch")
    ap.add_argument("--out", type=pathlib.Path,
                    default=here / "bin" / "websearch-fixedgo")
    ap.add_argument("--revert", choices=["1", "2", "3", "4", "5", "6"],
                    help="build with this ONE fix reverted (validation)")
    args = ap.parse_args()
    suffix = f"-no{args.revert}" if args.revert else ""
    args.out = args.out.with_name(args.out.name + suffix)
    return build(args.src.resolve(), args.out, args.revert)


if __name__ == "__main__":
    sys.exit(main())
