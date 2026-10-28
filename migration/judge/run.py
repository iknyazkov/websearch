"""CLI for the parity judge.

    make judge-old                          # reference determinism self-check
    uv run python migration/judge/run.py --old migration/judge/bin/websearch-go --sides old,old
    uv run python migration/judge/run.py --old .../websearch-fixedgo --sides new,new
    uv run python migration/judge/run.py --old .../websearch-go --new <python-entry>

--sides OLD,SIDE names the spec contract each binary is judged against
(default old,new): "old" = the original spec, "new" = the RULEBOOK
FIX-FORWARD spec. Amended scenarios are side-branched, so a plain old-vs-old
run can no longer pass them — use --sides old,old for the reference
self-check and --sides new,new to self-check a fixed-spec binary.
Exit code 0 iff the judge passes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from harness import SCENARIOS, Judge


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, help="path to the Go reference binary")
    parser.add_argument("--new", default=None, help="path/command of the port (defaults to --old)")
    parser.add_argument("--sides", default="old,new",
                        help="spec contract per binary, OLD,SIDE (old|new each)")
    parser.add_argument("--filter", default=None, help="substring filter on scenario names")
    parser.add_argument("--out", default=None, help="write the full JSON report here")
    args = parser.parse_args()

    sides = tuple(args.sides.split(","))
    if len(sides) != 2 or any(s not in ("old", "new") for s in sides):
        parser.error("--sides must be OLD,SIDE with each in {old,new}")

    scenarios = [s for s in SCENARIOS if args.filter and args.filter in s.name] if args.filter else SCENARIOS
    judge = Judge(args.old, args.new, scenarios, sides=sides)  # type: ignore[arg-type]
    report = judge.run()

    for entry in report["scenarios"]:
        status = "PASS" if entry["ok"] else "FAIL"
        print(f"[{status}] {entry['name']}")
        for failure in entry["old_invariant_failures"]:
            print(f"    old invariant: {failure}")
        for failure in entry["new_invariant_failures"]:
            print(f"    new invariant: {failure}")
        if entry["diverged"]:
            for diff in entry["diff"] or []:
                print(f"    divergence: {diff}")
    print(f"\n{report['passed']}/{report['passed'] + report['failed']} scenarios pass")

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
