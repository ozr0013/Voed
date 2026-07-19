"""Dispatch an agent Action to an ffmpeg operation and update the DB timeline.

Every timeline-changing edit produces a new EditVersion (rendered file) and a
fresh preview proxy, then rewrites the project's Clip rows. Originals are never
touched — `undo` just points the head back one version.

Two kinds of edits share one commit path:
  * structural   — change the SEGMENT list (cut/trim/split/reorder/delete/silence)
  * effect        — append to project.effects, re-render the SAME segments
                    (colour, speed, fades, volume, captions, geometry, …)
Add a new skill by writing one `_exec_*` and registering it in `_EXECUTORS`; the
action schema + skills/editing.md doc do the rest.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import media, storage
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


def _make_proxy(project: Project, version_file, pdir, idx: int) -> None:
    proxy = pdir / f"proxy_v{idx}.mp4"
    try:
        media.make_proxy(version_file, proxy)
        project.proxy_path = storage.rel_path(proxy)
    except media.MediaError:
        project.proxy_path = storage.rel_path(version_file)


def _commit_new_timeline(
    db: Session, project: Project, segments: list[Segment], action: Action, label: str
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
        effects=project.effects or [],
    )
    _make_proxy(project, version_file, pdir, next_idx)

    version = EditVersion(
        project_id=project.id,
        parent_id=project.head_version_id,
        version_index=next_idx,
        file_path=storage.rel_path(version_file),
        duration_s=ops.total_duration(segments),
        label=label,
        layout=[{"src_start_s": s.src_start, "src_end_s": s.src_end} for s in segments],
        action=action.model_dump(exclude_none=True),
        muted_snapshot=list(project.muted_ranges or []),
        effects_snapshot=list(project.effects or []),
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
    """Validate + clamp an action's [start_s, end_s] against the timeline length.

    The end of the range is resolved from `end_s` if given, otherwise from
    `duration_s` (start_s + duration_s) — the model often phrases "the first 10
    seconds" as start_s=0 + duration_s=10. If NEITHER is provided we refuse
    rather than silently defaulting to the whole timeline (which used to turn
    "mute the first 10s" into "mute the entire video")."""
    dur = ops.total_duration(_segments(project))
    a = max(0.0, action.start_s or 0.0)
    if action.end_s is not None:
        b = action.end_s
    elif action.duration_s is not None:
        b = a + action.duration_s
    else:
        raise EditError(
            f"{what} needs an end_s (or duration_s). Refusing to apply it to the "
            "whole timeline."
        )
    b = min(dur, b)
    if b <= a:
        raise EditError(f"{what} needs end_s greater than start_s.")
    return a, b


def _set_effect(project: Project, effect: dict, replace: tuple[str, ...]) -> None:
    """Append `effect`, dropping any existing effects whose type is in `replace`
    (so colour/speed/geometry toggles stay singletons and are idempotent)."""
    kept = [e for e in (project.effects or []) if e.get("type") not in replace]
    kept.append(effect)
    project.effects = kept


def _num(v, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Structural executors (change the segment list)
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
    src = [{"start": s, "end": e} for (s, e) in ops.timeline_to_source(segs, a, b)]
    project.muted_ranges = ops.merge_intervals(list(project.muted_ranges or []) + src)
    v = _commit_new_timeline(db, project, segs, action, f"mute {_fmt(a)}–{_fmt(b)}")
    return ExecResult(
        summary=f"Muted audio {_fmt(a)}–{_fmt(b)}; timeline length unchanged.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_split(db: Session, project: Project, action: Action) -> ExecResult:
    dur = ops.total_duration(_segments(project))
    p = max(ops.EPS, min(dur - ops.EPS, action.start_s or 0.0))
    out: list[Segment] = []
    t = 0.0
    did = False
    for seg in _segments(project):
        s0, s1 = t, t + seg.duration
        if s0 < p < s1 and not did:
            mid = seg.src_start + (p - s0)
            out.append(Segment(seg.src_start, mid))
            out.append(Segment(mid, seg.src_end))
            did = True
        else:
            out.append(seg)
        t = s1
    if not did:
        raise EditError("Nothing to split at that point.")
    v = _commit_new_timeline(db, project, out, action, f"split at {_fmt(p)}")
    return ExecResult(
        summary=f"Split the clip at {_fmt(p)}; there are now {len(out)} clips.",
        timeline_changed=True,
        version_id=v.id,
        seek_to=p,
    )


def _find_clip_index(project: Project, clip_id: str | None) -> int:
    if clip_id is None:
        raise EditError("This action needs a clip_id.")
    try:
        cid = int(clip_id)
    except (TypeError, ValueError):
        cid = None
    for i, c in enumerate(project.clips):
        if c.id == cid or str(c.id) == str(clip_id):
            return i
    raise EditError(f"No clip with id {clip_id}.")


def _exec_delete_clip(db: Session, project: Project, action: Action) -> ExecResult:
    idx = _find_clip_index(project, action.clip_id)
    segs = _segments(project)
    if len(segs) <= 1:
        raise EditError("Can't delete the only clip.")
    removed = segs.pop(idx)
    v = _commit_new_timeline(db, project, segs, action, f"delete clip {idx}")
    return ExecResult(
        summary=f"Deleted clip {idx} ({removed.duration:.1f}s); "
        f"{len(segs)} clips remain.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_reorder_clips(db: Session, project: Project, action: Action) -> ExecResult:
    idx = _find_clip_index(project, action.clip_id)
    segs = _segments(project)
    pos = action.position if action.position is not None else 0
    pos = max(0, min(len(segs) - 1, pos))
    seg = segs.pop(idx)
    segs.insert(pos, seg)
    v = _commit_new_timeline(db, project, segs, action, f"move clip {idx}->{pos}")
    return ExecResult(
        summary=f"Moved clip {idx} to position {pos}.",
        timeline_changed=True,
        version_id=v.id,
    )


def _exec_remove_silence(db: Session, project: Project, action: Action) -> ExecResult:
    silences = ops.detect_silences(project.waveform, project.duration_s)
    if not silences:
        raise EditError("No clear silent gaps were detected.")
    before = ops.total_duration(_segments(project))
    new = ops.subtract_from_segments(_segments(project), silences)
    if not new or ops.total_duration(new) < ops.EPS:
        raise EditError("Removing silence would empty the timeline.")
    v = _commit_new_timeline(db, project, new, action, "remove silence")
    saved = before - ops.total_duration(new)
    return ExecResult(
        summary=f"Removed {len(silences)} silent gap(s), {saved:.1f}s shorter; "
        f"timeline is now {ops.total_duration(new):.1f}s.",
        timeline_changed=True,
        version_id=v.id,
    )


# --------------------------------------------------------------------------- #
# Effect executors (append to project.effects, re-render same segments)
# --------------------------------------------------------------------------- #
def _commit_effect(
    db: Session, project: Project, action: Action, label: str, summary: str
) -> ExecResult:
    v = _commit_new_timeline(db, project, _segments(project), action, label)
    return ExecResult(summary=summary, timeline_changed=True, version_id=v.id)


def _exec_change_speed(db, project, action):
    factor = _num(action.factor, 2.0)
    if factor <= 0:
        raise EditError("Speed factor must be positive.")
    _set_effect(project, {"type": "speed", "factor": factor}, ("speed",))
    verb = "Sped up" if factor > 1 else "Slowed"
    return _commit_effect(db, project, action, f"speed x{factor:g}",
                          f"{verb} the video to {factor:g}× speed.")


def _exec_change_volume(db, project, action):
    factor = _num(action.factor, 1.5)
    _set_effect(project, {"type": "volume", "factor": factor}, ("volume", "silence_all"))
    return _commit_effect(db, project, action, f"volume x{factor:g}",
                          f"Set the audio volume to {factor:g}×.")


def _exec_silence_audio(db, project, action):
    _set_effect(project, {"type": "silence_all"}, ("silence_all", "volume"))
    return _commit_effect(db, project, action, "silence audio",
                          "Silenced the audio for the whole video.")


def _exec_fade_in(db, project, action):
    d = _num(action.duration_s, 1.0)
    _set_effect(project, {"type": "fade_in", "duration_s": d}, ("fade_in",))
    return _commit_effect(db, project, action, f"fade in {d:g}s",
                          f"Added a {d:g}s fade-in from black at the start.")


def _exec_fade_out(db, project, action):
    d = _num(action.duration_s, 1.0)
    _set_effect(project, {"type": "fade_out", "duration_s": d}, ("fade_out",))
    return _commit_effect(db, project, action, f"fade out {d:g}s",
                          f"Added a {d:g}s fade-out to black at the end.")


def _exec_grayscale(db, project, action):
    _set_effect(project, {"type": "grayscale"}, ("grayscale", "sepia"))
    return _commit_effect(db, project, action, "grayscale",
                          "Converted the video to black & white.")


def _exec_sepia(db, project, action):
    _set_effect(project, {"type": "sepia"}, ("sepia", "grayscale"))
    return _commit_effect(db, project, action, "sepia", "Applied a sepia tone.")


def _exec_invert(db, project, action):
    _set_effect(project, {"type": "invert"}, ("invert",))
    return _commit_effect(db, project, action, "invert", "Inverted the colours.")


def _exec_vignette(db, project, action):
    _set_effect(project, {"type": "vignette"}, ("vignette",))
    return _commit_effect(db, project, action, "vignette", "Added a vignette.")


def _exec_sharpen(db, project, action):
    _set_effect(project, {"type": "sharpen"}, ("sharpen",))
    return _commit_effect(db, project, action, "sharpen", "Sharpened the video.")


def _exec_blur(db, project, action):
    amt = _num(action.amount, 8.0)
    _set_effect(project, {"type": "blur", "value": amt}, ("blur",))
    return _commit_effect(db, project, action, f"blur {amt:g}",
                          f"Blurred the video (strength {amt:g}).")


def _exec_adjust_color(db, project, action):
    applied = []
    if action.brightness is not None:
        _set_effect(project, {"type": "brightness", "value": float(action.brightness)},
                    ("brightness",))
        applied.append(f"brightness {action.brightness:+g}")
    if action.contrast is not None:
        _set_effect(project, {"type": "contrast", "value": float(action.contrast)},
                    ("contrast",))
        applied.append(f"contrast {action.contrast:g}")
    if action.saturation is not None:
        _set_effect(project, {"type": "saturation", "value": float(action.saturation)},
                    ("saturation",))
        applied.append(f"saturation {action.saturation:g}")
    if not applied:
        raise EditError("adjust_color needs brightness, contrast, or saturation.")
    return _commit_effect(db, project, action, "adjust colour",
                          "Adjusted " + ", ".join(applied) + ".")


def _exec_rotate(db, project, action):
    # `angle` is the preferred field (matches the frontend); `degrees` is an alias.
    deg = int(action.angle or action.degrees or 90) % 360
    if deg not in (90, 180, 270):
        raise EditError("Rotation must be 90, 180, or 270 degrees.")
    _set_effect(project, {"type": "rotate", "degrees": deg}, ("rotate",))
    return _commit_effect(db, project, action, f"rotate {deg}",
                          f"Rotated the video {deg}°.")


def _exec_flip(db, project, action):
    direction = (action.direction or "horizontal").lower()
    etype = "vflip" if direction.startswith("v") else "hflip"
    _set_effect(project, {"type": etype}, (etype,))
    return _commit_effect(db, project, action, etype,
                          f"Flipped the video {('vertically' if etype=='vflip' else 'horizontally')}.")


def _aspect_crop_box(width: int, height: int, aspect: str) -> tuple[int, int, int, int]:
    """Centre-crop box (w, h, x, y) for a semantic aspect ratio. Dimensions are
    forced even (yuv420p / libx264 requires it)."""
    ow, oh = width, height
    if aspect == "square":
        w = h = min(ow, oh)
    elif aspect == "portrait":
        target = 9.0 / 16.0
        if ow / oh > target:
            w, h = int(round(oh * target)), oh
        else:
            w, h = ow, int(round(ow / target))
    elif aspect == "landscape":
        target = 16.0 / 9.0
        if ow / oh < target:
            w, h = ow, int(round(ow / target))
        else:
            w, h = int(round(oh * target)), oh
    else:
        raise EditError("Crop aspect must be square, portrait, or landscape.")
    w -= w % 2
    h -= h % 2
    return w, h, max(0, (ow - w) // 2), max(0, (oh - h) // 2)


def _exec_crop(db, project, action):
    aspect = action.aspect.value if hasattr(action.aspect, "value") else action.aspect
    if aspect:
        if not (project.width and project.height):
            raise EditError("Don't know the video size to crop by aspect.")
        w, h, x, y = _aspect_crop_box(project.width, project.height, aspect)
        eff = {"type": "crop", "w": w, "h": h, "x": x, "y": y}
        label, summary = f"crop {aspect}", f"Cropped the frame to {aspect} aspect."
    elif action.w is not None and action.h is not None:
        w, h = int(action.w) - int(action.w) % 2, int(action.h) - int(action.h) % 2
        eff = {"type": "crop", "w": w, "h": h,
               "x": int(action.x or 0), "y": int(action.y or 0)}
        label, summary = "crop", "Cropped the frame."
    else:
        raise EditError("Crop needs an aspect (square/portrait/landscape) or explicit w and h.")
    _set_effect(project, eff, ("crop",))
    return _commit_effect(db, project, action, label, summary)


def _exec_resize(db, project, action):
    h = int(action.height or 720)
    _set_effect(project, {"type": "scale", "height": h}, ("scale",))
    return _commit_effect(db, project, action, f"resize {h}p",
                          f"Resized the video to {h}p height.")


def _text_effect_from_action(action: Action, kind: str) -> dict:
    eff: dict = {"type": kind, "text": (action.text or "").strip()}
    if action.start_s is not None:
        eff["start_s"] = float(action.start_s)
    if action.end_s is not None:
        eff["end_s"] = float(action.end_s)
    if action.align:
        eff["position"] = action.align
    if action.size:
        eff["size"] = action.size
    if action.color:
        eff["color"] = action.color
    return eff


def _exec_add_caption(db, project, action):
    if not (action.text or "").strip():
        raise EditError("add_caption needs text.")
    eff = _text_effect_from_action(action, "caption")
    eff.setdefault("position", "bottom")
    project.effects = list(project.effects or []) + [eff]
    # also stamp caption_text on overlapping clips so the UI captions lane shows it
    a = eff.get("start_s", 0.0)
    b = eff.get("end_s", ops.total_duration(_segments(project)))
    segs = _segments(project)
    t = 0.0
    for c, seg in zip(project.clips, segs):
        s0, s1 = t, t + seg.duration
        if not (b <= s0 or a >= s1):
            c.caption_text = eff["text"]
        t = s1
    v = _commit_new_timeline(db, project, segs, action, "caption")
    return ExecResult(summary=f'Added caption "{eff["text"][:40]}".',
                      timeline_changed=True, version_id=v.id)


def _exec_add_text(db, project, action):
    if not (action.text or "").strip():
        raise EditError("add_text needs text.")
    eff = _text_effect_from_action(action, "text")
    eff.setdefault("position", "top")
    eff.setdefault("size", "large")
    project.effects = list(project.effects or []) + [eff]
    return _commit_effect(db, project, action, "text overlay",
                          f'Added on-screen text "{eff["text"][:40]}".')


def _exec_add_subtitles(db, project, action):
    words = project.transcript or []
    if not words:
        status = project.transcript_status
        if status == "processing":
            raise EditError(
                "Still transcribing the audio — try 'add subtitles' again in a few seconds."
            )
        if status == "error":
            raise EditError("Transcription failed, so there's no speech to caption.")
        raise EditError(
            "No speech was detected in this video, so there are no subtitles to add."
        )
    segs = _segments(project)
    # group words into ~3s / 8-word cues, mapped to timeline time
    cues: list[dict] = []
    cur: list[str] = []
    cue_start: float | None = None
    last_end = 0.0
    for w in words:
        ts = ops.source_to_timeline(segs, float(w.get("start", 0.0)))
        if ts is None:
            continue
        if cue_start is None:
            cue_start = ts
        cur.append(str(w.get("word", "")).strip())
        last_end = ts + 0.4
        if len(cur) >= 8 or (last_end - cue_start) >= 3.0:
            cues.append({"type": "subtitle", "text": " ".join(cur).strip(),
                         "start_s": cue_start, "end_s": last_end, "position": "bottom"})
            cur, cue_start = [], None
    if cur and cue_start is not None:
        cues.append({"type": "subtitle", "text": " ".join(cur).strip(),
                     "start_s": cue_start, "end_s": last_end, "position": "bottom"})
    if not cues:
        raise EditError("Couldn't build subtitles from the transcript.")
    # drop any prior auto-subtitles, then add the fresh set
    project.effects = [e for e in (project.effects or []) if e.get("type") != "subtitle"] + cues
    return _commit_effect(db, project, action, "subtitles",
                          f"Burned in {len(cues)} subtitle cues from the transcript.")


def _exec_remove_effects(db, project, action):
    if not project.effects:
        raise EditError("There are no effects to remove.")
    project.effects = []
    return _commit_effect(db, project, action, "clear effects",
                          "Removed all colour/text/speed effects.")


def _exec_undo(db, project, action):
    head = db.get(EditVersion, project.head_version_id) if project.head_version_id else None
    if head is None:
        raise EditError("Nothing to undo.")
    pdir = storage.project_dir(project.user_id, project.id)

    if head.parent_id:
        parent = db.get(EditVersion, head.parent_id)
        if parent is None:
            raise EditError("Nothing to undo.")
        layout = parent.layout or []
        segs = [Segment(s["src_start_s"], s["src_end_s"]) for s in layout]
        project.muted_ranges = list(parent.muted_snapshot or [])
        project.effects = list(parent.effects_snapshot or [])
        project.head_version_id = parent.id
        src_file = storage.abs_path(parent.file_path)
        _make_proxy(project, src_file, pdir, parent.version_index)
        target = "the previous version"
    else:
        # revert the first edit -> back to the untouched original
        segs = [Segment(0.0, project.duration_s)]
        project.muted_ranges = []
        project.effects = []
        project.head_version_id = None
        _make_proxy(project, storage.abs_path(project.original_path), pdir, 0)
        target = "the original"

    for c in list(project.clips):
        db.delete(c)
    db.flush()
    for i, seg in enumerate(segs):
        db.add(Clip(project_id=project.id, order_index=i,
                    src_start_s=seg.src_start, src_end_s=seg.src_end))
    db.commit()
    db.refresh(project)
    return ExecResult(summary=f"Undid the last edit — restored {target}.",
                      timeline_changed=True)


def _exec_seek_preview(db: Session, project: Project, action: Action) -> ExecResult:
    return ExecResult(
        summary=f"Moved the playhead to {_fmt(action.start_s or 0.0)}.",
        timeline_changed=False,
        seek_to=action.start_s or 0.0,
    )


_EXECUTORS = {
    # structural
    ActionName.cut_range: _exec_cut_range,
    ActionName.trim: _exec_trim,
    ActionName.mute_range: _exec_mute_range,
    ActionName.split: _exec_split,
    ActionName.delete_clip: _exec_delete_clip,
    ActionName.reorder_clips: _exec_reorder_clips,
    ActionName.remove_silence: _exec_remove_silence,
    # text
    ActionName.add_caption: _exec_add_caption,
    ActionName.add_text: _exec_add_text,
    ActionName.add_subtitles: _exec_add_subtitles,
    # audio
    ActionName.change_volume: _exec_change_volume,
    ActionName.silence_audio: _exec_silence_audio,
    # speed
    ActionName.change_speed: _exec_change_speed,
    # fades
    ActionName.fade_in: _exec_fade_in,
    ActionName.fade_out: _exec_fade_out,
    # colour / style
    ActionName.grayscale: _exec_grayscale,
    ActionName.sepia: _exec_sepia,
    ActionName.invert_colors: _exec_invert,
    ActionName.adjust_color: _exec_adjust_color,
    ActionName.blur: _exec_blur,
    ActionName.sharpen: _exec_sharpen,
    ActionName.vignette: _exec_vignette,
    # geometry
    ActionName.rotate: _exec_rotate,
    ActionName.flip: _exec_flip,
    ActionName.crop: _exec_crop,
    ActionName.resize: _exec_resize,
    # meta
    ActionName.undo: _exec_undo,
    ActionName.remove_effects: _exec_remove_effects,
    ActionName.seek_preview: _exec_seek_preview,
}


def apply_action(db: Session, project: Project, action: Action) -> ExecResult:
    """Execute a single timeline action. Raises EditError on invalid/unsupported edits."""
    handler = _EXECUTORS.get(action.name)
    if handler is None:
        raise EditError(f"Action '{action.name.value}' is not implemented yet.")
    return handler(db, project, action)
