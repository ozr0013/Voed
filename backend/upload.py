"""Chunked upload + project CRUD + media serving.

Upload protocol (kept simple and real):
  POST /api/projects/upload/init      -> create project, return {project_id}
  POST /api/projects/upload/chunk     -> append one binary chunk (sequential)
  POST /api/projects/upload/complete  -> validate (ffprobe), extract assets,
                                         build initial timeline, mark ready
Processing (probe, thumbnail, waveform, proxy) runs in a background thread so the
request returns immediately; the dashboard polls project status.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import asr, media, storage
from .auth import current_user
from .db import SessionLocal, get_db
from .models import Clip, EditVersion, Project, User
from .schemas_api import ProjectDetail, ProjectSummary

router = APIRouter(prefix="/api/projects", tags=["projects"])

_ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


# --------------------------------------------------------------------------- #
# Background processing
# --------------------------------------------------------------------------- #
def _process_upload(project_id: int, user_id: int, tmp_path: Path, ext: str) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None:
            return
        project.status = "processing"
        db.commit()

        pdir = storage.project_dir(user_id, project_id)
        original = pdir / f"original{ext}"
        tmp_path.replace(original)

        # 1. validate + probe
        info = media.ffprobe_info(original)
        project.original_path = storage.rel_path(original)
        project.duration_s = info.duration_s
        project.width = info.width
        project.height = info.height
        project.fps = info.fps

        # 2. thumbnail
        thumb = pdir / "thumb.jpg"
        try:
            media.make_thumbnail(original, thumb, at_s=min(1.0, info.duration_s / 2))
            project.thumb_path = storage.rel_path(thumb)
        except media.MediaError:
            pass

        # 3. waveform peaks for the timeline
        project.waveform = media.waveform_peaks(original, buckets=400)

        # 4. initial timeline: one clip spanning the whole video + version v0
        clip = Clip(
            project_id=project.id, order_index=0,
            src_start_s=0.0, src_end_s=info.duration_s,
        )
        db.add(clip)
        v0 = EditVersion(
            project_id=project.id, version_index=0,
            file_path=project.original_path, duration_s=info.duration_s,
            label="original", layout=[{"src_start_s": 0.0, "src_end_s": info.duration_s}],
        )
        db.add(v0)
        db.flush()
        project.head_version_id = v0.id

        # 5. 720p proxy for smooth preview
        proxy = pdir / "proxy.mp4"
        try:
            media.make_proxy(original, proxy)
            project.proxy_path = storage.rel_path(proxy)
        except media.MediaError:
            project.proxy_path = None  # preview falls back to original

        project.status = "ready"
        # Mark transcription in-flight, then run it in its own thread so the video
        # is immediately usable (time-based edits) while speech is transcribed.
        project.transcript_status = "processing"
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        project = db.get(Project, project_id)
        if project:
            project.status = "error"
            project.error = str(e)[:500]
            db.commit()
        db.close()
        return
    finally:
        db.close()

    threading.Thread(
        target=_transcribe_project, args=(project_id,), daemon=True
    ).start()


def _transcribe_project(project_id: int) -> None:
    """Word-level transcription of a project's audio via faster-whisper. Populates
    project.transcript (list of {start,end,word}) and flips transcript_status."""
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None or not project.original_path:
            return
        project.transcript_status = "processing"
        db.commit()
        original = storage.abs_path(project.original_path)
        tr = asr.transcribe_path(original, word_timestamps=True)
        # cast to native floats — faster-whisper returns numpy floats, which the
        # JSON column can't serialize.
        project.transcript = [
            {"start": float(w.start), "end": float(w.end), "word": w.word}
            for w in tr.words
        ]
        project.transcript_status = "ready"
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        project = db.get(Project, project_id)
        if project:
            project.transcript_status = "error"
            db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Upload endpoints
# --------------------------------------------------------------------------- #
@router.post("/upload/init")
def upload_init(
    name: str = Form(...),
    filename: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported format '{ext}'. Try MP4, MOV, MKV, or WEBM.",
        )
    project = Project(user_id=user.id, name=name.strip() or "Untitled", status="uploading")
    db.add(project)
    db.commit()
    db.refresh(project)
    # start a fresh temp part file
    part = storage.tmp_dir() / f"{project.id}{ext}.part"
    part.write_bytes(b"")
    return {"project_id": project.id, "ext": ext}


@router.post("/upload/chunk")
async def upload_chunk(
    project_id: int = Form(...),
    ext: str = Form(...),
    chunk: UploadFile = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    part = storage.tmp_dir() / f"{project_id}{ext}.part"
    data = await chunk.read()
    with open(part, "ab") as f:
        f.write(data)
    return {"ok": True, "received": part.stat().st_size}


@router.post("/upload/complete", response_model=ProjectSummary)
def upload_complete(
    project_id: int = Form(...),
    ext: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProjectSummary:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    part = storage.tmp_dir() / f"{project_id}{ext}.part"
    if not part.exists() or part.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="No upload data received")

    project.status = "processing"
    db.commit()
    threading.Thread(
        target=_process_upload,
        args=(project.id, user.id, part, ext),
        daemon=True,
    ).start()
    return ProjectSummary.of(project)


# --------------------------------------------------------------------------- #
# Project CRUD
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ProjectSummary])
def list_projects(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[ProjectSummary]:
    rows = db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
    ).all()
    return [ProjectSummary.of(p) for p in rows]


def _owned(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ProjectDetail:
    return ProjectDetail.of(_owned(project_id, user, db))


@router.delete("/{project_id}")
def delete_project(
    project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    project = _owned(project_id, user, db)
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/transcribe")
def transcribe(
    project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """(Re)start word-level transcription in the background. Idempotent: no-op if
    already transcribing or done. Lets pending/failed videos self-heal on open."""
    project = _owned(project_id, user, db)
    if project.transcript_status in ("processing", "ready"):
        return {"status": project.transcript_status}
    project.transcript_status = "processing"
    db.commit()
    threading.Thread(
        target=_transcribe_project, args=(project.id,), daemon=True
    ).start()
    return {"status": "processing"}


# --------------------------------------------------------------------------- #
# Media serving (range-capable via FileResponse)
# --------------------------------------------------------------------------- #
@router.get("/{project_id}/media/{asset}")
def get_media(
    project_id: int,
    asset: str,
    request: Request,  # noqa: ARG001 — FileResponse handles Range from headers
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    project = _owned(project_id, user, db)
    rel: str | None
    if asset == "thumb":
        rel = project.thumb_path
    elif asset == "preview":
        rel = project.proxy_path or project.original_path
    elif asset == "original":
        rel = project.original_path
    else:
        raise HTTPException(status_code=404, detail="Unknown asset")
    if not rel:
        raise HTTPException(status_code=404, detail="Asset not ready")
    path = storage.abs_path(rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path)


# --------------------------------------------------------------------------- #
# Export — hand off the current edited render as a downloadable file.
# Serves the head EditVersion (full-res edited timeline); falls back to the
# untouched original if no edits have been applied yet. Everything stays local.
# --------------------------------------------------------------------------- #
@router.get("/{project_id}/export")
def export_project(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    project = _owned(project_id, user, db)
    rel: str | None = None
    if project.head_version_id:
        head = db.get(EditVersion, project.head_version_id)
        rel = head.file_path if head else None
    rel = rel or project.original_path
    if not rel:
        raise HTTPException(status_code=404, detail="Nothing to export yet")
    path = storage.abs_path(rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")

    safe = re.sub(r"[^\w.-]+", "_", project.name).strip("_") or f"project_{project.id}"
    return FileResponse(path, media_type="video/mp4", filename=f"{safe}.mp4")
