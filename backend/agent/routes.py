"""Agent HTTP routes.

The plan -> act -> verify loop is orchestrated by LangGraph (see graph.py). Each
run is one checkpointed graph thread that pauses (`interrupt`) whenever it needs a
fresh screenshot of the live editor, which the browser supplies:

  POST /api/agent/step    start a run (or continue after a verify): plan + act,
                          then pause before verification.
  POST /api/agent/verify  resume the paused run with a fresh screenshot: verify,
                          then pause before the next plan step.

Gemma (via Ollama) remains the model for both planning and verification — the
graph only sequences the work. POST /api/agent/plan is a stateless one-shot
planner call kept for demos/debugging.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import storage
from ..auth import current_user
from ..model_state import get_active_model
from ..db import get_db
from ..models import AgentRun, Project, User
from . import graph as agent_graph
from . import planner

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _owned(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def save_screenshot(user_id: int, project_id: int, data: bytes) -> str:
    """Persist a screenshot under storage and return its relative path."""
    pdir = storage.project_dir(user_id, project_id) / "shots"
    pdir.mkdir(parents=True, exist_ok=True)
    path = pdir / f"{uuid.uuid4().hex}.png"
    path.write_bytes(data)
    return storage.rel_path(path)


@router.post("/plan")
async def plan_once(
    project_id: int = Form(...),
    goal: str = Form(...),
    screenshot: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """One planner call from a real screenshot (no execution). For demos/debugging."""
    project = _owned(project_id, user, db)
    img = await screenshot.read()
    if not img:
        raise HTTPException(status_code=400, detail="Empty screenshot")

    rel = save_screenshot(user.id, project.id, img)
    try:
        output, latency_ms, _raw = await planner.plan(
            project=project, goal=goal, screenshot=img, first_call=True
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Planner failed: {e}") from e

    return {
        "model": get_active_model(),
        "planner_latency_ms": latency_ms,
        "screenshot_url": f"/api/agent/shot?path={rel}",
        "thought": output.thought,
        "plan": output.plan,
        "action": output.action.model_dump(exclude_none=True),
        "expected_result": output.expected_result,
    }


def _step_response(run_id: int, vals: dict) -> dict:
    """Shape a graph state snapshot into the /step response contract."""
    resp = {
        "run_id": run_id,
        "step_id": vals.get("step_id"),
        "step_index": vals.get("step_index"),
        "model": get_active_model(),
        "thought": vals.get("thought", ""),
        "plan": vals.get("plan", []),
        "action": vals.get("action") or {},
        "expected_result": vals.get("expected_result", ""),
        "planner_latency_ms": vals.get("planner_latency_ms"),
        "screenshot_in_url": vals.get("screenshot_in_url"),
    }
    status = vals.get("status")
    if status == "acted":
        resp.update(
            status="acted",
            summary=vals.get("summary"),
            seek_to=vals.get("seek_to"),
            timeline_changed=vals.get("timeline_changed", False),
        )
    elif status == "complete":
        resp.update(status="complete", message=vals.get("message") or "Done.")
    elif status == "failed":
        resp.update(status="failed", message=vals.get("message") or "I couldn't complete that.")
    elif status == "ask":
        resp.update(status="ask", question=vals.get("question") or "Could you clarify?")
    elif status == "error":
        resp.update(status="error", message=vals.get("message") or "That edit failed.")
    else:
        resp.update(status=status or "acted")
    return resp


@router.post("/step")
async def agent_step(
    project_id: int = Form(...),
    goal: str = Form(...),
    screenshot: UploadFile = File(...),
    run_id: int | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """One iteration: plan from the live screenshot, then execute one action.

    Returns a Server-Sent Events stream so the planner's reasoning renders live:
      data: {"type":"step_start","step_index":n,"screenshot_in_url":...}
      data: {"type":"thought","step_index":n,"text":"<reasoning so far>"}   (repeated)
      data: {"type":"done", ...full step result... }

    Starts a new LangGraph run when `run_id` is absent, otherwise resumes the
    existing run (paused waiting for the next plan screenshot). The graph pauses
    again before verification; the frontend posts a fresh screenshot to /verify,
    then calls /step again until the run is terminal.
    """
    project = _owned(project_id, user, db)
    img = await screenshot.read()
    if not img:
        raise HTTPException(status_code=400, detail="Empty screenshot")

    if run_id is None:
        run = AgentRun(project_id=project.id, goal=goal, status="running")
        db.add(run)
        db.commit()  # persist so the graph's own session can load it
        run_id = run.id
        events = agent_graph.start_run_stream(
            run_id=run_id,
            project_id=project.id,
            user_id=user.id,
            goal=goal,
            screenshot=img,
        )
    else:
        run = db.get(AgentRun, run_id)
        if not run or run.project_id != project.id:
            raise HTTPException(status_code=404, detail="Run not found")
        events = agent_graph.resume_run_stream(run_id=run_id, screenshot=img)

    async def sse():
        try:
            async for ev in events:
                if ev.get("type") == "__done__":
                    payload = _step_response(run_id, ev["values"])
                    payload["type"] = "done"
                    yield f"data: {json.dumps(payload)}\n\n"
                else:
                    yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/verify")
async def agent_verify(
    run_id: int = Form(...),
    step_id: int = Form(...),  # kept for API compatibility; the graph tracks the step
    screenshot: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Verify the just-executed action against a FRESH screenshot of the editor."""
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    project = db.get(Project, run.project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    img = await screenshot.read()
    if not img:
        raise HTTPException(status_code=400, detail="Empty screenshot")

    try:
        vals = await agent_graph.resume_run(run_id=run_id, screenshot=img)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Verifier failed: {e}") from e

    return {
        "success": vals.get("verify_success"),
        "observed": vals.get("verify_observed", ""),
        "verifier_latency_ms": vals.get("verifier_latency_ms"),
        "screenshot_out_url": vals.get("screenshot_out_url"),
    }


def _label_for(action: dict | None) -> str:
    """Human label for a persisted step's action (mirrors the frontend)."""
    a = action or {}
    name = a.get("name")
    if name == "cut_range":
        return f"Cut {a.get('start_s', 0)}s–{a.get('end_s', '?')}s"
    if name == "trim":
        return f"Trim to {a.get('start_s', 0)}s–{a.get('end_s', '?')}s"
    if name == "mute_range":
        return f"Mute {a.get('start_s', 0)}s–{a.get('end_s', '?')}s"
    return (name or "step").replace("_", " ")


def _shot_url(path: str | None) -> str | None:
    return f"/api/agent/shot?path={path}" if path else None


def _step_view(s) -> dict:
    status = "done" if s.verify_success is True else "failed" if s.verify_success is False else "done"
    return {
        "index": s.step_index,
        "label": _label_for(s.action),
        "status": status,
        "thought": s.thought,
        "expectedResult": s.expected_result,
        "observed": s.verify_observed,
        "shotIn": _shot_url(s.screenshot_in_path),
        "shotOut": _shot_url(s.screenshot_out_path),
    }


@router.get("/runs")
def list_runs(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """All (recent) runs + their steps for a project, oldest→newest, so the Editor
    can restore the FULL agent conversation — each command stacks in the panel
    instead of replacing the last one."""
    project = _owned(project_id, user, db)
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.project_id == project.id)
        .order_by(AgentRun.id.desc())
        .limit(40)
        .all()
    )
    out = [
        {
            "id": run.id,
            "goal": run.goal,
            "status": run.status,
            "steps": [_step_view(s) for s in run.steps],
        }
        for run in reversed(runs)
        if run.steps  # skip empty runs (nothing to show)
    ]
    return {"runs": out}


@router.get("/shot")
def get_shot(
    path: str, user: User = Depends(current_user)
) -> FileResponse:
    """Serve a stored screenshot, scoped to the requesting user's storage."""
    # rel paths look like "<user_id>/<project_id>/shots/<name>.png"
    if not path.startswith(f"{user.id}/") or ".." in path:
        raise HTTPException(status_code=403, detail="Forbidden")
    abs_p = storage.abs_path(path)
    if not abs_p.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(abs_p)
