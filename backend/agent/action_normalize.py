"""Fill missing time ranges on planner actions from the user's goal text.

Gemma often emits mute_range/cut_range/trim with no start_s/end_s/duration_s while
filling unrelated schema fields (saturation, height, question, …). The spoken
goal still contains the range ("mute the first 10 seconds"), so we infer it
before executing rather than failing or muting the whole timeline.
"""
from __future__ import annotations

import re

from .schemas import Action, ActionName

_RANGE_ACTIONS = frozenset({ActionName.cut_range, ActionName.trim, ActionName.mute_range})

_FIRST_SECONDS = re.compile(
    r"\bfirst\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b",
    re.IGNORECASE,
)
_LAST_SECONDS = re.compile(
    r"\blast\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b",
    re.IGNORECASE,
)
_BETWEEN = re.compile(
    r"\b(?:from\s+)?(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)?"
    r"\s*(?:to|[-–—])\s*"
    r"(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)?\b",
    re.IGNORECASE,
)
_MUTE_SECONDS = re.compile(
    r"\b(?:mute|mule|mild|mew|silence|silent|silenced)\b.*?(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b",
    re.IGNORECASE | re.DOTALL,
)
_CUT_SECONDS = re.compile(
    r"\b(?:cut|trim|remove|delete)\b.*?(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b",
    re.IGNORECASE | re.DOTALL,
)


def infer_range_from_text(text: str, *, timeline_duration: float) -> tuple[float, float] | None:
    """Parse common spoken time phrases into [start_s, end_s]."""
    if not (text or "").strip():
        return None

    m = _FIRST_SECONDS.search(text)
    if m:
        end = float(m.group(1))
        return 0.0, end

    m = _BETWEEN.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))

    m = _LAST_SECONDS.search(text)
    if m:
        span = float(m.group(1))
        return max(0.0, timeline_duration - span), timeline_duration

    if re.search(r"\b(?:mute|mule|mild|mew|silence|silent)\b", text, re.IGNORECASE):
        m = _MUTE_SECONDS.search(text) or re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b", text, re.IGNORECASE
        )
        if m:
            return 0.0, float(m.group(1))

    if re.search(r"\b(?:cut|trim|remove|delete)\b", text, re.IGNORECASE):
        m = _CUT_SECONDS.search(text) or re.search(
            r"\b(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b", text, re.IGNORECASE
        )
        if m:
            return 0.0, float(m.group(1))

    return None


def _has_range(action: Action) -> bool:
    return action.end_s is not None or action.duration_s is not None


def normalize_action(
    action: Action,
    *,
    goal: str,
    timeline_duration: float,
) -> Action:
    """Ensure range actions carry start/end before execution."""
    if action.name not in _RANGE_ACTIONS or _has_range(action):
        return action

    for text in (goal, action.text or ""):
        inferred = infer_range_from_text(text, timeline_duration=timeline_duration)
        if inferred is None:
            continue
        start, end = inferred
        end = min(end, timeline_duration)
        if end <= start:
            continue
        return action.model_copy(update={"start_s": start, "end_s": end})

    return action
