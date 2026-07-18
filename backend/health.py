"""Startup + runtime health checks for the local dependencies.

Surfaces a single /api/health payload the frontend and start scripts read to
tell the user exactly what is missing (and the command to fix it).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass

from . import ollama_client
from .config import settings


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def _which_version(binary: str, args: list[str]) -> str | None:
    path = shutil.which(binary)
    if not path:
        return None
    try:
        out = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=10
        )
        first = (out.stdout or out.stderr).splitlines()
        return first[0] if first else path
    except (subprocess.SubprocessError, OSError):
        return path


def check_ffmpeg() -> Check:
    v = _which_version("ffmpeg", ["-version"])
    if v:
        return Check("ffmpeg", True, v)
    return Check(
        "ffmpeg", False, "not found on PATH",
        fix="Install ffmpeg (https://ffmpeg.org/download.html) and add it to PATH.",
    )


def check_ffprobe() -> Check:
    v = _which_version("ffprobe", ["-version"])
    if v:
        return Check("ffprobe", True, v)
    return Check(
        "ffprobe", False, "not found on PATH",
        fix="ffprobe ships with ffmpeg; ensure the ffmpeg bin dir is on PATH.",
    )


async def check_ollama() -> Check:
    if not await ollama_client.is_up():
        return Check(
            "ollama", False, f"daemon not reachable at {settings.ollama_url}",
            fix="Start Ollama (https://ollama.com). It must be running for the agent.",
        )
    return Check("ollama", True, f"reachable at {settings.ollama_url}")


async def check_model() -> Check:
    if not await ollama_client.is_up():
        return Check(
            "model", False, "cannot verify — ollama not reachable",
            fix=f"Start Ollama, then run: ollama pull {settings.model}",
        )
    if await ollama_client.has_model():
        return Check("model", True, f"{settings.model} present")
    try:
        available = ", ".join(await ollama_client.list_models()) or "none"
    except Exception:  # noqa: BLE001
        available = "unknown"
    return Check(
        "model", False,
        f"{settings.model} not pulled (available: {available})",
        fix=f"Run: ollama pull {settings.model}  "
            f"(or set VOICECUT_MODEL to a local multimodal tag such as gemma3:4b)",
    )


def check_whisper() -> Check:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return Check(
            "whisper", False, "faster-whisper not installed",
            fix="pip install -r requirements.txt",
        )
    return Check("whisper", True, f"faster-whisper ready ({settings.whisper_model})")


def check_piper() -> Check:
    if settings.piper_model_path.exists():
        return Check("piper", True, f"voice {settings.piper_voice} installed")
    return Check(
        "piper", False, f"voice {settings.piper_voice} not downloaded",
        fix=(
            f"python -m piper.download_voices --download-dir "
            f"{settings.piper_dir} {settings.piper_voice}"
        ),
    )


async def full_report() -> dict:
    checks = [
        check_ffmpeg(),
        check_ffprobe(),
        await check_ollama(),
        await check_model(),
        check_whisper(),
        check_piper(),
    ]
    return {
        "ok": all(c.ok for c in checks),
        "model": settings.model,
        "checks": [asdict(c) for c in checks],
    }
