"""VoiceCut FastAPI application.

Serves the JSON API, (later) the agent WebSocket, and — in a production build —
the compiled frontend from frontend/dist. CORS is opened to the LAN so teammates
and judges can reach the app via the host's IP.
"""
from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth, health, integrations, models_routes, stt, tts, upload
from .agent import routes as agent_routes
from .config import ROOT, settings
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    init_db()
    yield


app = FastAPI(title="VoiceCut", version="0.1.0", lifespan=lifespan)

# LAN access: the frontend dev server (Vite, :5173) and any teammate machine on
# the local network. We allow all origins because this only ever runs on a
# trusted LAN with no internet exposure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def lan_ip() -> str:
    """Best-effort primary LAN IP (no packets actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@app.get("/api/health")
async def api_health() -> dict:
    report = await health.full_report()
    report["lan_url"] = f"http://{lan_ip()}:{settings.port}"
    return report


@app.get("/api/ping")
async def ping() -> dict:
    return {"ok": True, "app": "voicecut"}


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(stt.router)
app.include_router(tts.router)
app.include_router(agent_routes.router)
app.include_router(integrations.router)
app.include_router(models_routes.router)


# --- Static frontend (production build) ---
# In dev, the frontend runs under Vite on :5173 and talks to this API directly.
# In a production build (`npm run build`), frontend/dist exists and we serve it.
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:  # noqa: ARG001
        # Serve real files if present, else fall back to index.html (SPA routing).
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
