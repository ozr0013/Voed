"""Agent HTTP routes.

Milestone 5 exposes a single planner call: POST /api/agent/plan takes the live
editor screenshot + goal and returns one schema-valid action, saving the exact
screenshot the model looked at as judge-verifiable evidence. The full
plan->act->verify loop + WebSocket streaming arrive in later milestones.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import storage
from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..edits import engine
from ..edits.engine import EditError
from ..models import AgentRun, AgentStep, Project, User, utcnow
from ..models import Clip  # noqa: F401
from . import planner, verifier
from .schemas import ActionName

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
    """One planner call from a real screenshot (no execution yet)."""
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
        "model": settings.model,
        "planner_latency_ms": latency_ms,
        "screenshot_url": f"/api/agent/shot?path={rel}",
        "thought": output.thought,
        "plan": output.plan,
        "action": output.action.model_dump(exclude_none=True),
        "expected_result": output.expected_result,
    }


def _run_context(run: AgentRun) -> tuple[list[str], str | None]:
    """Prior-step summaries + last verification line, for the planner prompt."""
    completed: list[str] = []
    last_verify: str | None = None
    for s in run.steps:
        if s.action:
            completed.append(
                f"{s.action.get('name')}: {s.expected_result or ''}".strip()
            )
        if s.verify_observed:
            last_verify = s.verify_observed
    return completed, last_verify


@router.post("/step")
async def agent_step(
    project_id: int = Form(...),
    goal: str = Form(...),
    screenshot: UploadFile = File(...),
    run_id: int | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """One iteration: plan from the live screenshot, then execute one action.

    The caller (frontend) must re-capture a fresh screenshot afterwards and POST
    it to /verify, then call /step again until status is complete/failed/ask.
    """
    project = _owned(project_id, user, db)
    img = await screenshot.read()
    if not img:
        raise HTTPException(status_code=400, detail="Empty screenshot")

    if run_id is not None:
        run = db.get(AgentRun, run_id)
        if not run or run.project_id != project.id:
            raise HTTPException(status_code=404, detail="Run not found")
        first_call = False
    else:
        run = AgentRun(project_id=project.id, goal=goal, status="running")
        db.add(run)
        db.flush()
        first_call = True

    if len(run.steps) >= settings.max_steps:
        run.status = "failed"
        run.finished_at = utcnow()
        db.commit()
        return {"run_id": run.id, "status": "failed",
                "message": f"Stopped after the {settings.max_steps}-step limit."}

    shot_in = save_screenshot(user.id, project.id, img)
    completed, last_verify = _run_context(run)

    try:
        output, latency_ms, _raw = await planner.plan(
            project=project, goal=goal, screenshot=img,
            first_call=first_call, completed_steps=completed, last_verify=last_verify,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Planner failed: {e}") from e

    step = AgentStep(
        run_id=run.id,
        step_index=len(run.steps),
        thought=output.thought,
        action=output.action.model_dump(exclude_none=True),
        expected_result=output.expected_result,
        screenshot_in_path=shot_in,
        planner_latency_ms=latency_ms,
    )
    db.add(step)
    db.flush()

    name = output.action.name
    base = {
        "run_id": run.id,
        "step_id": step.id,
        "step_index": step.step_index,
        "model": settings.model,
        "thought": output.thought,
        "plan": output.plan,
        "action": output.action.model_dump(exclude_none=True),
        "expected_result": output.expected_result,
        "planner_latency_ms": latency_ms,
        "screenshot_in_url": f"/api/agent/shot?path={shot_in}",
    }

    # terminal actions --------------------------------------------------------
    if name == ActionName.task_complete:
        run.status = "complete"
        run.finished_at = utcnow()
        db.commit()
        return {**base, "status": "complete",
                "message": output.expected_result or "Done."}
    if name == ActionName.task_failed:
        run.status = "failed"
        run.finished_at = utcnow()
        db.commit()
        return {**base, "status": "failed",
                "message": output.expected_result or "I couldn't complete that."}
    if name == ActionName.ask_user:
        db.commit()
        return {**base, "status": "ask",
                "question": output.action.question or "Could you clarify?"}

    # execute a real edit -----------------------------------------------------
    try:
        result = engine.apply_action(db, project, output.action)
    except EditError as e:
        step.verify_success = False
        step.verify_observed = f"edit rejected: {e}"
        db.commit()
        return {**base, "status": "error", "message": str(e)}

    db.commit()
    return {
        **base,
        "status": "acted",
        "summary": result.summary,
        "seek_to": result.seek_to,
        "timeline_changed": result.timeline_changed,
    }


@router.post("/verify")
async def agent_verify(
    run_id: int = Form(...),
    step_id: int = Form(...),
    screenshot: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Verify the just-executed action against a FRESH screenshot of the editor."""
    step = db.get(AgentStep, step_id)
    run = db.get(AgentRun, run_id)
    if not step or not run or step.run_id != run.id:
        raise HTTPException(status_code=404, detail="Step not found")
    project = db.get(Project, run.project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    img = await screenshot.read()
    shot_out = save_screenshot(user.id, project.id, img)
    step.screenshot_out_path = shot_out

    try:
        result, latency_ms = await verifier.verify(
            expected_result=step.expected_result or "", screenshot=img
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Verifier failed: {e}") from e

    step.verify_success = result.success
    step.verify_observed = result.observed
    step.verifier_latency_ms = latency_ms
    db.commit()

    return {
        "success": result.success,
        "observed": result.observed,
        "verifier_latency_ms": latency_ms,
        "screenshot_out_url": f"/api/agent/shot?path={shot_out}",
    }


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
