"""Command speech-to-text. POST /api/stt (multipart audio) -> {text, language}.

Accepts whatever the browser's MediaRecorder produces (usually webm/opus).
faster-whisper via the shared ASR module; audio is decoded to 16 kHz WAV first.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from . import asr
from .auth import current_user
from .models import User

router = APIRouter(prefix="/api", tags=["stt"])


@router.post("/stt")
async def stt(
    audio: UploadFile = File(...),
    user: User = Depends(current_user),  # noqa: ARG001 — auth-gate the endpoint
) -> dict:
    data = await audio.read()
    suffix = Path(audio.filename or "clip.webm").suffix or ".webm"
    tmp = Path(tempfile.mktemp(suffix=suffix))
    tmp.write_bytes(data)
    # --- TEMP DIAGNOSTIC: keep the last upload so we can inspect what the
    #     browser actually captured. Remove once the mic issue is resolved. ---
    try:
        dbg = Path("data")
        dbg.mkdir(exist_ok=True)
        (dbg / f"last_stt_upload{suffix}").write_bytes(data)
        print(f"[stt] received {len(data)} bytes, suffix={suffix}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[stt] debug-save failed: {e}", flush=True)
    try:
        result = asr.transcribe_path(tmp, word_timestamps=False)
        print(f"[stt] transcript={result.text!r} lang={result.language}", flush=True)
        return {"text": result.text, "language": result.language}
    finally:
        tmp.unlink(missing_ok=True)
