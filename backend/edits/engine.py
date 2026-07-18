"""Dispatch an agent Action to an ffmpeg operation and update the DB timeline.

Every timeline-changing edit produces a new EditVersion (rendered file) and a
fresh preview proxy, then rewrites the project's Clip rows. Originals are never
touched — `undo` just points the head back one version.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import media, storage
from ..config import settings
from ..models import Clip, EditVersion, Project
from ..agent.schemas import Action, ActionName
from . import operations as ops
from .operations import Segment
from ..agent.planner import state_summary  # noqa: F401 (kept for parity/imports)


class EditError(RuntimeError):
    pass


@dataclass
class ExecResult:
    summary: str
    timeline_changed: bool = False
    version_id: int | None = None
    seek_to: float | None = None


def _segments(project: Project) -> list[Segment]:
    return [Segment(c.src_start_s, c.src_end_s) for c in project.clips]


def _fmt(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def _commit_new_timeline(
    db: Session,
    project: Project,
    segments: list[Segment],
    action: Action,
    label: str,
    rotate_angle: int | None = None,
    crop_aspect: str | None = None,
) -> EditVersion:
    if not segments or ops.total_duration(segments) < ops.EPS:
        raise EditError("That edit would empty the timeline.")

    original = storage.abs_path(project.original_path)
    pdir = storage.project_dir(project.user_id, project.id)
    next_idx = (max((v.version_index for v in project.versions), default=0)) + 1

    version_file = pdir / "versions" / f"v{next_idx}.mp4"
    ops.render_segments(
        original,
        segments,
        version_file,
        muted=project.muted_ranges or [],
        rotate_angle=rotate_angle,
        aspect=crop_aspect,
    )

    # preview proxy (<=720p) of the new timeline
    proxy = pdir / f"proxy_v{next_idx}.mp4"
    try:
        media.make_proxy(version_file, proxy)
        project.proxy_path = storage.rel_path(proxy)
    except media.MediaError:
        project.proxy_path = storage.rel_path(version_file)

    version = EditVersion(
        project_id=project.id,
        parent_id=project.head_version_id,
        version_index=next_idx,
        file_path=storage.rel_path(version_file),
        duration_s=ops.total_duration(segments),
        label=label,
        layout=[{"src_start_s": s.src_start, "src_end_s": s.src_end} for s in segments],
        action=action.model_dump(exclude_none=True),
    )
    db.add(version)
    db.flush()

    # rewrite clip rows to the new segment list, preserving captions by overlap
    old_caps = [(c.src_start_s, c.src_end_s, c.caption_text) for c in project.clips]
    for c in list(project.clips):
        db.delete(c)
    db.flush()
    for i, seg in enumerate(segments):
        caption = next(
            (
                cap
                for (cs, ce, cap) in old_caps
                if cap and not (ce <= seg.src_start or cs >= seg.src_end)
            ),
            None,
        )
        db.add(
            Clip(
                project_id=project.id,
                order_index=i,
                src_start_s=seg.src_start,
                src_end_s=seg.src_end,
                caption_text=caption,
            )
        )
    project.head_version_id = version.id
    db.commit()
    db.refresh(project)
    return version


def _clamp_range(project: Project, action: Action, what: str) -> tuple[float, float]:
    """Validate + clamp an action's [start_s, end_s] against the timeline length."""
    dur = ops.total_duration(_segments(project))
    a = max(0.0, action.start_s or 0.0)
    b = min(dur, action.end_s if action.end_s is not None else dur)
    if b <= a:
        raise EditError(f"{what} needs end_s greater than start_s.")
    return a, b


# --------------------------------------------------------------------------- #
# Executors — one per capability. Add a new edit by writing a function here and
# registering it below; the agent action schema + skill doc do the rest. This is
# what lets editing grow without a new branch in a giant if/elif for every verb.
# --------------------------------------------------------------------------- #
def _exec_cut_range(db: Session, project: Project, action: Action) -> ExecResult:
    a, b = _clamp_range(project, action, "cut_range")
    new = ops.remove_interval(_segments(project), a, b)
    v = _commit_new_timeline(db, project, new, action, f"cut {_fmt(a)}–{_fmt(b)}")
    return ExecResult(
        summary=f"Removed {_fmt(a)}–{_fmt(b)} ({b - a:.1f}s); "
        f"timeline is now {ops.total_duration(new):.1f}s.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_trim(db: Session, project: Project, action: Action) -> ExecResult:
    a, b = _clamp_range(project, action, "trim")
    new = ops.keep_interval(_segments(project), a, b)
    v = _commit_new_timeline(db, project, new, action, f"trim to {_fmt(a)}–{_fmt(b)}")
    return ExecResult(
        summary=f"Trimmed to {_fmt(a)}–{_fmt(b)}; "
        f"timeline is now {ops.total_duration(new):.1f}s.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_mute_range(db: Session, project: Project, action: Action) -> ExecResult:
    a, b = _clamp_range(project, action, "mute_range")
    segs = _segments(project)
    # Record the mute in SOURCE time (survives later cuts/trims), then re-render
    # the SAME timeline with the audio silenced — length is unchanged.
    src = [{"start": s, "end": e} for (s, e) in ops.timeline_to_source(segs, a, b)]
    project.muted_ranges = ops.merge_intervals(list(project.muted_ranges or []) + src)
    v = _commit_new_timeline(db, project, segs, action, f"mute {_fmt(a)}–{_fmt(b)}")
    return ExecResult(
        summary=f"Muted audio {_fmt(a)}–{_fmt(b)}; timeline length unchanged.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_crop(db: Session, project: Project, action: Action) -> ExecResult:
    if action.aspect is None:
        raise EditError("crop needs an aspect ratio.")
    segs = _segments(project)
    aspect = action.aspect.value if hasattr(action.aspect, "value") else action.aspect
    v = _commit_new_timeline(
        db,
        project,
        segs,
        action,
        f"crop {aspect}",
        crop_aspect=aspect,
    )
    return ExecResult(
        summary=f"Cropped the frame to {aspect} aspect.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_rotate(db: Session, project: Project, action: Action) -> ExecResult:
    if action.angle is None:
        raise EditError("rotate needs an angle.")
    if action.angle not in (90, 180, 270):
        raise EditError("rotate angle must be 90, 180, or 270.")
    segs = _segments(project)
    v = _commit_new_timeline(
        db,
        project,
        segs,
        action,
        f"rotate {action.angle}°",
        rotate_angle=action.angle,
    )
    return ExecResult(
        summary=f"Rotated the frame by {action.angle}°.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_seek_preview(db: Session, project: Project, action: Action) -> ExecResult:
    return ExecResult(
        summary=f"Moved the playhead to {_fmt(action.start_s or 0.0)}.",
        timeline_changed=False,
        seek_to=action.start_s or 0.0,
    )


_EXECUTORS = {
    ActionName.cut_range: _exec_cut_range,
    ActionName.trim: _exec_trim,
    ActionName.mute_range: _exec_mute_range,
    ActionName.crop: _exec_crop,
    ActionName.rotate: _exec_rotate,
    ActionName.seek_preview: _exec_seek_preview,
}


def apply_action(db: Session, project: Project, action: Action) -> ExecResult:
    """Execute a single timeline action. Raises EditError on invalid/unsupported edits."""
    handler = _EXECUTORS.get(action.name)
    if handler is None:
        raise EditError(f"Action '{action.name.value}' is not implemented yet.")
    return handler(db, project, action)
