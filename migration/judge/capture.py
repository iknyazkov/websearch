"""Capture the fixedGo binary's normalized observations (amendment evidence).

Runs the affected scenarios against bin/websearch-fixedgo and dumps each
observation's normalized responses + proxy requests to JSON. The pinned
values in the amended harness (harness.py) come FROM THIS CAPTURE — never
hand-derived — and the capture is kept as evidence alongside the harness.

Usage: capture.py [--bin BIN] [--out JSON]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import harness
from harness import SCENARIOS, Scenario, observe, SEARCH_HOST, search_handler, fixture  # noqa: F401
from proxy import JudgeProxy

INTEREST = {"s01_tools_list", "s02_websearch_happy_linkup", "s06_plaintext_passthrough",
            "s07_html_extraction_rich", "s08_html_charset_cp1251",
            "s13_cloud_failover_to_local", "s16_empty_api_keys"}


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=str(here / "bin" / "websearch-fixedgo"))
    ap.add_argument("--out", default=str(here / "amendments-capture.json"))
    args = ap.parse_args()

    # Extra probe: WebSearch with an explicit limit — the FF-2 wire contract.
    limit_probe = Scenario(
        "s18_search_limit_honored",
        routes={harness.SEARCH_HOST: search_handler(fixture("linkup.json"))},
        calls=[("WebSearch", {"query": "limit probe", "limit": 2})],
    )

    proxy = JudgeProxy()
    captured = {}
    try:
        for sc in SCENARIOS:
            if sc.name not in INTEREST:
                continue
            captured[sc.name] = observe(args.bin, sc, proxy)
        captured[limit_probe.name] = observe(args.bin, limit_probe, proxy)
    finally:
        proxy.stop()

    pathlib.Path(args.out).write_text(json.dumps(captured, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"wrote {args.out}: {sorted(captured)}")

    # Console digest of the pins the harness needs.
    def content_of(obs):
        n = obs["responses"][0]["normalized"]
        return (n.get("structured") or {}).get("content")

    for name in ("s06_plaintext_passthrough", "s07_html_extraction_rich",
                 "s08_html_charset_cp1251", "s13_cloud_failover_to_local"):
        print(f"--- {name} content = {content_of(captured[name])!r}")
    lp = captured["s18_search_limit_honored"]
    body = next((r.get("body") for r in lp["proxy_requests"]
                 if r.get("host") == harness.SEARCH_HOST), None)
    print(f"--- s18 search body = {body!r}")
    s16 = captured["s16_empty_api_keys"]
    for r in s16["proxy_requests"]:
        print(f"--- s16 req {r['host']} authorization = "
              f"{r['headers'].get('authorization')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
