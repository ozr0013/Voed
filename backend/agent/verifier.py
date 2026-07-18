"""Verifier: screenshot + expected_result -> {success, observed} (via Gemma).

Uses a separate, minimal prompt and a tiny token budget — this is the cheap
visual confirmation pass after each action.
"""
from __future__ import annotations

import json
import time

from .. import ollama_client
from ..config import settings
from . import prompts
from .schemas import VERIFIER_JSON_SCHEMA, VerifierOutput


async def verify(
    *, expected_result: str, screenshot: bytes
) -> tuple[VerifierOutput, int]:
    t0 = time.time()
    resp = await ollama_client.generate(
        system=prompts.VERIFIER_SYSTEM,
        prompt=prompts.build_verifier_prompt(expected_result),
        images=[screenshot],
        json_schema=VERIFIER_JSON_SCHEMA,
        max_tokens=settings.verifier_max_tokens,
        temperature=0.0,
    )
    latency_ms = int((time.time() - t0) * 1000)
    data = json.loads(resp.get("response", "{}"))
    return VerifierOutput.model_validate(data), latency_ms
