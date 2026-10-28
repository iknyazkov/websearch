"""Mutation validation for the parity judge (judge-setup, validation step).

Each mutant copies the Go source tree to a scratch dir, applies ALL SIX
FIX-FORWARD edits (fixedgo.EDITS — the RULEBOOK §0 spec the new side is
judged against), then exactly one behavior-changing mutation on top, builds,
and is judged old-vs-mutant with default sides (old,new). A mutant the judge
does NOT flag is a blind spot in the harness — that is the failure this
script exists to detect. Exit code 0 iff every mutant was caught.

Building from the FIXED source is what keeps a catch meaningful: a mutant
built from the ORIGINAL source fails all six fix contracts on the new side
(s01/s02/s06–s10/s13/s16/s18) regardless of its mutation, so "CAUGHT" fires
on anything and isolates nothing. On the fixed base, only the named mutation
can diverge. Fix-pinning itself is validated separately by the revert
binaries (fixedgo.py --revert k, see README).

Two mutation anchors differ on the fixed tree and are written against it:
m2 mutates the FF-4 UA literal, m4 misspells the FF-1 "title" key.

    uv run python migration/judge/mutations.py [--src DIR] [--ref BIN]

Defaults: --src /Users/iknyazkov/Downloads/websearch
          --ref <here>/bin/websearch-go
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

from fixedgo import EDITS

HERE = pathlib.Path(__file__).resolve().parent

# (name, repo-relative file, exact old text, new text, what the mutation breaks)
# Every `old` text must occur exactly once in its file — asserted at runtime.
MUTANTS: list[tuple[str, str, str, str, str]] = [
    (
        "m1_snippet_precedence",
        "internal/services/websearch/cloud/service.go",
        '\tif snippet != "" || len(content) == 0 {',
        "\tif len(content) == 0 {",
        "snippetFromContent: content now wins over a non-empty snippet",
    ),
    (
        "m2_client_ua",
        "internal/services/webfetch/local/grabber/client/fingerprint.go",
        'Firefox/158.0"',
        'Firefox/158.0-X"',
        ("client grabber User-Agent fingerprint altered (anchored on the "
         "FF-4 fixed literal — the old Chrome/91 string no longer exists)"),
    ),
    (
        "m3_url_check_dropped",
        "internal/tools/webfetch/webfetch.go",
        '\tif !strings.HasPrefix(input.URL, "http://") && !strings.HasPrefix(input.URL, "https://") {',
        '\tif false && !strings.HasPrefix(input.URL, "http://") && !strings.HasPrefix(input.URL, "https://") {',
        "WebFetch no longer rejects non-http(s) URLs",
    ),
    (
        "m4_wrong_title_key",
        "internal/tools/websearch/output.go",
        'json:"title"',
        'json:"titre"',
        ("title key misspelled on the FF-1-fixed tree: the side-aware "
         "waiver must NOT canonicalize a third value (query=old, "
         "title=fixed, anything else=divergence). The pre-amendment m4 "
         "(query->title) now equals the sanctioned FF-1 spec and would be "
         "correctly PASSED; replaced by this mutant at the amendment step"),
    ),
    (
        "m5_choice_json_branch",
        "internal/services/webfetch/local/postprocessor/choice/processor.go",
        "\tcase jsonContentType:\n\t\treturn postprocessor.ContentWasNotFound",
        '\tcase jsonContentType:\n\t\treturn "MUTATED-JSON"',
        "application/json branch returns content instead of empty",
    ),
    (
        "m6_github_file_routing",
        "internal/services/webfetch/local/grabber/github/grabber.go",
        "/blob/",
        "/tree/",
        "github file URLs miss the file regex -> generic grab fallback",
    ),
    (
        "m7_no_local_fallback",
        "internal/services/webfetch/complex/service.go",
        "\treturn service.localWebFetchService.Fetch(ctx, url, opts)",
        "\treturn result, err",
        "complex service returns the cloud failure, never falls back to local",
    ),
    (
        "m8_search_error_format",
        "internal/services/websearch/cloud/service.go",
        'fmt.Errorf("search request failed: %s", resp.Status)',
        'fmt.Errorf("search failed: %s", resp.Status)',
        "WebSearch non-2xx error string altered",
    ),
    (
        "m9_repo_regex_http_intolerance",
        "internal/services/webfetch/local/grabber/github/grabber.go",
        "`^https?://github\\.com/([^/]+)/([^/]+)/?$`",
        "`^https://github\\.com/([^/]+)/([^/]+)/?$`",
        "repo regex no longer tolerates http:// scheme (fallback fires)",
    ),
    (
        "m10_fetch_auth_unconditional",
        "internal/services/webfetch/cloud/service.go",
        '\tif apiKey != "" {\n\t\trequest.Header.Set("Authorization", "Bearer "+apiKey)\n\t}',
        '\trequest.Header.Set("Authorization", "Bearer "+apiKey)',
        "webfetch sends Authorization even with an empty API key",
    ),
    (
        "m11_results_dropped",
        "internal/services/websearch/cloud/service.go",
        "\treturn &websearch.Output{Results: results}, nil",
        "\treturn &websearch.Output{}, nil",
        ("search results dropped from the output (caught via s02's count; NOTE: "
         "a nil-vs-empty [] distinction is NOT Go-mutable — the go-sdk erases "
         "nil slices to [] before the wire, so s17's null-guard is port-side "
         "divergence only, see README)"),
    ),
    (
        "m12_description_template",
        "internal/tools/websearch/prompt.go",
        "IMPORTANT - Use the correct year in search queries:",
        "IMPORTANT: Use the correct year in search queries:",
        "WebSearch description template text altered",
    ),
    (
        "m13_month_format",
        "internal/tools/websearch/websearch.go",
        'return time.Now().Format("Jan 2006")',
        'return time.Now().Format("January 2006")',
        "month-year rendered in full-month format",
    ),
]


def build_one(name: str, relpath: str, old: str, new: str) -> pathlib.Path | None:
    """Copy the source, apply the six FIX-FORWARD edits, apply the mutation,
    build. Returns the binary path (None on a setup/build failure, with the
    reason printed)."""
    work = pathlib.Path(tempfile.gettempdir()) / "judge-mutations" / name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(ARGS.src, work)
    for fix_id, edit_rel, edit_old, edit_new in EDITS:
        target = work / edit_rel
        text = target.read_text()
        if text.count(edit_old) != 1:
            print(f"[ERROR] {name}: FF-{fix_id} pattern count "
                  f"{text.count(edit_old)} != 1 in {edit_rel}")
            return None
        target.write_text(text.replace(edit_old, edit_new, 1))
    target = work / relpath
    text = target.read_text()
    if text.count(old) != 1:
        print(f"[ERROR] {name}: pattern count {text.count(old)} != 1 in {relpath}")
        return None
    target.write_text(text.replace(old, new, 1))
    proc = subprocess.run(
        ["go", "build", "-o", "websearch-go", "."], cwd=work,
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        print(f"[ERROR] {name}: go build failed:\n{proc.stderr}")
        return None
    return work / "websearch-go"


def judge_mutant(binary: pathlib.Path) -> tuple[bool, list[str], str]:
    """Run the judge old-vs-mutant.

    Returns (caught, failing scenario names, note). A mutant counts as
    CAUGHT only if the JUDGE FLAGGED THE MUTANT — a new-side invariant
    failure or an old-vs-new divergence. A non-zero exit WITHOUT either
    (judge crash, broken reference binary producing only old-side
    failures) is an ERROR, not a catch: green lights must mean something.
    """
    proc = subprocess.run(
        [sys.executable, str(HERE / "run.py"),
         "--old", str(ARGS.ref), "--new", str(binary)],
        capture_output=True, text=True, cwd=str(HERE.parent.parent), check=False,
    )
    lines = proc.stdout.splitlines()
    failed = [line.split("] ", 1)[1].strip()
              for line in lines if line.startswith("[FAIL]")]
    new_side = any(line.lstrip().startswith("new invariant:")
                   or line.lstrip().startswith("divergence:") for line in lines)
    note = ""
    if proc.returncode != 0 and not new_side:
        note = ("exit non-zero but the mutant was never flagged "
                f"(judge crash? stderr: {proc.stderr.strip()[-200:]})")
    return new_side, failed, note


def preflight() -> bool:
    """Sanity-check the reference binary before trusting any result: the
    judge must pass cleanly with the reference playing both sides."""
    proc = subprocess.run(
        [sys.executable, str(HERE / "run.py"), "--old", str(ARGS.ref),
         "--sides", "old,old", "--filter", "s01"],
        capture_output=True, text=True, cwd=str(HERE.parent.parent), check=False,
    )
    if proc.returncode != 0:
        print(f"[ERROR] reference pre-flight failed (is --ref a working build?)\n"
              f"{proc.stdout[-400:]}{proc.stderr[-400:]}")
        return False
    return True


def main() -> int:
    if not preflight():
        return 1
    results: list[tuple[str, bool, list[str], str]] = []
    for name, relpath, old, new, desc in MUTANTS:
        print(f"== {name}: {desc}")
        binary = build_one(name, relpath, old, new)
        if binary is None:
            results.append((name, False, ["<setup-failed>"], desc))
            continue
        caught, failed, note = judge_mutant(binary)
        status = "CAUGHT" if caught else "*** MISSED ***"
        print(f"   {status}: {', '.join(failed) if failed else 'no scenario failed'}")
        if note:
            print(f"   NOTE: {note}")
        results.append((name, caught, failed, desc))

    print("\n=== mutation summary ===")
    for name, caught, failed, desc in results:
        status = "CAUGHT" if caught else "MISSED"
        print(f"[{status}] {name} ({'; '.join(failed) if failed else '-'}) — {desc}")
    missed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(missed)}/{len(results)} mutants caught")
    return 0 if not missed else 1


ARGS: argparse.Namespace  # populated in main()


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="/Users/iknyazkov/Downloads/websearch",
                        help="Go source tree to mutate copies of")
    parser.add_argument("--ref", default=str(HERE / "bin" / "websearch-go"),
                        help="reference (unmutated) Go binary")
    return parser.parse_args()


if __name__ == "__main__":
    ARGS = _parse()
    raise SystemExit(main())
