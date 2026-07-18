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
from ..models import Project, User
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
