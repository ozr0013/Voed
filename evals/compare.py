"""Diff two eval result files (e.g. two models, or before/after a prompt change).

    python -m evals.compare evals/results/a.json evals/results/b.json

Prints per-category outcome rates side by side, and lists cases whose outcome flipped.
A difference is only worth believing if the confidence intervals don't overlap.
"""
from __future__ import annotations

import json
import sys


def _load(path: str) -> dict:
    return json.loads(open(path).read())


def _cell(block: dict) -> str:
    if not block["n"]:
        return "-"
    lo, hi = block["ci95"]
    return f"{block['rate']:.0%} [{lo:.0%}-{hi:.0%}]"


def main(a_path: str, b_path: str) -> int:
    a, b = _load(a_path), _load(b_path)
    label = lambda d: f"{d['meta']['agent']}:{d['meta']['model'] or '-'}:{d['meta']['screenshot']}"  # noqa: E731
    print(f"A = {label(a)}  ({a['meta']['git']})\nB = {label(b)}  ({b['meta']['git']})\n")
    for suite in sorted(set(a["summary"]) & set(b["summary"])):
        print(f"== {suite} ==")
        print(f"{'category':<14} {'A outcome':<20} {'B outcome':<20}")
        cats = ["OVERALL"] + sorted(set(a["summary"][suite]["by_category"]) | set(b["summary"][suite]["by_category"]))
        for c in cats:
            ga = a["summary"][suite]["overall" if c == "OVERALL" else "by_category"]
            gb = b["summary"][suite]["overall" if c == "OVERALL" else "by_category"]
            ra = ga["outcome"] if c == "OVERALL" else ga.get(c, {}).get("outcome", {"n": 0})
            rb = gb["outcome"] if c == "OVERALL" else gb.get(c, {}).get("outcome", {"n": 0})
            print(f"{c:<14} {_cell(ra):<20} {_cell(rb):<20}")
    ra = {(r["suite"], r["id"]): r for r in a["results"]}
    rb = {(r["suite"], r["id"]): r for r in b["results"]}
    flips = [(k, ra[k], rb[k]) for k in ra if k in rb and bool(ra[k].get("outcome_pass")) != bool(rb[k].get("outcome_pass"))]
    print(f"\nCases whose outcome differs: {len(flips)}")
    for (suite, cid), x, y in flips:
        fmt = lambda r: ", ".join(s["name"] for s in r.get("actions", [])) or "-"  # noqa: E731
        print(f"  {suite}/{cid}: A={'pass' if x.get('outcome_pass') else 'FAIL'} ({fmt(x)})  "
              f"B={'pass' if y.get('outcome_pass') else 'FAIL'} ({fmt(y)})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
