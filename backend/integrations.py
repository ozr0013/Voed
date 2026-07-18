"""External export integrations. Currently: Google Drive.

VoiceCut is local-first; this module is strictly opt-in. It does nothing unless
the operator supplies their own Google OAuth client via:
    VOICECUT_GOOGLE_CLIENT_ID / VOICECUT_GOOGLE_CLIENT_SECRET

Flow (per user):
    connect  -> redirect to Google consent
    callback -> exchange code, store tokens (Integration row)
    export   -> refresh token if needed, upload the current render to Drive

All Google calls go over plain REST via httpx (already a dependency), so we
avoid pulling in the heavy google-api-python-client stack.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import storage
from .auth import current_user
from .config import settings
from .db import get_db
from .models import EditVersion, Integration, Project, User, utcnow

router = APIRouter(prefix="/api/integrations/drive", tags=["integrations"])

PROVIDER = "google_drive"
SCOPES = "openid email https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
UPLOAD_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=multipart&fields=id,name,webViewLink"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _owned_project(project_id: int, user: User, db: Session) -> Project:
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _render_path(project: Project, db: Session):
    """Absolute path to the current edited render (or the original)."""
    rel = None
    if project.head_version_id:
        head = db.get(EditVersion, project.head_version_id)
        rel = head.file_path if head else None
    rel = rel or project.original_path
    if not rel:
        raise HTTPException(status_code=404, detail="Nothing to export yet")
    path = storage.abs_path(rel)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export file missing")
    return path


def _sign_state(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "purpose": "drive_oauth",
        "exp": utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _verify_state(state: str) -> int:
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("purpose") != "drive_oauth":
            raise ValueError("bad purpose")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from e


def _get_integration(db: Session, user_id: int) -> Integration | None:
    return db.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == PROVIDER
        )
    )


def _needs_refresh(integ: Integration) -> bool:
    if not integ.token_expiry:
        return True
    exp = integ.token_expiry
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= exp - timedelta(seconds=60)


def _store_tokens(
    db: Session, user_id: int, token: dict, email: str | None
) -> Integration:
    integ = _get_integration(db, user_id)
    if not integ:
        integ = Integration(user_id=user_id, provider=PROVIDER, access_token="")
        db.add(integ)
    integ.access_token = token["access_token"]
    # Google omits refresh_token on re-consent unless prompt=consent; keep old one.
    if token.get("refresh_token"):
        integ.refresh_token = token["refresh_token"]
    integ.token_expiry = utcnow() + timedelta(seconds=int(token.get("expires_in", 3600)))
    if email:
        integ.account_email = email
    db.commit()
    db.refresh(integ)
    return integ


def _fresh_access_token(db: Session, integ: Integration) -> str:
    if not _needs_refresh(integ):
        return integ.access_token
    if not integ.refresh_token:
        raise HTTPException(
            status_code=401, detail="Drive access expired — reconnect your account."
        )
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": integ.refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not refresh Drive access.")
    integ = _store_tokens(db, integ.user_id, resp.json(), None)
    return integ.access_token


def _require_configured() -> None:
    if not settings.google_drive_configured:
        raise HTTPException(
            status_code=503,
            detail="Google Drive is not configured on this server. Set "
            "VOICECUT_GOOGLE_CLIENT_ID and VOICECUT_GOOGLE_CLIENT_SECRET.",
        )


# --------------------------------------------------------------------------- #
# OAuth endpoints
# --------------------------------------------------------------------------- #
@router.get("/status")
def status(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    integ = _get_integration(db, user.id)
    return {
        "configured": settings.google_drive_configured,
        "connected": integ is not None,
        "email": integ.account_email if integ else None,
    }


@router.get("/connect")
def connect(user: User = Depends(current_user)) -> RedirectResponse:
    _require_configured()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": _sign_state(user.id),
    }
    url = str(httpx.URL(AUTH_URL, params=params))
    return RedirectResponse(url)


@router.get("/callback")
def callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error or not code or not state:
        return _popup_html(f"Google sign-in failed: {error or 'no code returned'}", False)
    _require_configured()
    user_id = _verify_state(state)

    token_resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if token_resp.status_code != 200:
        return _popup_html("Could not complete Google authorization.", False)
    token = token_resp.json()

    email = None
    try:
        info = httpx.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            timeout=15,
        )
        if info.status_code == 200:
            email = info.json().get("email")
    except httpx.HTTPError:
        pass

    _store_tokens(db, user_id, token, email)
    return _popup_html("Google Drive connected. You can close this window.", True)


@router.post("/disconnect")
def disconnect(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    integ = _get_integration(db, user.id)
    if integ:
        db.delete(integ)
        db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
@router.post("/export/{project_id}")
def export_to_drive(
    project_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_configured()
    integ = _get_integration(db, user.id)
    if not integ:
        raise HTTPException(status_code=401, detail="Google Drive not connected.")

    project = _owned_project(project_id, user, db)
    path = _render_path(project, db)
    token = _fresh_access_token(db, integ)

    import re

    safe = re.sub(r"[^\w.-]+", "_", project.name).strip("_") or f"project_{project.id}"
    filename = f"{safe}.mp4"

    boundary = "voicecut_drive_boundary_7c1f"
    metadata = json.dumps({"name": filename, "mimeType": "video/mp4"}).encode()
    file_bytes = path.read_bytes()
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n" + metadata + b"\r\n"
        b"--" + boundary.encode() + b"\r\n"
        b"Content-Type: video/mp4\r\n\r\n" + file_bytes + b"\r\n"
        b"--" + boundary.encode() + b"--"
    )
    resp = httpx.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body,
        timeout=300,
    )
    if resp.status_code not in (200, 201):
        detail = f"Drive upload failed ({resp.status_code})."
        try:
            detail = resp.json().get("error", {}).get("message", detail)
        except (ValueError, AttributeError):
            pass
        raise HTTPException(status_code=502, detail=detail)
    data = resp.json()
    return {
        "ok": True,
        "name": data.get("name", filename),
        "link": data.get("webViewLink"),
    }


# --------------------------------------------------------------------------- #
def _popup_html(message: str, ok: bool) -> HTMLResponse:
    color = "#1f8a57" if ok else "#ef5a24"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>VoiceCut · Google Drive</title>
<style>
  body{{margin:0;height:100vh;display:grid;place-items:center;background:#e7e4dc;
       font-family:ui-monospace,Consolas,monospace;color:#17150f}}
  .card{{border:1px solid #17150f;background:#dedad0;padding:28px 32px;
        box-shadow:4px 4px 0 0 #17150f;text-align:center;max-width:360px}}
  .msg{{color:{color};font-weight:700;text-transform:uppercase;
       letter-spacing:.08em;font-size:13px;line-height:1.5}}
</style></head><body>
<div class="card"><div class="msg">{message}</div></div>
<script>
  try {{ window.opener && window.opener.postMessage(
    {{ source: 'voicecut-drive', ok: {str(ok).lower()} }}, '*'); }} catch (e) {{}}
  setTimeout(function(){{ window.close(); }}, {'1200' if ok else '3000'});
</script></body></html>"""
    return HTMLResponse(html)
