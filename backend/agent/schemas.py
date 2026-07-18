"""Agent action schema.

Two representations, kept in lockstep:
  - Pydantic models (`PlannerOutput`, `Action`) for parsing/validation in Python.
  - `PLANNER_JSON_SCHEMA`, a flat hand-authored JSON Schema passed to Ollama's
    `format` parameter so Gemma can only emit a valid action object. It is kept
    ref-free (no $defs) because that is the most reliable shape for Ollama's
    constrained decoding.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ActionName(str, Enum):
    trim = "trim"
    cut_range = "cut_range"
    mute_range = "mute_range"
    split = "split"
    remove_silence = "remove_silence"
    reorder_clips = "reorder_clips"
    add_caption = "add_caption"
    seek_preview = "seek_preview"
    export = "export"
    delete_clip = "delete_clip"
    ask_user = "ask_user"
    task_complete = "task_complete"
    task_failed = "task_failed"


class Action(BaseModel):
    name: ActionName
    start_s: float | None = None
    end_s: float | None = None
    clip_id: str | None = None
    position: int | None = None
    text: str | None = None
    quality: str | None = None
    question: str | None = None


class PlannerOutput(BaseModel):
    # No length caps: Gemma can write a long `thought`, and the JSON schema sent
    # to Ollama does not constrain it, so a Pydantic cap here would hard-reject
    # otherwise-valid model output (surfacing as a spurious "too long" error).
    thought: str = Field(default="")
    plan: list[str] = Field(default_factory=list)
    action: Action
    expected_result: str = Field(default="")


# Flat JSON schema for Ollama `format`. Mirrors the models above.
PLANNER_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "plan": {"type": "array", "items": {"type": "string"}},
        "action": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": [a.value for a in ActionName],
                },
                "start_s": {"type": "number"},
                "end_s": {"type": "number"},
                "clip_id": {"type": "string"},
                "position": {"type": "integer"},
                "text": {"type": "string"},
                "quality": {"type": "string", "enum": ["1080p", "720p"]},
                "question": {"type": "string"},
            },
            "required": ["name"],
        },
        "expected_result": {"type": "string"},
    },
    "required": ["thought", "action", "expected_result"],
}


class VerifierOutput(BaseModel):
    success: bool
    observed: str = Field(default="")


VERIFIER_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "observed": {"type": "string"},
    },
    "required": ["success", "observed"],
}
