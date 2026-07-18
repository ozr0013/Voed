"""Planner: screenshot + goal + timeline state -> next Action (via Gemma)."""
from __future__ import annotations

import json
import time

from .. import ollama_client
from ..config import settings
from ..models import Project
from . import prompts
from .schemas import PlannerOutput


def state_summary(project: Project) -> str:
    """Compact, text description of the current timeline for the planner."""
    lines = [
        f"timeline_duration_s: {project.timeline_duration_s:.2f}",
        f"source_duration_s: {project.duration_s:.2f}",
        f"transcript_status: {project.transcript_status}",
        f"clips ({len(project.clips)}):",
    ]
    for i, c in enumerate(project.clips):
        cap = f' caption="{c.caption_text}"' if c.caption_text else ""
        lines.append(
            f"  [{i}] id={c.id} {c.src_start_s:.2f}-{c.src_end_s:.2f}s"
            f" ({c.duration_s:.2f}s){cap}"
        )
    return "\n".join(lines)


def transcript_window(project: Project, goal: str) -> str | None:
    """A relevant slice of the video transcript for semantic commands.

    Milestone 8 makes this smart (search words by the goal's content terms). For
    now, if a word-level transcript exists, provide a compact time-tagged view.
    """
    words = project.transcript or []
    if not words:
        return None
    # Group words into ~5s buckets to keep the prompt small.
    buckets: dict[int, list[str]] = {}
    for w in words:
        b = int(w.get("start", 0) // 5) * 5
        buckets.setdefault(b, []).append(str(w.get("word", "")).strip())
    lines = [f"[{t}-{t + 5}s] {' '.join(ws)}" for t, ws in sorted(buckets.items())]
    return "\n".join(lines[:40])  # cap size


async def plan(
    *,
    project: Project,
    goal: str,
    screenshot: bytes,
    first_call: bool,
    completed_steps: list[str] | None = None,
    last_verify: str | None = None,
) -> tuple[PlannerOutput, int, str]:
    """Run one planner call. Returns (parsed output, latency_ms, raw_response)."""
    from .schemas import PLANNER_JSON_SCHEMA

    user_prompt = prompts.build_planner_prompt(
        goal=goal,
        state_summary=state_summary(project),
        transcript_window=transcript_window(project, goal),
        completed_steps=completed_steps,
        last_verify=last_verify,
        first_call=first_call,
    )

    t0 = time.time()
    resp = await ollama_client.generate(
        system=prompts.PLANNER_SYSTEM,
        prompt=user_prompt,
        images=[screenshot],
        json_schema=PLANNER_JSON_SCHEMA,
        max_tokens=settings.planner_max_tokens,
        temperature=0.0,
    )
    latency_ms = int((time.time() - t0) * 1000)

    raw = resp.get("response", "")
    data = json.loads(raw)
    output = PlannerOutput.model_validate(data)
    return output, latency_ms, raw
