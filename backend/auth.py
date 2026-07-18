"""Minimal email + password auth.

Deliberately small: bcrypt password hashing, a JWT stored in an httpOnly cookie,
no email verification / OAuth / password reset. It exists to prove VoiceCut is a
real multi-user product, not to consume build time.
"""
from __future__ import annotations

from datetime import timedelta

import re

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
