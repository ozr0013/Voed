"""VoiceCut eval runner.

    python -m evals.run --suite exec                       # engine oracles, no LLM needed
    python -m evals.run --suite planner --agent gold       # harness self-test, no LLM needed
    python -m evals.run --suite planner --model gemma3:4b  # real planner, needs Ollama running

Suites
  exec     Gold actions -> real edit engine -> deterministic ffprobe/numpy oracles.
           Proves the oracles (and the engine) are right, independent of any model.
  planner  Natural-language goal + timeline state + screenshot -> planner -> real edit
           engine -> the same oracles. Scores BOTH the action chosen and the outcome.

Not covered here: the VLM verifier (see README "Roadmap").
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from . import harness  # noqa: F401  (must come first: redirects DB/storage to a temp dir)
from .harness import (SessionLocal, Snapshot, make_project, render_screenshot, resolve,
                      run_assertions)
from .scoring import aggregate, match_action

from backend import ollama_client  # noqa: E402
from backend.agent import planner  # noqa: E402
from backend.agent.schemas import Action  # noqa: E402
from backend.edits import engine  # noqa: E402
from backend.edits.engine import EditError  # noqa: E402

HERE = Path(__file__).parent
TERMINAL = {"task_complete", "task_failed", "ask_user"}
NON_EDITS = TERMINAL | {"seek_preview"}


# --------------------------------------------------------------------------- #
# Agents (the thing under test)
# --------------------------------------------------------------------------- #
class OllamaAgent:
    """The real planner, called exactly as the app calls it."""

    name = "ollama"

    async def next(self, *, project, goal, screenshot, step, completed) -> dict[str, Any]:
        for attempt in range(3):
            try:
                out, latency_ms, _raw = await planner.plan(
                    project=project, goal=goal, screenshot=screenshot,
                    first_call=(step == 0), completed_steps=completed, last_verify=None,
                )
                break
            except ollama_client.OllamaError as e:
                if isinstance(e.__cause__, httpx.TimeoutException):
                    # Too slow for the request timeout. This is a REAL failure (the app would hit the
                    # same ceiling), not infra flakiness, so it is scored, not excluded.
                    return {"timeout": f"no response within the {ollama_client.generate.__kwdefaults__['timeout']:.0f}s request timeout"}
                # otherwise transport: Ollama down/restarting, not the model's fault
                if attempt == 2:
                    return {"infra": f"{type(e).__name__}: {str(e)[:160]}"}
                await asyncio.sleep(5 * (attempt + 1))
            except Exception as e:  # noqa: BLE001 — unparseable/invalid model output IS data
                return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        return {"action": out.action.model_dump(mode="json", exclude_none=True),
                "expected_result": out.expected_result, "latency_ms": latency_ms}


class GoldAgent:
    """Replays the case's reference solution. Self-tests the harness: every planner case
    must pass with this agent, or the case/oracle itself is wrong."""

    name = "gold"

    def __init__(self, case: dict):
        self._plan = list(case["gold"])

    async def next(self, *, project, goal, screenshot, step, completed) -> dict[str, Any]:
        raw = self._plan[step] if step < len(self._plan) else {"name": "task_complete"}
        return {"action": resolve(raw, project), "expected_result": "", "latency_ms": 0}


class NoopAgent:
    """Does nothing. Used by the selftest: every oracle that expects an edit must reject it."""

    name = "noop"

    async def next(self, *, project, goal, screenshot, step, completed) -> dict[str, Any]:
        return {"action": {"name": "task_complete"}, "expected_result": "", "latency_ms": 0}


# --------------------------------------------------------------------------- #
# Suites
# --------------------------------------------------------------------------- #
def _expects_no_change(case: dict) -> bool:
    return all(a["type"] == "unchanged" for a in case["assert"])


async def run_selftest(cases: dict) -> list[dict]:
    """Oracle discrimination: a do-nothing run must FAIL every case that expects a change,
    and pass the ones that expect no change. A case that a no-op passes can't tell a
    correct edit from no edit, so its score would be meaningless."""
    rows: list[dict] = []
    for c in cases["exec"]:
        if c.get("expect_error"):  # tests engine rejection, not an oracle
            continue
        db = SessionLocal()
        try:
            snap = Snapshot(db, make_project(db, prior=c.get("prior")))
            passed, notes = run_assertions(c["assert"], snap, snap)
        finally:
            db.close()
        rows.append({"id": c["id"], "category": c["category"], "suite": "selftest/exec",
                     "outcome_pass": not passed, "notes": ["no-op wrongly PASSES"] if passed else notes})
    for c in cases["planner"]:
        r = await run_planner_case(c, NoopAgent(), "blank", 1)
        want_pass = _expects_no_change(c)
        rows.append({"id": c["id"], "category": c["category"], "suite": "selftest/planner",
                     "outcome_pass": bool(r.get("outcome_pass")) == want_pass,
                     "notes": [] if bool(r.get("outcome_pass")) == want_pass
                     else [f"no-op outcome={r.get('outcome_pass')} but expected {want_pass}"] + r.get("notes", [])})
    return rows


def run_exec_case(case: dict) -> dict[str, Any]:
    db = SessionLocal()
    row: dict[str, Any] = {"id": case["id"], "category": case["category"], "suite": "exec"}
    try:
        project = make_project(db, prior=case.get("prior"))
        before = Snapshot(db, project)
        action = Action.model_validate(resolve(case["action"], project))
        t0 = time.time()
        try:
            engine.apply_action(db, project, action)
        except EditError as e:
            if case.get("expect_error"):  # a clean rejection is the correct behaviour
                db.refresh(project)
                ok, notes = run_assertions(case["assert"], before, Snapshot(db, project))
                row.update(outcome_pass=ok, notes=[f"rejected cleanly: {e}"] + notes)
            else:
                row.update(outcome_pass=False, notes=[f"EditError: {e}"])
            return row
        if case.get("expect_error"):
            row.update(outcome_pass=False, notes=["edit should have been rejected but was applied"])
            return row
        row["latency_ms"] = int((time.time() - t0) * 1000)
        db.refresh(project)
        ok, notes = run_assertions(case["assert"], before, Snapshot(db, project))
        row.update(outcome_pass=ok, notes=notes)
    except Exception as e:  # noqa: BLE001
        row.update(outcome_pass=False, notes=[f"harness error: {type(e).__name__}: {e}"])
    finally:
        db.close()
    return row


async def run_planner_case(case: dict, agent, shot_mode: str, max_steps: int) -> dict[str, Any]:
    db = SessionLocal()
    row: dict[str, Any] = {"id": case["id"], "category": case["category"], "suite": "planner",
                           "goal": case["goal"]}
    try:
        project = make_project(db, transcript=case.get("transcript"), prior=case.get("prior"))
        expect = resolve(case["expect"], project)
        multi = "all_of" in expect
        before = Snapshot(db, project)

        steps: list[dict] = []
        completed: list[str] = []
        latencies: list[int] = []
        schema_valid, edit_error, engine_crash = True, None, False
        for i in range(max_steps if multi else 1):
            shot = render_screenshot(project, 0.0, blank=(shot_mode == "blank"))
            r = await agent.next(project=project, goal=case["goal"], screenshot=shot,
                                 step=i, completed=completed)
            if "timeout" in r:
                row.update(timed_out=True, outcome_pass=False, action_ok=False, schema_valid=None,
                           notes=[f"TIMEOUT (counted as a failure): {r['timeout']}"])
                return row
            if "infra" in r:
                row.update(infra_error=r["infra"], outcome_pass=None, action_ok=None, schema_valid=None,
                           notes=[f"INFRA ERROR (excluded from rates): {r['infra']}"])
                return row
            if "error" in r:
                schema_valid, row["error"] = False, r["error"]
                break
            act = r["action"]
            steps.append(act)
            latencies.append(r["latency_ms"])
            if act["name"] in TERMINAL:
                break
            try:
                engine.apply_action(db, project, Action.model_validate(act))
                db.refresh(project)
            except EditError as e:
                edit_error = str(e)
                break
            except Exception as e:  # noqa: BLE001 — the app's execute_node only catches EditError
                db.rollback()
                edit_error, engine_crash = f"ENGINE CRASH {type(e).__name__}: {str(e)[-160:]}", True
                break
            completed.append(f"{act['name']}: {r['expected_result']}".strip())

        names = [s["name"] for s in steps]
        if multi:
            action_ok = schema_valid and all(any(n in group for n in names) for group in expect["all_of"])
            name_ok = action_ok
        else:
            name_ok, action_ok, _ = match_action(steps[0] if steps else None, expect["any_of"])
        forbidden = bool(set(names) & set(expect.get("forbid", []))) or (
            expect.get("forbid_edits", False) and any(n not in NON_EDITS for n in names))

        if schema_valid:
            ok, notes = run_assertions(case["assert"], before, Snapshot(db, project))
        else:
            ok, notes = False, ["planner output unusable"]
        if edit_error:
            notes.append(f"EditError: {edit_error}")
        row.update(
            schema_valid=schema_valid, action_ok=action_ok and not forbidden, name_ok=name_ok,
            outcome_pass=ok, forbidden_hit=forbidden, engine_crash=engine_crash, actions=steps, steps=len(steps),
            finished=bool(names and names[-1] == "task_complete"),
            latency_ms=latencies[0] if latencies else None,
            total_latency_ms=sum(latencies) if latencies else None, notes=notes,
        )
    except Exception as e:  # noqa: BLE001
        row.update(outcome_pass=False, notes=[f"harness error: {type(e).__name__}: {e}"])
    finally:
        db.close()
    return row


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _pct(block: dict) -> str:
    if not block["n"]:
        return "  -  "
    lo, hi = block["ci95"]
    return f"{block['k']}/{block['n']} ({block['rate']:.0%}, CI {lo:.0%}-{hi:.0%})"


def print_summary(agg: dict, results: list[dict], suite: str) -> None:
    print(f"\n=== {suite} ===")
    hdr = f"{'category':<14} {'n':>3}  {'outcome':<26} {'action':<26} {'p50 ms':>7}"
    print(hdr + "\n" + "-" * len(hdr))
    rows = [("OVERALL", agg["overall"])] + list(agg["by_category"].items())
    for cat, a in rows:
        p50 = f"{a['latency_ms_p50']:.0f}" if a["latency_ms_p50"] is not None else "-"
        print(f"{cat:<14} {a['cases']:>3}  {_pct(a['outcome']):<26} {_pct(a['action']):<26} {p50:>7}")
    o = agg["overall"]
    if o["schema"]["n"]:
        print(f"schema-valid: {_pct(o['schema'])}   forbidden-action hits: {o['forbidden_hits']}   "
              f"engine crashes: {o['engine_crashes']}   timeouts (failures): {o['timeouts']}   infra errors (excluded): {o['infra_errors']}   latency p95: {o['latency_ms_p95']}")
    bad = [r for r in results if not r.get("infra_error") and (not r.get("outcome_pass") or r.get("action_ok") is False)]
    if bad:
        print("\nFailures / action mismatches:")
        for r in bad:
            tag = "OUTCOME" if not r.get("outcome_pass") else "action-only"
            got = "; ".join(json.dumps(a) for a in r.get("actions", [])) or r.get("error", "-")
            print(f"  [{tag}] {r['suite']}/{r['id']}" + (f"  goal={r['goal']!r}" if "goal" in r else ""))
            print(f"      got: {got}")
            for n in r.get("notes", []):
                print(f"      {n}")


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------- #
async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", choices=["exec", "planner", "selftest", "all"], default="all")
    ap.add_argument("--agent", choices=["ollama", "gold"], default="ollama")
    ap.add_argument("--model", help="Ollama tag to evaluate (default: the app's active model)")
    ap.add_argument("--screenshot", choices=["synthetic", "blank"], default="synthetic",
                    help="'blank' ablates the screenshot to measure how much the model relies on it")
    ap.add_argument("--only", help="run only case ids containing any of these comma-separated substrings")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-call Ollama timeout in seconds (120 = the app's own; raise it to separate "
                         "slow-but-correct from wrong)")
    ap.add_argument("--max-steps", type=int, default=5, help="step cap for multi-step cases")
    ap.add_argument("--out", default=str(HERE / "results"), help="directory for the results JSON")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="exit 1 if the overall outcome pass rate is below this (CI gate)")
    args = ap.parse_args()

    cases = json.loads((HERE / "cases.json").read_text())
    pick = lambda xs: [c for c in xs if not args.only or any(o in c["id"] for o in args.only.split(","))]  # noqa: E731

    suites = ["exec", "planner"] if args.suite == "all" else [args.suite]
    if args.suite == "selftest":
        rows = await run_selftest(cases)
        agg = aggregate(rows)
        print_summary(agg, rows, "selftest (oracle discrimination: 'outcome' = oracle behaves correctly)")
        return 0 if agg["overall"]["outcome"]["k"] == agg["overall"]["outcome"]["n"] else 1
    # With the default ollama agent, an `all` run still works offline: only planner needs it.
    use_llm = "planner" in suites and args.agent == "ollama"
    model = args.model or ollama_client.get_active_model()
    if use_llm:
        ollama_client.generate.__kwdefaults__["timeout"] = args.timeout
        if args.model:
            ollama_client.get_active_model = lambda: args.model  # evals pin the model explicitly
        if not await ollama_client.is_up():
            print("Ollama is not reachable. Start it (`ollama serve`) or use --agent gold.", file=sys.stderr)
            return 2
        if not await ollama_client.has_model(model):
            print(f"Model '{model}' is not pulled. Run: ollama pull {model}", file=sys.stderr)
            return 2

    all_results: list[dict] = []
    summary: dict[str, Any] = {}
    for suite in suites:
        t0 = time.time()
        if suite == "exec":
            rows = [run_exec_case(c) for c in pick(cases["exec"])]
        else:
            rows = []
            for c in pick(cases["planner"]):
                agent = GoldAgent(c) if args.agent == "gold" else OllamaAgent()
                rows.append(await run_planner_case(c, agent, args.screenshot, args.max_steps))
                print(f"  {'ok  ' if rows[-1].get('outcome_pass') else 'FAIL'} {c['id']}", flush=True)
        agg = aggregate(rows)
        summary[suite] = agg
        all_results += rows
        print_summary(agg, rows, suite)
        print(f"({suite}: {len(rows)} cases in {time.time() - t0:.1f}s)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"{args.agent}-{model.replace(':', '_').replace('/', '_')}" if use_llm else args.agent
    path = out / f"{stamp}_{label}.json"
    path.write_text(json.dumps({
        "meta": {"timestamp": stamp, "git": _git_rev(), "agent": args.agent,
                 "model": model if use_llm else None, "screenshot": args.screenshot,
                 "suites": suites, "only": args.only, "timeout_s": args.timeout},
        "summary": summary, "results": all_results}, indent=2))
    print(f"\nresults -> {path}")

    if args.fail_under is not None:
        rate = (sum(1 for r in all_results if r.get("outcome_pass")) / len(all_results)) if all_results else 0.0
        if rate < args.fail_under:
            print(f"FAIL: outcome pass rate {rate:.0%} < {args.fail_under:.0%}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
