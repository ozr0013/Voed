"""Runtime-active Ollama model tag (persisted locally).

`VOICECUT_MODEL` / `.env` sets the default at process start; users can override
via the model picker, which writes `data/active_model.json`.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR, settings

_STATE_FILE = DATA_DIR / "active_model.json"


def default_model() -> str:
    return settings.model


def get_active_model() -> str:
    if _STATE_FILE.is_file():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            tag = data.get("model")
            if isinstance(tag, str) and tag.strip():
                return tag.strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return default_model()


def set_active_model(tag: str) -> str:
    tag = tag.strip()
    if not tag:
        raise ValueError("model tag required")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"model": tag}, indent=2), encoding="utf-8")
    return tag
