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


class CropAspect(str, Enum):
    square = "square"
    portrait = "portrait"
    landscape = "landscape"


class ActionName(str, Enum):
    # --- structural / timeline ---
    trim = "trim"
    cut_range = "cut_range"
    mute_range = "mute_range"
    split = "split"
    remove_silence = "remove_silence"
    reorder_clips = "reorder_clips"
    delete_clip = "delete_clip"
    seek_preview = "seek_preview"
    # --- text on screen ---
    add_caption = "add_caption"
    add_text = "add_text"
    add_subtitles = "add_subtitles"
    # --- audio ---
    change_volume = "change_volume"
    silence_audio = "silence_audio"
    # --- speed ---
    change_speed = "change_speed"
    # --- transitions / fades ---
    fade_in = "fade_in"
    fade_out = "fade_out"
    # --- colour / style ---
    grayscale = "grayscale"
    sepia = "sepia"
    invert_colors = "invert_colors"
    adjust_color = "adjust_color"
    blur = "blur"
    sharpen = "sharpen"
    vignette = "vignette"
    # --- geometry ---
    rotate = "rotate"
    flip = "flip"
    crop = "crop"
    resize = "resize"
    # --- lifecycle / meta ---
    undo = "undo"
    remove_effects = "remove_effects"
    export = "export"
    ask_user = "ask_user"
    task_complete = "task_complete"
    task_failed = "task_failed"


class Action(BaseModel):
    name: ActionName
    # ranges / timing (seconds)
    start_s: float | None = None
    end_s: float | None = None
    duration_s: float | None = None
    # clip targeting / ordering
    clip_id: str | None = None
    position: int | None = None
    # text
    text: str | None = None
    align: str | None = None      # top | center | bottom
    size: str | None = None       # small | medium | large
    color: str | None = None      # e.g. white, yellow, #ffcc00
    # numeric knobs
    factor: float | None = None       # speed / volume multiplier
    brightness: float | None = None   # -1..1  (0 = neutral)
    contrast: float | None = None     # 0..3   (1 = neutral)
    saturation: float | None = None   # 0..3   (1 = neutral)
    amount: float | None = None       # blur sigma / generic strength
    degrees: int | None = None        # rotate: 90 | 180 | 270 (alias: angle)
    angle: int | None = None          # rotate: 90 | 180 | 270 (preferred name)
    direction: str | None = None      # flip: horizontal | vertical
    # geometry
    aspect: CropAspect | None = None  # crop: square | portrait | landscape
    height: int | None = None         # resize target height
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None
    # meta
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
                "duration_s": {"type": "number"},
                "clip_id": {"type": "string"},
                "position": {"type": "integer"},
                "text": {"type": "string"},
                "align": {"type": "string", "enum": ["top", "center", "bottom"]},
                "size": {"type": "string", "enum": ["small", "medium", "large"]},
                "color": {"type": "string"},
                "factor": {"type": "number"},
                "brightness": {"type": "number"},
                "contrast": {"type": "number"},
                "saturation": {"type": "number"},
                "amount": {"type": "number"},
                "degrees": {"type": "integer", "enum": [90, 180, 270]},
                "angle": {"type": "integer", "enum": [90, 180, 270]},
                "direction": {"type": "string", "enum": ["horizontal", "vertical"]},
                "aspect": {"type": "string", "enum": ["square", "portrait", "landscape"]},
                "height": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "w": {"type": "integer"},
                "h": {"type": "integer"},
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
