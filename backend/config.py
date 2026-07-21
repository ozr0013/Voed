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
MODELS_DIR = ROOT / "models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOICECUT_", env_file=".env", extra="ignore")

    # --- Server ---
    host: str = "0.0.0.0"          # bind all interfaces so the LAN can reach it
    port: int = 8000

    # --- Model runtime (all local) ---
    ollama_url: str = "http://127.0.0.1:11434"
    # Gemma 4 12B multimodal (Q4 by default), the project's core model. Override
    # with VOICECUT_MODEL to test on a lighter local model, e.g. gemma3:4b.
    model: str = "gemma4:12b"
    whisper_model: str = "large-v3"  # most accurate; catches noisy/accented real-mic speech
    whisper_compute: str = "int8"    # CPU-friendly; use "float16" on GPU
    piper_voice: str = "en_US-lessac-medium"
    piper_dir: str = str(MODELS_DIR / "piper")

    @property
    def piper_model_path(self) -> Path:
        return Path(self.piper_dir) / f"{self.piper_voice}.onnx"

    @property
    def piper_config_path(self) -> Path:
        return Path(self.piper_dir) / f"{self.piper_voice}.onnx.json"

    # --- Storage ---
    db_url: str = f"sqlite:///{(DATA_DIR / 'voicecut.sqlite').as_posix()}"
    storage_dir: str = str(STORAGE_DIR)

    # --- Auth ---
    # 32+ bytes so HS256 is happy in dev; start scripts inject a per-machine
    # random secret via VOICECUT_JWT_SECRET for real runs.
    jwt_secret: str = "voicecut-dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_hours: int = 720
    cookie_name: str = "voicecut_session"
    cookie_secure: bool = False   # LAN over http; no TLS in the hackathon setup

    # --- Integrations (optional; opt-in cloud export) ---
    # Google Drive export. Empty by default — VoiceCut stays fully local unless
    # the user supplies their own OAuth client. Set these via env / .env:
    #   VOICECUT_GOOGLE_CLIENT_ID, VOICECUT_GOOGLE_CLIENT_SECRET
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/integrations/drive/callback"
    # "Sign in with Google" lands on the FRONTEND origin (Vite proxies /api to the
    # backend) so the session cookie is set for the origin the app actually runs
    # on. Register this exact URI in the OAuth client's authorized redirect URIs.
    google_login_redirect_uri: str = "http://localhost:5173/api/auth/google/callback"

    @property
    def google_drive_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

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
