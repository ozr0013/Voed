"""Model catalog, download, and selection API."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import ollama_client
from .model_catalog import GEMMA4_CATALOG, is_catalog_tag
from .model_state import get_active_model, set_active_model

router = APIRouter(prefix="/api/models", tags=["models"])


class SelectModelBody(BaseModel):
    tag: str


class PullModelBody(BaseModel):
    tag: str


def _normalize_installed(tags: list[str]) -> set[str]:
    out: set[str] = set()
    for t in tags:
        out.add(t)
        if ":" not in t:
            out.add(f"{t}:latest")
        elif t.endswith(":latest"):
            out.add(t[: -len(":latest")])
    return out


def _is_installed(tag: str, installed: set[str]) -> bool:
    wanted = tag if ":" in tag else f"{tag}:latest"
    bare = tag.split(":")[0] if ":" in tag else tag
    return (
        tag in installed
        or wanted in installed
        or f"{bare}:latest" in installed
        or bare in installed
    )


@router.get("")
async def list_models_api() -> dict:
    active = get_active_model()
    ollama_up = await ollama_client.is_up()
    installed_raw: list[str] = []
    if ollama_up:
        try:
            installed_raw = await ollama_client.list_models()
        except Exception:  # noqa: BLE001
            installed_raw = []
    installed_set = _normalize_installed(installed_raw)

    catalog = []
    for entry in GEMMA4_CATALOG:
        catalog.append(
            {
                **entry.__dict__,
                "installed": _is_installed(entry.tag, installed_set),
                "active": entry.tag == active,
            }
        )

    return {
        "active": active,
        "ollama_up": ollama_up,
        "catalog": catalog,
        "installed": sorted(installed_raw),
    }


@router.post("/select")
async def select_model(body: SelectModelBody) -> dict:
    tag = body.tag.strip()
    if not is_catalog_tag(tag):
        raise HTTPException(400, f"Unknown model tag: {tag}")
    if not await ollama_client.is_up():
        raise HTTPException(503, "Ollama is not running")
    if not await ollama_client.has_model(tag):
        raise HTTPException(400, f"Model not installed: {tag}. Download it first.")
    active = set_active_model(tag)
    return {"ok": True, "active": active}


async def _pull_stream(tag: str) -> AsyncIterator[bytes]:
    try:
        async for event in ollama_client.pull_model(tag):
            yield (json.dumps(event) + "\n").encode("utf-8")
    except ollama_client.OllamaError as e:
        yield (json.dumps({"status": "error", "error": str(e)}) + "\n").encode("utf-8")


@router.post("/pull")
async def pull_model(body: PullModelBody) -> StreamingResponse:
    tag = body.tag.strip()
    if not is_catalog_tag(tag):
        raise HTTPException(400, f"Unknown model tag: {tag}")
    if not await ollama_client.is_up():
        raise HTTPException(503, "Ollama is not running")
    return StreamingResponse(
        _pull_stream(tag),
        media_type="application/x-ndjson",
    )


@router.delete("/{tag:path}")
async def delete_model(tag: str) -> dict:
    tag = tag.strip()
    if not is_catalog_tag(tag):
        raise HTTPException(400, f"Unknown model tag: {tag}")
    if not await ollama_client.is_up():
        raise HTTPException(503, "Ollama is not running")
    if tag == get_active_model():
        raise HTTPException(400, "Cannot delete the active model. Select another model first.")
    try:
        await ollama_client.delete_model(tag)
    except ollama_client.OllamaError as e:
        raise HTTPException(502, str(e)) from e
    return {"ok": True, "deleted": tag}
