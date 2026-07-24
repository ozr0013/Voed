"""Thin async client for a local Ollama daemon.

All Gemma calls (planner, verifier) go through here. Two design rules matter for
this project:

1. Byte-stable prefixes: callers pass a static `system` string and a static
   schema; only the trailing user content changes. Ollama keys its prefix/KV
   cache on the exact prompt bytes, so keeping the system prompt identical across
   calls is what makes repeated planning fast.
2. Structured output: we pass a JSON schema via the `format` field so the model
   can only emit a valid action object.
"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import settings
from .model_state import get_active_model


class OllamaError(RuntimeError):
    pass


async def is_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(f"{settings.ollama_url}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def has_model(tag: str | None = None) -> bool:
    tag = tag or get_active_model()
    try:
        models = await list_models()
    except httpx.HTTPError:
        return False
    # Ollama reports tags with an implicit ":latest"; match loosely.
    wanted = tag if ":" in tag else f"{tag}:latest"
    return any(m == tag or m == wanted for m in models)


async def pull_model(tag: str) -> AsyncIterator[dict[str, Any]]:
    """Stream Ollama pull progress (newline-delimited JSON objects)."""
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_url}/api/pull",
                json={"name": tag, "stream": True},
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    yield json.loads(line)
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama pull failed: {e}") from e


async def delete_model(tag: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.request(
                "DELETE",
                f"{settings.ollama_url}/api/delete",
                json={"name": tag},
            )
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama delete failed: {e}") from e


def _encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


async def generate(
    *,
    system: str,
    prompt: str,
    images: list[bytes] | None = None,
    json_schema: dict[str, Any] | None = None,
    max_tokens: int = 250,
    temperature: float = 0.0,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """One-shot generation. Returns the parsed JSON dict from `/api/generate`.

    `system` and `json_schema` should be constant per call-site to preserve the
    prompt cache. Dynamic content goes in `prompt` and `images`.
    """
    payload: dict[str, Any] = {
        "model": get_active_model(),
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if images:
        payload["images"] = [_encode_image(b) for b in images]
    if json_schema is not None:
        payload["format"] = json_schema

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{settings.ollama_url}/api/generate", json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:  # noqa: PERF203
        raise OllamaError(f"Ollama request failed: {e}") from e


async def generate_stream(
    *,
    system: str,
    prompt: str,
    images: list[bytes] | None = None,
    json_schema: dict[str, Any] | None = None,
    max_tokens: int = 250,
    temperature: float = 0.0,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """Streaming generation: yields response text chunks as Ollama produces them.

    Same request shape as `generate` but with `stream: true`. Ollama returns
    newline-delimited JSON objects, each carrying a `response` token fragment and
    a final `done: true`. Used to surface the planner's reasoning live.
    """
    payload: dict[str, Any] = {
        "model": get_active_model(),
        "system": system,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if images:
        payload["images"] = [_encode_image(b) for b in images]
    if json_schema is not None:
        payload["format"] = json_schema

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{settings.ollama_url}/api/generate", json=payload
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    frag = obj.get("response")
                    if frag:
                        yield frag
                    if obj.get("done"):
                        break
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama stream failed: {e}") from e
