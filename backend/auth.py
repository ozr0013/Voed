"""Minimal email + password auth.

Deliberately small: bcrypt password hashing, a JWT stored in an httpOnly cookie,
no email verification / OAuth / password reset. It exists to prove VoiceCut is a
real multi-user product, not to consume build time.
"""
from __future__ import annotations

from datetime import timedelta

import re
import secrets

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Google OAuth (reuses the same client as the Drive export integration).
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# --- password + token helpers ---
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "iat": utcnow()}
    exp = utcnow() + timedelta(hours=settings.jwt_ttl_hours)
    payload["exp"] = exp
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_ttl_hours * 3600,
        path="/",
    )


# --- current-user dependency ---
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid session") from None
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Account not found")
    return user


# --- schemas ---
# Deliberately permissive: a demo user should be able to sign up with any
# reasonable-looking address (including throwaway .local domains) without a
# deliverability check. Just enough shape to catch obvious typos.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class UserOut(BaseModel):
    id: int
    email: str


# --- routes ---
@router.post("/signup", response_model=UserOut)
def signup(
    creds: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    existing = db.scalar(select(User).where(User.email == creds.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=creds.email.lower(), password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    _set_cookie(response, make_token(user.id))
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut)
def login(
    creds: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    user = db.scalar(select(User).where(User.email == creds.email.lower()))
    if not user or not verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    _set_cookie(response, make_token(user.id))
    return UserOut(id=user.id, email=user.email)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email)


# --- Sign in with Google ---
def _sign_login_state() -> str:
    payload = {"purpose": "google_login", "exp": utcnow() + timedelta(minutes=10)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _valid_login_state(state: str) -> bool:
    try:
        payload = jwt.decode(
            state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload.get("purpose") == "google_login"
    except jwt.PyJWTError:
        return False


def _find_or_create_google_user(db: Session, email: str) -> User:
    """Match an existing account by email, or create a passwordless one.

    OAuth accounts get a random unguessable password hash so the password login
    path can never authenticate them — sign-in is only ever via Google.
    """
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.get("/google/available")
def google_available() -> dict:
    """Public: lets the sign-in page decide whether to show the Google button."""
    return {"configured": settings.google_drive_configured}


@router.get("/google/login")
def google_login() -> RedirectResponse:
    """Kick off the OAuth dance: redirect the browser to Google's consent screen."""
    if not settings.google_drive_configured:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_login_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "state": _sign_login_state(),
    }
    return RedirectResponse(str(httpx.URL(_GOOGLE_AUTH_URL, params=params)))


@router.get("/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Google redirects here with an auth code; exchange it, then start a session.

    On any failure we bounce back to /signin rather than showing a raw error,
    since this is a full-page navigation, not an API call.
    """
    if error or not code or not state or not _valid_login_state(state):
        return RedirectResponse("/signin?error=google")

    token_resp = httpx.post(
        _GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "redirect_uri": settings.google_login_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if token_resp.status_code != 200:
        return RedirectResponse("/signin?error=google")

    access_token = token_resp.json().get("access_token")
    email = None
    if access_token:
        try:
            info = httpx.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if info.status_code == 200:
                email = info.json().get("email")
        except httpx.HTTPError:
            pass
    if not email:
        return RedirectResponse("/signin?error=google")

    user = _find_or_create_google_user(db, email)
    resp = RedirectResponse("/dashboard")
    _set_cookie(resp, make_token(user.id))
    return resp
