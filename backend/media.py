"""ffmpeg / ffprobe helpers. All video work is local subprocess calls."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-800:]
        raise MediaError(f"{cmd[0]} failed: {err}")
    return proc


@dataclass
class ProbeResult:
    duration_s: float
    width: int
    height: int
    fps: float
    has_audio: bool


def ffprobe_info(path: str | Path) -> ProbeResult:
    """Validate a file is real media and read its key metadata."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = _run(cmd, timeout=60)
    data = json.loads(proc.stdout.decode("utf-8", "replace"))
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("No video stream found — is this a video file?")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
    width = int(video.get("width", 0) or 0)
    height = int(video.get("height", 0) or 0)

    fps = 0.0
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/0"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    return ProbeResult(duration, width, height, round(fps, 3), has_audio)


def make_thumbnail(src: str | Path, out: str | Path, at_s: float = 1.0) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{max(0.0, at_s):.3f}", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(out),
    ], timeout=60)


def make_proxy(src: str | Path, out: str | Path) -> None:
    """720p H.264 proxy for instant timeline scrubbing in the browser."""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(src),
        # downscale to 720p tall at most; never upscale a smaller source
        "-vf", "scale=-2:'min(720,ih)'",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(out),
    ])


def waveform_peaks(src: str | Path, buckets: int = 400) -> list[float]:
    """Return `buckets` normalized peak amplitudes (0..1) for timeline rendering.

    Decodes mono 8 kHz PCM (tiny) and reduces to peak-per-bucket. Returns a flat
    zero array if the file has no audio.
    """
    import numpy as np

    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", str(src),
                "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
            ],
            capture_output=True, timeout=300,
        )
    except subprocess.SubprocessError:
        return [0.0] * buckets
    if proc.returncode != 0 or not proc.stdout:
        return [0.0] * buckets

    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return [0.0] * buckets
    samples = np.abs(samples) / 32768.0
    # split into `buckets` chunks, take peak of each
    idx = np.linspace(0, samples.size, buckets + 1).astype(int)
    peaks = [
        float(samples[idx[i]:idx[i + 1]].max()) if idx[i + 1] > idx[i] else 0.0
        for i in range(buckets)
    ]
    hi = max(peaks) or 1.0
    return [round(p / hi, 3) for p in peaks]
