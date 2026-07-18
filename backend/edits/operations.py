"""Pure timeline math + the ffmpeg render.

The timeline is an ordered list of segments, each a slice [src_start, src_end]
of the ORIGINAL video. Editing = transforming that list; rendering = extracting
those slices from the original and concatenating them (frame-accurate re-encode).
The original file is never modified.
"""
from __future__ import annotations

import shutil
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


def source_to_timeline(segments: list[Segment], ts: float) -> float | None:
    """Map a SOURCE time to its position on the current timeline, or None if that
    source time was cut away. Inverse of `timeline_to_source`."""
    t = 0.0
    for seg in segments:
        if seg.src_start - EPS <= ts <= seg.src_end + EPS:
            return t + max(0.0, ts - seg.src_start)
        t += seg.duration
    return None


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


# --------------------------------------------------------------------------- #
# Effects — a post-concat filter pass applied to the whole edited timeline.
#
# Effects live in Project.effects as a list of dicts (see models.py). They are
# applied AFTER the segments are concatenated, in a fixed, sensible order, so the
# agent can grow new skills (colour grade, speed, captions, fades, …) purely by
# emitting new effect dicts — no change to the segment/render contract.
# --------------------------------------------------------------------------- #
# Fast-path fonts that commonly exist per-OS.
_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    # macOS — Arial isn't guaranteed; Helvetica/SFNS always ship with the OS
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/Library/Fonts/Arial.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

