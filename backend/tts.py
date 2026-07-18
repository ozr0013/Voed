"""Piper text-to-speech. POST /api/tts {text} -> streamed WAV.

The Piper voice is loaded once and reused. Voice model files live under
models/piper/ and are downloaded by the start script (or manually via
`python -m piper.download_voices --download-dir models/piper en_US-lessac-medium`).
All synthesis is local — no network.
"""
from __future__ import annotations

import io
import wave
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config import settings

router = APIRouter(prefix="/api", tags=["tts"])

_voice = None
_lock = Lock()


def _get_voice():
    global _voice
    if _voice is None:
        with _lock:
            if _voice is None:
                if not settings.piper_model_path.exists():
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Piper voice '{settings.piper_voice}' not installed. "
                            f"Run: python -m piper.download_voices "
                            f"--download-dir {settings.piper_dir} {settings.piper_voice}"
                        ),
                    )
                from piper import PiperVoice

                _voice = PiperVoice.load(
                    str(settings.piper_model_path), str(settings.piper_config_path)
                )
    return _voice


def synthesize_wav_bytes(text: str) -> bytes:
    voice = _get_voice()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav(text, wf)
    return buf.getvalue()


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/tts")
def tts(req: TTSRequest) -> Response:
    audio = synthesize_wav_bytes(req.text.strip())
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )
