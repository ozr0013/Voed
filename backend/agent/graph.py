"""LangGraph orchestration for the plan -> act -> verify loop.

The graph is the backend brain of one voice command. It reuses the existing
planner / verifier / edit-engine functions as nodes and keeps Gemma (via Ollama)
as the model — LangGraph only sequences the work and makes each run a resumable,
checkpointed thread.

Screenshots come from the browser (it captures the live editor DOM), so the graph
pauses with `interrupt()` whenever it needs a fresh screenshot:

  START -> plan -> (terminal? -> END)
                -> execute -> verify_gate[interrupt: verify screenshot]
                -> verify -> loop_gate[interrupt: next plan screenshot] -> plan ...

One run == one `thread_id`. The HTTP layer feeds screenshots in by resuming the
thread (`Command(resume=<png bytes>)`) and reads the resulting state to build its
response. This preserves the existing /step + /verify contract with the frontend.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .. import storage
from ..config import settings
from ..db import SessionLocal
from ..edits import engine
from ..edits.engine import EditError
from ..models import AgentRun, AgentStep, Project, utcnow
from . import planner, verifier
from .schemas import Action

# Actions that end a run without an edit + verification pass.
TERMINAL_NAMES = {"task_complete", "task_failed", "ask_user"}


class AgentState(TypedDict, total=False):
    # identity / inputs
    run_id: int
    project_id: int
    user_id: int
    goal: str

    # screenshots handed in from the browser (consumed then cleared)
    screenshot_in: Optional[bytes]
    screenshot_out: Optional[bytes]

    # planner output for the current step
    step_id: Optional[int]
    step_index: int
    thought: str
    plan: list
    action: Optional[dict]
    expected_result: str
    planner_latency_ms: Optional[int]
    screenshot_in_url: Optional[str]

    # execution / control
    status: str
    message: Optional[str]
    question: Optional[str]
    summary: Optional[str]
    seek_to: Optional[float]
    timeline_changed: bool

    # verifier output
    verify_success: Optional[bool]
    verify_observed: Optional[str]
    verifier_latency_ms: Optional[int]
    screenshot_out_url: Optional[str]


def _save_shot(user_id: int, project_id: int, data: bytes) -> str:
    """Persist a screenshot under storage and return its relative path."""
    pdir = storage.project_dir(user_id, project_id) / "shots"
    pdir.mkdir(parents=True, exist_ok=True)
    path = pdir / f"{uuid.uuid4().hex}.png"
    path.write_bytes(data)
    return storage.rel_path(path)


def _run_context(run: AgentRun) -> tuple[list[str], str | None]:
    """Prior-step summaries + last verification line, for the planner prompt."""
    completed: list[str] = []
    last_verify: str | None = None
    for s in run.steps:
        if s.action:
            completed.append(f"{s.action.get('name')}: {s.expected_result or ''}".strip())
        if s.verify_observed:
            last_verify = s.verify_observed
    return completed, last_verify


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def _writer():
    """Return the active custom stream writer, or a no-op when not streaming."""
    try:
        return get_stream_writer()
    except Exception:  # noqa: BLE001 — not in a streaming context
        return lambda _chunk: None


async def plan_node(state: AgentState) -> dict[str, Any]:
    """Plan one action from the live screenshot; persist an AgentStep row.

    Streams the planner's reasoning live via the custom stream writer so the UI
    can render the thought token-by-token instead of after the call returns.
    """
    db = SessionLocal()
    try:
        run = db.get(AgentRun, state["run_id"])
        project = db.get(Project, state["project_id"])
        n_steps = len(run.steps)

        if n_steps >= settings.max_steps:
            run.status = "failed"
            run.finished_at = utcnow()
            db.commit()
            return {
                "status": "failed",
                "action": None,
                "message": f"Stopped after the {settings.max_steps}-step limit.",
            }

        shot = state.get("screenshot_in") or b""
        shot_rel = _save_shot(state["user_id"], project.id, shot)
        completed, last_verify = _run_context(run)

        write = _writer()
        write({
            "type": "step_start",
            "step_index": n_steps,
            "screenshot_in_url": f"/api/agent/shot?path={shot_rel}",
        })

        output = None
        latency_ms = 0
        async for ev in planner.plan_stream(
            project=project,
            goal=state["goal"],
            screenshot=shot,
            first_call=(n_steps == 0),
            completed_steps=completed,
            last_verify=last_verify,
        ):
            if "thought" in ev:
                write({"type": "thought", "step_index": n_steps, "text": ev["thought"]})
            elif "final" in ev:
                output = ev["final"]
                latency_ms = ev["latency_ms"]

        if output is None:  # stream produced no parseable action
            raise RuntimeError("planner produced no output")

        # JSON mode -> enum names become plain strings (stable across the JSON DB
        # column, the graph checkpoint serializer, and the frontend contract).
        action_dict = output.action.model_dump(mode="json", exclude_none=True)
        step = AgentStep(
            run_id=run.id,
            step_index=n_steps,
            thought=output.thought,
            action=action_dict,
            expected_result=output.expected_result,
            screenshot_in_path=shot_rel,
            planner_latency_ms=latency_ms,
        )
        db.add(step)
        db.flush()
        step_id = step.id
        db.commit()

        return {
            "step_id": step_id,
            "step_index": n_steps,
            "thought": output.thought,
            "plan": output.plan,
            "action": action_dict,
            "expected_result": output.expected_result,
            "planner_latency_ms": latency_ms,
            "screenshot_in_url": f"/api/agent/shot?path={shot_rel}",
            "status": "planned",
            "screenshot_in": None,
        }
    finally:
        db.close()


async def terminal_node(state: AgentState) -> dict[str, Any]:
    """Handle task_complete / task_failed / ask_user (no edit performed)."""
    db = SessionLocal()
    try:
        run = db.get(AgentRun, state["run_id"])
        action = state.get("action") or {}
        name = action.get("name")

        if name == "task_complete":
            run.status = "complete"
            run.finished_at = utcnow()
            db.commit()
            return {"status": "complete", "message": state.get("expected_result") or "Done."}
        if name == "task_failed":
            run.status = "failed"
            run.finished_at = utcnow()
            db.commit()
            return {
                "status": "failed",
                "message": state.get("expected_result") or "I couldn't complete that.",
            }
        # ask_user: leave the run open; the frontend will ask and start a new run.
        return {"status": "ask", "question": action.get("question") or "Could you clarify?"}
    finally:
        db.close()


async def execute_node(state: AgentState) -> dict[str, Any]:
    """Apply a real edit via the ffmpeg engine."""
    db = SessionLocal()
    try:
        project = db.get(Project, state["project_id"])
        step = db.get(AgentStep, state["step_id"])
        action = Action.model_validate(state["action"])
        try:
            result = engine.apply_action(db, project, action)
        except EditError as e:
            if step is not None:
                step.verify_success = False
                step.verify_observed = f"edit rejected: {e}"
            db.commit()
            return {"status": "error", "message": str(e)}

        db.commit()
        return {
            "status": "acted",
            "summary": result.summary,
            "seek_to": result.seek_to,
            "timeline_changed": result.timeline_changed,
        }
    finally:
        db.close()


def verify_gate(state: AgentState) -> dict[str, Any]:
    """Pause until the browser posts a fresh screenshot for verification."""
    shot = interrupt({"need": "verify_screenshot", "step_id": state.get("step_id")})
    return {"screenshot_out": shot}


async def verify_node(state: AgentState) -> dict[str, Any]:
    """Confirm the edit against the fresh screenshot; persist the result."""
    db = SessionLocal()
    try:
        step = db.get(AgentStep, state["step_id"])
        project = db.get(Project, state["project_id"])
        shot = state.get("screenshot_out") or b""
        shot_rel = _save_shot(state["user_id"], project.id, shot)
        if step is not None:
            step.screenshot_out_path = shot_rel

        result, latency_ms = await verifier.verify(
            expected_result=(step.expected_result if step else "") or "",
            screenshot=shot,
        )
        if step is not None:
            step.verify_success = result.success
            step.verify_observed = result.observed
            step.verifier_latency_ms = latency_ms
        db.commit()

        return {
            "status": "verified",
            "verify_success": result.success,
            "verify_observed": result.observed,
            "verifier_latency_ms": latency_ms,
            "screenshot_out_url": f"/api/agent/shot?path={shot_rel}",
            "screenshot_out": None,
        }
    finally:
        db.close()


def loop_gate(state: AgentState) -> dict[str, Any]:
    """Pause until the browser posts the next screenshot for the next plan step."""
    shot = interrupt({"need": "plan_screenshot"})
    return {"screenshot_in": shot}


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route_after_plan(state: AgentState) -> str:
    action = state.get("action")
    if not action:  # step-limit reached (plan_node cleared the action)
        return "end"
    if action.get("name") in TERMINAL_NAMES:
        return "terminal"
    return "execute"


def route_after_execute(state: AgentState) -> str:
    return "end" if state.get("status") == "error" else "verify"


# --------------------------------------------------------------------------- #
# Graph assembly (singleton)
# --------------------------------------------------------------------------- #
def _build():
    builder = StateGraph(AgentState)
    builder.add_node("plan", plan_node)
    builder.add_node("terminal", terminal_node)
    builder.add_node("execute", execute_node)
    builder.add_node("verify_gate", verify_gate)
    builder.add_node("verify", verify_node)
    builder.add_node("loop_gate", loop_gate)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan",
        route_after_plan,
        {"terminal": "terminal", "execute": "execute", "end": END},
    )
    builder.add_edge("terminal", END)
    builder.add_conditional_edges(
        "execute",
        route_after_execute,
        {"verify": "verify_gate", "end": END},
    )
    builder.add_edge("verify_gate", "verify")
    builder.add_edge("verify", "loop_gate")
    builder.add_edge("loop_gate", "plan")

    return builder.compile(checkpointer=MemorySaver())


graph = _build()


def _config(run_id: int) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"run-{run_id}"}}


async def _values(run_id: int) -> dict[str, Any]:
    snapshot = await graph.aget_state(_config(run_id))
    return dict(snapshot.values or {})


async def start_run(
    *, run_id: int, project_id: int, user_id: int, goal: str, screenshot: bytes
) -> dict[str, Any]:
    """Begin a run: plan -> act, pausing before verification. Returns state values."""
    init: AgentState = {
        "run_id": run_id,
        "project_id": project_id,
        "user_id": user_id,
        "goal": goal,
        "step_index": 0,
        "screenshot_in": screenshot,
    }
    await graph.ainvoke(init, _config(run_id))
    return await _values(run_id)


async def resume_run(*, run_id: int, screenshot: bytes) -> dict[str, Any]:
    """Resume a paused run with a screenshot (feeds verify_gate or loop_gate)."""
    await graph.ainvoke(Command(resume=screenshot), _config(run_id))
    return await _values(run_id)


async def _astream(inp: Any, run_id: int):
    """Run the graph, forwarding custom stream-writer events, then a final
    {"type": "__done__", "values": <state>} once it pauses/finishes."""
    async for chunk in graph.astream(inp, _config(run_id), stream_mode="custom"):
        yield chunk
    yield {"type": "__done__", "values": await _values(run_id)}


async def start_run_stream(
    *, run_id: int, project_id: int, user_id: int, goal: str, screenshot: bytes
):
    """Streaming variant of start_run: yields reasoning events, then final state."""
    init: AgentState = {
        "run_id": run_id,
        "project_id": project_id,
        "user_id": user_id,
        "goal": goal,
        "step_index": 0,
        "screenshot_in": screenshot,
    }
    async for ev in _astream(init, run_id):
        yield ev


async def resume_run_stream(*, run_id: int, screenshot: bytes):
    """Streaming variant of resume_run (used for the next plan step)."""
    async for ev in _astream(Command(resume=screenshot), run_id):
        yield ev
