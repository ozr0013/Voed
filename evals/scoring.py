"""Pure scoring helpers (no backend / ffmpeg / Ollama imports, so they unit-test fast)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

# Parameter aliases the engine accepts (rotate takes `angle` or `degrees`).
_ALIASES = {"degrees": "angle"}

NUMERIC_TOL = 0.5  # seconds / units, unless a case overrides with "tol"


def _canon(params: dict[str, Any]) -> dict[str, Any]:
    return {_ALIASES.get(k, k): v for k, v in params.items() if v is not None}


def _value_ok(actual: Any, want: Any, tol: float) -> bool:
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        try:
            return abs(float(actual) - float(want)) <= tol
        except (TypeError, ValueError):
            return False
    if isinstance(want, str):
        return str(actual).strip().lower() == want.strip().lower()
    return actual == want


def match_action(
    actual: dict[str, Any] | None, alternatives: list[dict[str, Any]]
) -> tuple[bool, bool, int | None]:
    """Compare a planner action against acceptable alternatives.

    Returns (name_ok, params_ok, index_of_matching_alternative). `params_ok` implies
    `name_ok`. Only the params listed in an alternative are checked; extra params the
    model emits are ignored (the engine ignores them too).
    """
    if not actual:
        return False, False, None
    name = actual.get("name")
    act = _canon({k: v for k, v in actual.items() if k != "name"})
    name_ok = False
    for i, alt in enumerate(alternatives):
        if alt.get("name") != name:
            continue
        name_ok = True
        tol = float(alt.get("tol", NUMERIC_TOL))
        want = _canon(alt.get("params", {}))
        if all(k in act and _value_ok(act[k], v, tol) for k, v in want.items()):
            return True, True, i
    return name_ok, False, None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate. Honest error bars for small n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Iterable[float], q: float) -> float | None:
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _rate(rows: list[dict], key: str) -> dict[str, Any]:
    scored = [r for r in rows if r.get(key) is not None]
    k = sum(1 for r in scored if r[key])
    lo, hi = wilson(k, len(scored))
    return {"k": k, "n": len(scored), "rate": (k / len(scored)) if scored else None,
            "ci95": [round(lo, 3), round(hi, 3)]}


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Overall + per-category rollup of per-case result rows."""
    def roll(rows: list[dict]) -> dict[str, Any]:
        return {
            "cases": len(rows),
            "outcome": _rate(rows, "outcome_pass"),
            "action": _rate(rows, "action_ok"),
            "schema": _rate(rows, "schema_valid"),
            "latency_ms_p50": percentile((r.get("latency_ms") for r in rows), 0.5),
            "latency_ms_p95": percentile((r.get("latency_ms") for r in rows), 0.95),
            "forbidden_hits": sum(1 for r in rows if r.get("forbidden_hit")),
            "engine_crashes": sum(1 for r in rows if r.get("engine_crash")),
            "infra_errors": sum(1 for r in rows if r.get("infra_error")),
            "timeouts": sum(1 for r in rows if r.get("timed_out")),
        }

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_cat[r.get("category", "uncategorised")].append(r)
    return {"overall": roll(results), "by_category": {c: roll(rs) for c, rs in sorted(by_cat.items())}}
