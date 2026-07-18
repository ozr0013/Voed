"""Shared faster-whisper ASR. Used by /stt (command transcription) and, in a
later milestone, background video transcription.

The model is loaded once (lazily) and reused. Audio is decoded to 16 kHz mono
WAV via ffmpeg first so any container the browser produces (webm/opus, ogg, wav)
transcribes reliably.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from .config import settings

_model = None
_lock = Lock()


def get_model():
    """Lazily construct the WhisperModel singleton (thread-safe)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from faster_whisper import WhisperModel

                _model = WhisperModel(
                    settings.whisper_model,
                    device="cpu",
                    compute_type=settings.whisper_compute,
                )
    return _model


@dataclass
class Word:
    start: float
    end: float
    word: str


@dataclass
class Transcript:
    text: str
    language: str
    words: list[Word] = field(default_factory=list)


def _to_wav16k(src: Path) -> Path:
    out = Path(tempfile.mktemp(suffix=".wav"))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-ar", "16000", "-ac", "1", str(out)],
        check=True, capture_output=True, timeout=120,
    )
    return out


def transcribe_path(path: str | Path, *, word_timestamps: bool = False) -> Transcript:
    """Transcribe any audio/video file. Decodes to 16 kHz mono WAV first."""
    model = get_model()
    wav = _to_wav16k(Path(path))
    try:
        segments, info = model.transcribe(
            str(wav), word_timestamps=word_timestamps, vad_filter=False
        )
        text_parts: list[str] = []
        words: list[Word] = []
        for seg in segments:
            text_parts.append(seg.text)
            if word_timestamps and seg.words:
                for w in seg.words:
                    words.append(Word(start=w.start, end=w.end, word=w.word))
        return Transcript(
            text="".join(text_parts).strip(),
            language=info.language,
            words=words,
        )
    finally:
        wav.unlink(missing_ok=True)
