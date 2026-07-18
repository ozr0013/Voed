"""Pure timeline math + the ffmpeg render.

The timeline is an ordered list of segments, each a slice [src_start, src_end]
of the ORIGINAL video. Editing = transforming that list; rendering = extracting
those slices from the original and concatenating them (frame-accurate re-encode).
The original file is never modified.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .. import media

EPS = 0.02  # ignore sub-frame slivers


@dataclass
class Segment:
    src_start: float
    src_end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.src_end - self.src_start)


def remove_interval(segments: list[Segment], a: float, b: float) -> list[Segment]:
    """Remove timeline interval [a, b] (timeline seconds). Splits/trims/drops
    clips as needed. Returns the new segment list."""
    if b <= a:
        return list(segments)
    out: list[Segment] = []
    t = 0.0  # running timeline position at the start of each segment
    for seg in segments:
        span = seg.duration
        s0, s1 = t, t + span  # this segment's timeline range
        # kept left part [s0, min(s1, a)]
        if s0 < a:
            keep_end_tl = min(s1, a)
            src_end = seg.src_start + (keep_end_tl - s0)
            if src_end - seg.src_start > EPS:
                out.append(Segment(seg.src_start, src_end))
        # kept right part [max(s0, b), s1]
        if s1 > b:
            keep_start_tl = max(s0, b)
            src_start = seg.src_start + (keep_start_tl - s0)
            if seg.src_end - src_start > EPS:
                out.append(Segment(src_start, seg.src_end))
        t = s1
    return out


def keep_interval(segments: list[Segment], a: float, b: float) -> list[Segment]:
    """Keep only timeline interval [a, b] (used by `trim`)."""
    total = sum(s.duration for s in segments)
    kept = remove_interval(segments, b, total)  # drop after b
    kept = remove_interval(kept, 0.0, a)        # drop before a
    return kept


def total_duration(segments: list[Segment]) -> float:
    return sum(s.duration for s in segments)


def timeline_to_source(
    segments: list[Segment], a: float, b: float
) -> list[tuple[float, float]]:
    """Map a timeline interval [a, b] to the source (src_start, src_end) ranges it
    covers, walking the ordered segment list. Used to record mutes in source time
    so they survive later cuts/trims."""
    out: list[tuple[float, float]] = []
    if b <= a:
        return out
    t = 0.0
    for seg in segments:
        s0, s1 = t, t + seg.duration
        lo, hi = max(a, s0), min(b, s1)
        if hi - lo > EPS:
            out.append((seg.src_start + (lo - s0), seg.src_start + (hi - s0)))
        t = s1
    return out


def merge_intervals(intervals: list[dict]) -> list[dict]:
    """Union a list of {"start","end"} intervals into a sorted, non-overlapping set."""
    items = sorted(
        (i["start"], i["end"]) for i in intervals if i.get("end", 0) - i.get("start", 0) > EPS
    )
    merged: list[list[float]] = []
    for s, e in items:
        if merged and s <= merged[-1][1] + EPS:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start": s, "end": e} for s, e in merged]


def build_video_transform_filter(
    width: int,
    height: int,
    rotate_angle: int | None = None,
    aspect: str | None = None,
) -> str | None:
    """Build an ffmpeg video filter chain for optional rotate / crop transforms."""
    filters: list[str] = []
    if rotate_angle is not None:
        if rotate_angle == 90:
            filters.append("transpose=1")
        elif rotate_angle == 180:
            filters.append("transpose=1,transpose=1")
        elif rotate_angle == 270:
            filters.append("transpose=2")
        else:
            raise ValueError("rotate angle must be 90, 180, or 270")
    if aspect is not None:
        ow, oh = width, height
        if aspect == "square":
            size = min(ow, oh)
            w = h = size
        elif aspect == "portrait":
            target = 9.0 / 16.0
            if ow / oh > target:
                w = int(round(oh * target))
                h = oh
            else:
                w = ow
                h = int(round(ow / target))
        elif aspect == "landscape":
            target = 16.0 / 9.0
            if ow / oh < target:
                h = int(round(ow / target))
                w = ow
            else:
                h = oh
                w = int(round(oh * target))
        else:
            raise ValueError("crop aspect must be square, portrait, or landscape")
        x = max(0, (ow - w) // 2)
        y = max(0, (oh - h) // 2)
        filters.append(f"crop={w}:{h}:{x}:{y}")
    return ",".join(filters) if filters else None


def _has_audio(src: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(src)],
            capture_output=True, text=True, timeout=30,
        )
        return bool(out.stdout.strip())
    except subprocess.SubprocessError:
        return False


def _local_mutes(
    seg: Segment, muted: list[dict]
) -> list[tuple[float, float]]:
    """Muted source intervals that overlap this segment, expressed in the
    segment's LOCAL time (0-based) after atrim resets PTS to 0."""
    local: list[tuple[float, float]] = []
    for m in muted:
        ms, me = m["start"], m["end"]
        lo, hi = max(ms, seg.src_start), min(me, seg.src_end)
        if hi - lo > EPS:
            local.append((lo - seg.src_start, hi - seg.src_start))
    return local


def render_segments(
    original: Path,
    segments: list[Segment],
    out: Path,
    muted: list[dict] | None = None,
    rotate_angle: int | None = None,
    aspect: str | None = None,
) -> None:
    """Extract each source segment from the original and concatenate them into a
    single frame-accurate file (ultrafast re-encode). `muted` is a list of
    source-time {"start","end"} intervals whose audio is silenced (video kept)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise ValueError("Cannot render an empty timeline")

    muted = muted or []
    has_audio = _has_audio(original)
    info = media.ffprobe_info(original) if rotate_angle is not None or aspect is not None else None
    width = info.width if info is not None else 0
    height = info.height if info is not None else 0
    transform_filter = build_video_transform_filter(width, height, rotate_angle, aspect)

    parts, vlabels, alabels = [], [], []
    for i, seg in enumerate(segments):
        s, e = seg.src_start, seg.src_end
        video_expr = f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS"
        if transform_filter:
            video_expr += f",{transform_filter}"
        parts.append(f"{video_expr}[v{i}];")
        vlabels.append(f"[v{i}]")
        if has_audio:
            achain = f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS"
            for lo, hi in _local_mutes(seg, muted):
                achain += f",volume=enable='between(t,{lo:.3f},{hi:.3f})':volume=0"
            parts.append(f"{achain}[a{i}];")
            alabels.append(f"[a{i}]")

    n = len(segments)
    if has_audio:
        concat = "".join(f"{vlabels[i]}{alabels[i]}" for i in range(n))
        filtergraph = "".join(parts) + f"{concat}concat=n={n}:v=1:a=1[outv][outa]"
        maps = ["-map", "[outv]", "-map", "[outa]"]
    else:
        concat = "".join(vlabels)
        filtergraph = "".join(parts) + f"{concat}concat=n={n}:v=1:a=0[outv]"
        maps = ["-map", "[outv]"]

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(original),
        "-filter_complex", filtergraph, *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart", str(out)]

    proc = subprocess.run(cmd, capture_output=True, timeout=900)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-800:]
        raise RuntimeError(f"ffmpeg render failed: {err}")
