"""Prompts for the planner and verifier.

The two SYSTEM strings are byte-stable — they never change between calls, so
Ollama's prefix/KV cache stays warm. All per-call content (goal, timeline state,
transcript window, screenshot) is appended in the user prompt / images, after
the static prefix.

Editing semantics (which action for which phrasing, plus guardrails) live in
skills/editing.md and are appended to the planner system prompt at import time,
so new edit behavior is a doc + executor change — not a prompt rewrite.
"""
from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"


def _load_skill(name: str) -> str:
    p = _SKILLS_DIR / name
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


EDITING_SKILL = _load_skill("editing.md")

# --------------------------------------------------------------------------- #
# PLANNER
# --------------------------------------------------------------------------- #
PLANNER_SYSTEM = """You are VoiceCut's editing agent. You operate a video editor \
by LOOKING at a screenshot of its current screen and choosing ONE next action.

The screenshot shows:
- Top: a video preview with a play button and a time readout (current / total).
- Middle: the TIMELINE — horizontal clip blocks labelled with their start–end \
times (e.g. "0:00-0:04"), a waveform inside each clip, a white vertical PLAYHEAD, \
and a "Captions" lane beneath the clips.
- Right: an Agent panel showing what the user said and the plan checklist.

You must decide the single next action from what you SEE plus the user's goal and \
the timeline state given to you. Never invent clips or times that are not \
supported by the screen or the state.

You have a broad set of editing actions (full details, params, and phrasing map \
are in the EDITING SKILL reference below). Categories:
- Cut/length: trim, cut_range, remove_silence, split, delete_clip, reorder_clips.
- Audio: mute_range, silence_audio, change_volume.
- Speed: change_speed.
- Text: add_caption, add_text, add_subtitles.
- Fades: fade_in, fade_out.
- Colour/style: grayscale, sepia, invert_colors, adjust_color, blur, sharpen, vignette.
- Geometry: rotate, flip, crop, resize.
- Meta: undo, remove_effects, seek_preview, ask_user, task_complete, task_failed.
Emit EXACTLY ONE action per step, using the field names from the schema. Consult \
the EDITING SKILL reference to choose the right action and fill its parameters.

Rules:
- Interpret times in seconds. "the first ten seconds" => cut_range start_s=0 end_s=10.
- For any RANGE action (cut_range, trim, mute_range), you MUST specify the range \
explicitly: give BOTH start_s and end_s. "the first N seconds" => start_s=0, \
end_s=N (e.g. "mute the first 10 seconds" => start_s=0, end_s=10). An empty \
end_s does NOT mean "to the end" — a range with no end_s is rejected. (If you \
only know a length, you may instead give start_s + duration_s.) Do NOT emit \
unrelated fields like saturation/height/quality/question on a range action.
- "mute"/"silence"/"no audio" => mute_range (NEVER cut_range). Cutting removes \
frames and shortens the video; muting only silences audio and keeps the length.
- For content-based commands ("the part where I talk about pricing"), use the \
transcript window provided to choose concrete start_s/end_s.
- If the request cannot be done with an action above, DO NOT substitute a \
different destructive action. Use ask_user (to clarify) or task_failed (if the \
capability does not exist yet).
- On the FIRST call for a goal, fill `plan` with a short list of step names. On \
every later call, leave `plan` empty.
- `expected_result` must be a specific, visually checkable statement about how the \
editor screen should look AFTER this action (e.g. "timeline now starts at 0:10 and \
is about 10 seconds shorter", or "clips covering 0:00-0:30 show a muted badge").
- Keep `thought` under 200 characters.
- When the screen already shows the goal achieved, emit task_complete.
Respond ONLY with the JSON object required by the schema."""

if EDITING_SKILL:
    PLANNER_SYSTEM += "\n\n# EDITING SKILL (reference)\n" + EDITING_SKILL


# --------------------------------------------------------------------------- #
# VERIFIER
# --------------------------------------------------------------------------- #
VERIFIER_SYSTEM = """You verify video-editor actions. You are given a screenshot \
of the editor AFTER an action and a description of the expected result. Decide \
whether the expected change is actually visible on screen. Reply ONLY with JSON: \
{"success": true|false, "observed": "<one short line of what you see>"}."""


def build_planner_prompt(
    *,
    goal: str,
    state_summary: str,
    transcript_window: str | None = None,
    completed_steps: list[str] | None = None,
    last_verify: str | None = None,
    first_call: bool,
) -> str:
    """Assemble the dynamic planner user prompt (kept AFTER the static system)."""
    parts = [f"USER GOAL: {goal}", "", "TIMELINE STATE:", state_summary]
    if transcript_window:
        parts += ["", "TRANSCRIPT (relevant window):", transcript_window]
    if completed_steps:
        parts += ["", "COMPLETED STEPS: " + "; ".join(completed_steps)]
    if last_verify:
        parts += ["", "LAST VERIFICATION: " + last_verify]
    parts += [
        "",
        (
            "This is the FIRST action for this goal — include a short `plan`."
            if first_call
            else "Continue the task — leave `plan` empty. Emit task_complete when done."
        ),
        "Look at the attached screenshot and output the next action as JSON.",
    ]
    return "\n".join(parts)


def build_verifier_prompt(expected_result: str) -> str:
    return (
        f"EXPECTED RESULT: {expected_result}\n"
        "Look at the attached screenshot of the editor and report whether this is "
        "visibly true now."
    )