# Font folders to scan if no fast-path font exists (guarantees a hit on any OS).
_FONT_DIRS = [
    "C:/Windows/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/System/Library/Fonts",
    "/Library/Fonts",
    str(Path.home() / "Library" / "Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".fonts"),
]


def _resolve_font() -> str | None:
    """Find a usable font on ANY OS (Windows / macOS / Linux). We always hand
    drawtext a concrete fontfile instead of relying on fontconfig (some ffmpeg
    builds ship without it), so burned-in captions render identically everywhere.
    macOS was failing because Arial isn't guaranteed at a fixed path — the
    directory scan below always finds a system font (Helvetica/SFNS/…)."""
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    # Fallback: first real font file anywhere in the platform font dirs.
    for ext in ("*.ttf", "*.otf", "*.ttc"):
        for d in _FONT_DIRS:
            dp = Path(d)
            if not dp.is_dir():
                continue
            try:
                hits = sorted(dp.glob(ext)) or sorted(dp.rglob(ext))
            except OSError:
                continue
            if hits:
                return str(hits[0])
    return None


_FONT_SIZES = {"small": 26, "medium": 40, "large": 60}
_POSITIONS = {
    "top": "y=h*0.08",
    "center": "y=(h-th)/2",
    "bottom": "y=h*0.86-th",
}


def _atempo_chain(factor: float) -> str:
    """atempo only accepts 0.5–2.0 per instance; chain to reach any factor."""
    factor = max(0.25, min(100.0, factor))
    parts: list[str] = []
    remaining = factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _speed_factor(effects: list[dict]) -> float:
    f = 1.0
    for e in effects:
        if e.get("type") == "speed":
            f *= float(e.get("factor", 1.0) or 1.0)
    return max(0.1, f)


def _drawtext(e: dict, font_ref: str | None, textfile_ref: str, tscale: float) -> str:
    """One drawtext filter. `textfile_ref`/`font_ref` are RELATIVE filenames
    resolved against ffmpeg's cwd, so no path/quote escaping is ever needed;
    `expansion=none` makes the file's text fully literal."""
    fontsize = _FONT_SIZES.get(e.get("size", "medium"), _FONT_SIZES["medium"])
    color = str(e.get("color", "white")).replace(":", "").replace("'", "").replace(" ", "")
    ypos = _POSITIONS.get(e.get("position", "bottom"), _POSITIONS["bottom"])
    opts = [
        f"textfile={textfile_ref}",
        "expansion=none",
        "x=(w-tw)/2",
        ypos,
        f"fontsize={fontsize}",
        f"fontcolor={color or 'white'}",
        "box=1",
        "boxcolor=black@0.55",
        "boxborderw=14",
    ]
    if font_ref:
        opts.insert(0, f"fontfile={font_ref}")
    start = e.get("start_s")
    end = e.get("end_s")
    if start is not None or end is not None:
        a = float(start or 0.0) * tscale
        b = float(end if end is not None else 1e9) * tscale
        opts.append(f"enable='between(t,{a:.3f},{b:.3f})'")
    return "drawtext=" + ":".join(opts)


def build_video_filters(
    effects: list[dict],
    base_duration: float,
    font_ref: str | None = None,
    workdir: Path | None = None,
    prefix: str = "",
) -> str:
    """Ordered video-filter chain for the effect list (empty string = passthrough).
    Text effects write their content to `workdir/<prefix>capN.txt` and reference it
    by relative name, so arbitrary caption text needs no escaping."""
    if not effects:
        return ""
    speed = _speed_factor(effects)
    tscale = 1.0 / speed
    eff_dur = base_duration * tscale
    chain: list[str] = []

    # 1) geometry
    for e in effects:
        t = e.get("type")
        if t == "crop":
            chain.append(
                f"crop={e.get('w','iw')}:{e.get('h','ih')}:{e.get('x',0)}:{e.get('y',0)}"
            )
        elif t in ("scale", "resize"):
            h = int(e.get("height", 720))
            chain.append(f"scale=-2:{h}")
        elif t == "rotate":
            deg = int(e.get("degrees", 90)) % 360
            chain.append(
                {90: "transpose=1", 180: "transpose=2,transpose=2", 270: "transpose=2"}.get(
                    deg, "transpose=1"
                )
            )
        elif t in ("hflip", "flip_horizontal"):
            chain.append("hflip")
        elif t in ("vflip", "flip_vertical"):
            chain.append("vflip")

    # 2) speed (video side)
    if speed != 1.0:
        chain.append(f"setpts=PTS/{speed:.4f}")

    # 3) colour / stylistic
    eq = {}
    for e in effects:
        t = e.get("type")
        if t == "brightness":
            eq["brightness"] = float(e.get("value", 0.0))
        elif t == "contrast":
            eq["contrast"] = float(e.get("value", 1.0))
        elif t == "saturation":
            eq["saturation"] = float(e.get("value", 1.0))
    if eq:
        chain.append("eq=" + ":".join(f"{k}={v}" for k, v in eq.items()))
    for e in effects:
        t = e.get("type")
        if t == "grayscale":
            chain.append("hue=s=0")
        elif t == "sepia":
            chain.append(
                "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
            )
        elif t == "invert":
            chain.append("negate")
        elif t == "blur":
            chain.append(f"gblur=sigma={float(e.get('value', 8))}")
        elif t == "sharpen":
            chain.append("unsharp=5:5:1.0")
        elif t == "vignette":
            chain.append("vignette")

    # 4) fades (use post-speed duration)
    for e in effects:
        t = e.get("type")
        d = float(e.get("duration_s", 1.0) or 1.0)
        if t == "fade_in":
            chain.append(f"fade=t=in:st=0:d={d:.3f}")
        elif t == "fade_out":
            chain.append(f"fade=t=out:st={max(0.0, eff_dur - d):.3f}:d={d:.3f}")

    # 5) burned-in text / captions / subtitles
    ti = 0
    for e in effects:
        if e.get("type") in ("text", "caption", "subtitle"):
            txt = str(e.get("text", "")).strip()
            if not txt or workdir is None:
                continue
            fn = f"{prefix}cap{ti}.txt"
            (workdir / fn).write_text(txt, encoding="utf-8")
            chain.append(_drawtext(e, font_ref, fn, tscale))
            ti += 1

    return ",".join(chain)


def build_audio_filters(effects: list[dict], base_duration: float) -> str:
    """Ordered audio-filter chain for the effect list (empty string = passthrough)."""
    if not effects:
        return ""
    speed = _speed_factor(effects)
    tscale = 1.0 / speed
    eff_dur = base_duration * tscale
    chain: list[str] = []
    if speed != 1.0:
        chain.append(_atempo_chain(speed))
    for e in effects:
        t = e.get("type")
        if t == "volume":
            chain.append(f"volume={float(e.get('factor', 1.0))}")
        elif t == "silence_all":
            chain.append("volume=0")
    for e in effects:
        t = e.get("type")
        d = float(e.get("duration_s", 1.0) or 1.0)
        if t == "fade_in":
            chain.append(f"afade=t=in:st=0:d={d:.3f}")
        elif t == "fade_out":
            chain.append(f"afade=t=out:st={max(0.0, eff_dur - d):.3f}:d={d:.3f}")
    return ",".join(chain)


def detect_silences(
    waveform: list[float] | None,
    source_duration: float,
    threshold: float = 0.06,
    min_len_s: float = 0.6,
) -> list[tuple[float, float]]:
    """Find silent SOURCE intervals from the peak waveform (0..1 per bucket)."""
    if not waveform or source_duration <= 0:
        return []
    n = len(waveform)
    bucket = source_duration / n
    out: list[tuple[float, float]] = []
    run_start: float | None = None
    for i, peak in enumerate(waveform):
        t = i * bucket
        if peak < threshold:
            if run_start is None:
                run_start = t
        else:
            if run_start is not None and (t - run_start) >= min_len_s:
                out.append((run_start, t))
            run_start = None
    if run_start is not None and (source_duration - run_start) >= min_len_s:
        out.append((run_start, source_duration))
    return out


def subtract_from_segments(
    segments: list[Segment], intervals: list[tuple[float, float]]
) -> list[Segment]:
    """Remove SOURCE intervals (e.g. detected silences) from every segment,
    splitting them as needed. Stays in source space, so it composes with cuts."""
    cuts = sorted(intervals)
    out: list[Segment] = []
    for seg in segments:
        pieces = [(seg.src_start, seg.src_end)]
        for cs, ce in cuts:
            nxt: list[tuple[float, float]] = []
            for ps, pe in pieces:
                if ce <= ps or cs >= pe:
                    nxt.append((ps, pe))
                    continue
                if ps < cs:
                    nxt.append((ps, cs))
                if ce < pe:
                    nxt.append((ce, pe))
            pieces = nxt
        for ps, pe in pieces:
            if pe - ps > EPS:
                out.append(Segment(ps, pe))
    return out


def render_segments(
    original: Path,
    segments: list[Segment],
    out: Path,
    muted: list[dict] | None = None,
    effects: list[dict] | None = None,
) -> None:
    """Extract each source segment from the original, concatenate them, then apply
    the effect pass. Produces a single frame-accurate file (ultrafast re-encode).
    `muted` = source-time {"start","end"} audio silences; `effects` = timeline
    effect dicts applied after concat (colour, speed, fades, captions, …)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise ValueError("Cannot render an empty timeline")

    muted = muted or []
    effects = effects or []
    has_audio = _has_audio(original)
    base_duration = total_duration(segments)
    parts, vlabels, alabels = [], [], []
    for i, seg in enumerate(segments):
        s, e = seg.src_start, seg.src_end
        parts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];"
        )
        vlabels.append(f"[v{i}]")
        if has_audio:
            achain = f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS"
            for lo, hi in _local_mutes(seg, muted):
                achain += f",volume=enable='between(t,{lo:.3f},{hi:.3f})':volume=0"
            parts.append(f"{achain}[a{i}];")
            alabels.append(f"[a{i}]")

    n = len(segments)
    # Text effects reference a font + textfiles by RELATIVE name; ffmpeg runs with
    # cwd=out.parent so no Windows path/quote escaping is ever needed.
    workdir = out.parent
    prefix = f"{out.stem}_"
    font_ref = None
    if any(e.get("type") in ("text", "caption", "subtitle") for e in effects):
        font = _resolve_font()
        if font:
            font_ref = f"{prefix}font.ttf"
            try:
                shutil.copyfile(font, workdir / font_ref)
            except OSError:
                font_ref = None
    vf = build_video_filters(effects, base_duration, font_ref, workdir, prefix)
    af = build_audio_filters(effects, base_duration) if has_audio else ""

    graph = "".join(parts)
    if has_audio:
        concat = "".join(f"{vlabels[i]}{alabels[i]}" for i in range(n))
        graph += f"{concat}concat=n={n}:v=1:a=1[cv][ca]"
        vout, aout = "[cv]", "[ca]"
        if vf:
            graph += f";[cv]{vf}[outv]"; vout = "[outv]"
        if af:
            graph += f";[ca]{af}[outa]"; aout = "[outa]"
        maps = ["-map", vout, "-map", aout]
    else:
        concat = "".join(vlabels)
        graph += f"{concat}concat=n={n}:v=1:a=0[cv]"
        vout = "[cv]"
        if vf:
            graph += f";[cv]{vf}[outv]"; vout = "[outv]"
        maps = ["-map", vout]

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(original),
        "-filter_complex", graph, *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart", str(out)]

    proc = subprocess.run(cmd, capture_output=True, timeout=900, cwd=str(workdir))
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-800:]
        raise RuntimeError(f"ffmpeg render failed: {err}")
