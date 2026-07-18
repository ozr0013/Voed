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


def render_segments(original: Path, segments: list[Segment], out: Path) -> None:
    """Extract each source segment from the original and concatenate them into a
    single frame-accurate file (ultrafast re-encode)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise ValueError("Cannot render an empty timeline")

    has_audio = _has_audio(original)
    parts, vlabels, alabels = [], [], []
    for i, seg in enumerate(segments):
        s, e = seg.src_start, seg.src_end
        parts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
        )
        vlabels.append(f"[v{i}]")
        if has_audio:
            parts.append(
                f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}];"
            )
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
