"""SQLAlchemy ORM models.

Editing model (non-destructive):
  - The **timeline** is an ordered list of `Clip` rows. Each clip is a segment
    [src_start_s, src_end_s] of the project's original video, optionally with a
    burned caption. Edits mutate these rows.
  - Each render produces an immutable `EditVersion` (a real file on disk) plus a
    JSON snapshot of the clip layout, which gives us free `undo` by pointing the
    project head back one version.
  - The original upload is never modified.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))

    # lifecycle: uploading -> processing -> ready | error
    status: Mapped[str] = mapped_column(String(32), default="uploading")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # media assets (paths relative to storage/)
    original_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    proxy_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    waveform: Mapped[list | None] = mapped_column(JSON, nullable=True)  # peak samples 0..1

    # probed metadata
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0.0)

    # transcription: pending -> processing -> ready | error
    transcript_status: Mapped[str] = mapped_column(String(32), default="pending")
    transcript: Mapped[list | None] = mapped_column(JSON, nullable=True)  # word-level

    # muted audio regions in SOURCE seconds: [{"start": s, "end": e}, ...]. Kept
    # in source time so they survive cuts/trims (which only reslice segments).
    muted_ranges: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Post-concat effects applied at render time, in TIMELINE seconds:
    # [{"type": "grayscale"}, {"type": "text", "text": "...", "start_s", "end_s"},
    #  {"type": "speed", "factor": 2.0}, {"type": "fade_out", "duration_s": 1}, ...].
    # Colour/geometry/speed/volume/fade/caption effects all live here so the agent
    # can grow new skills without new columns. See edits/operations.py.
    effects: Mapped[list | None] = mapped_column(JSON, nullable=True)

    head_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("edit_versions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    @property
    def timeline_duration_s(self) -> float:
        """Length of the current edited timeline (sum of kept clips).

        `duration_s` stays fixed at the source video's length; this shrinks as
        the user cuts. Waveform peaks are indexed against the source duration.
        """
        total = sum(c.duration_s for c in self.clips)
        return total if total > 0 else self.duration_s

    user: Mapped[User] = relationship(back_populates="projects")
    clips: Mapped[list["Clip"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Clip.order_index",
    )
    versions: Mapped[list["EditVersion"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="EditVersion.project_id",
        order_by="EditVersion.version_index",
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # segment into the ORIGINAL source video
    src_start_s: Mapped[float] = mapped_column(Float, default=0.0)
    src_end_s: Mapped[float] = mapped_column(Float, default=0.0)
    caption_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="clips")

    @property
    def duration_s(self) -> float:
        return max(0.0, self.src_end_s - self.src_start_s)


class EditVersion(Base):
    __tablename__ = "edit_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("edit_versions.id"), nullable=True
    )
    version_index: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(255), default="")
    layout: Mapped[list | None] = mapped_column(JSON, nullable=True)  # clip snapshot
    action: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # action that made it
    # full editing state at this version, so `undo` can restore it exactly
    muted_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    effects_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    project: Mapped[Project] = relationship(
        back_populates="versions", foreign_keys=[project_id]
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    goal: Mapped[str] = mapped_column(Text)
    # running -> complete | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_index",
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    verify_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verify_observed: Mapped[str | None] = mapped_column(Text, nullable=True)
    # judge-verifiable evidence: the exact screenshots the model looked at
    screenshot_in_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screenshot_out_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    planner_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verifier_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="steps")


class Integration(Base):
    """A user's connection to an external service (e.g. Google Drive export).

    Stores OAuth tokens so exports can be pushed without re-authorizing each
    time. One row per (user, provider). Tokens are stored as-is in the local
    SQLite file — acceptable for a self-hosted, single-machine app.
    """

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))  # "google_drive"
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
