"""Pydantic response models for the HTTP API (distinct from the agent action
schema in agent/schemas.py)."""
from __future__ import annotations

from pydantic import BaseModel

from .models import Clip, Project


class ClipOut(BaseModel):
    id: int
    order_index: int
    src_start_s: float
    src_end_s: float
    duration_s: float
    caption_text: str | None = None
    muted: bool = False  # audio silenced somewhere in this clip's source range

    @classmethod
    def of(cls, c: Clip, muted: bool = False) -> "ClipOut":
        return cls(
            id=c.id,
            order_index=c.order_index,
            src_start_s=c.src_start_s,
            src_end_s=c.src_end_s,
            duration_s=c.duration_s,
            caption_text=c.caption_text,
            muted=muted,
        )


class ProjectSummary(BaseModel):
    id: int
    name: str
    status: str
    error: str | None = None
    duration_s: float           # source video length (fixed)
    timeline_duration_s: float  # current edited timeline length
    width: int
    height: int
    thumb_url: str | None = None
    transcript_status: str
    updated_at: str

    @classmethod
    def of(cls, p: Project) -> "ProjectSummary":
        return cls(
            id=p.id,
            name=p.name,
            status=p.status,
            error=p.error,
            duration_s=p.duration_s,
            timeline_duration_s=p.timeline_duration_s,
            width=p.width,
            height=p.height,
            thumb_url=f"/api/projects/{p.id}/media/thumb" if p.thumb_path else None,
            transcript_status=p.transcript_status,
            updated_at=p.updated_at.isoformat(),
        )


class ProjectDetail(ProjectSummary):
    fps: float
    waveform: list[float] | None = None
    clips: list[ClipOut] = []
    muted_ranges: list[dict] = []  # source-time [{"start","end"}] silenced regions
    preview_url: str | None = None

    @classmethod
    def of(cls, p: Project) -> "ProjectDetail":  # type: ignore[override]
        base = ProjectSummary.of(p).model_dump()
        muted = p.muted_ranges or []

        def _is_muted(c: Clip) -> bool:
            return any(
                not (m["end"] <= c.src_start_s or m["start"] >= c.src_end_s) for m in muted
            )

        base.update(
            fps=p.fps,
            waveform=p.waveform,
            clips=[ClipOut.of(c, _is_muted(c)).model_dump() for c in p.clips],
            muted_ranges=muted,
            preview_url=(
                f"/api/projects/{p.id}/media/preview"
                if (p.proxy_path or p.original_path)
                else None
            ),
        )
        return cls(**base)
