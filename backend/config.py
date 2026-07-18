"""Central configuration for VoiceCut.

Every value is local-first. No cloud endpoints, no API keys. The only network
call the app ever makes is to a local Ollama daemon (default 127.0.0.1:11434)
and, optionally, teammates' machines on the LAN.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the backend/ package directory.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOICECUT_", env_file=".env", extra="ignore")

    # --- Server ---
    host: str = "0.0.0.0"          # bind all interfaces so the LAN can reach it
    port: int = 8000

    # --- Model runtime (all local) ---
    ollama_url: str = "http://127.0.0.1:11434"
    # NOTE: There is no "gemma4" tag in Ollama. The current multimodal 12B Gemma
    # is `gemma3:12b` (Q4 by default). Override with VOICECUT_MODEL to test on a
    # lighter local model already on disk, e.g. `gemma3:4b`.
    model: str = "gemma3:12b"
    whisper_model: str = "small"   # faster-whisper size for STT
    whisper_compute: str = "int8"  # CPU-friendly; use "float16" on GPU
    piper_voice: str = "en_US-lessac-medium"

    # --- Storage ---
    db_url: str = f"sqlite:///{(DATA_DIR / 'voicecut.sqlite').as_posix()}"
    storage_dir: str = str(STORAGE_DIR)

    # --- Auth ---
    jwt_secret: str = "dev-only-change-me"   # regenerated in start scripts for real runs
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 720
    cookie_name: str = "voicecut_session"
    cookie_secure: bool = False   # LAN over http; no TLS in the hackathon setup

    # --- Agent loop ---
    max_steps: int = 12
    planner_max_tokens: int = 250
    verifier_max_tokens: int = 60

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    s.storage_path.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
