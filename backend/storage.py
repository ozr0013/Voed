"""Filesystem layout helpers. Everything lives under settings.storage_dir.

Paths are stored in the DB relative to storage_dir so the data directory stays
relocatable.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import settings


def project_dir(user_id: int, project_id: int) -> Path:
    p = settings.storage_path / str(user_id) / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_path(user_id: int, project_id: int) -> Path:
    """The project's storage dir WITHOUT creating it (for deletion/inspection)."""
    return settings.storage_path / str(user_id) / str(project_id)


def remove_project_dir(user_id: int, project_id: int) -> None:
    """Delete a project's on-disk files (originals, renders, proxies, shots)."""
    p = project_path(user_id, project_id)
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def tmp_dir() -> Path:
    p = settings.storage_path / "tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def abs_path(rel: str) -> Path:
    return settings.storage_path / rel


def rel_path(abs_p: Path) -> str:
    return str(abs_p.relative_to(settings.storage_path)).replace("\\", "/")
