# VoiceCut editing skill

Reference for mapping a spoken command to ONE agent action. This file is loaded
into the planner's system prompt, so editing behavior can grow by editing this
doc + adding an executor — not by inventing a new action name for every phrasing.

## Command → action mapping

| The user says (examples)                                  | Action        | Effect on the timeline                    |
| -------------------------------------------------------- | ------------- | ----------------------------------------- |
| "cut / remove / delete the first 10s", "take out 5–8s"   | `cut_range`   | Removes that range. Timeline gets SHORTER. |
| "trim to 10–30s", "keep only the middle", "crop the ends" | `trim`        | Keeps only [start,end]. Timeline gets shorter. |
| "mute / silence / no audio from 0–30s", "kill the sound" | `mute_range`  | Silences audio in that range. Length UNCHANGED. |
| "go to / scrub to / show me 12s"                         | `seek_preview`| Moves the playhead only. No edit.          |

## Critical distinctions (do not confuse)

- **Cut ≠ Mute.** "Mute the first 30 seconds" means silence the AUDIO for
  0–30s while keeping every frame — the video stays the same length. It is NOT
  `cut_range`. If you hear mute / silence / "remove the audio" / "no sound",
  use `mute_range`, never `cut_range`.
- **Trim ≠ Cut.** `trim` KEEPS the given range and drops everything else;
  `cut_range` REMOVES the given range and keeps everything else.

## Times

- Interpret times in seconds. "the first ten seconds" → start_s=0, end_s=10.
- For content-based commands ("the part about pricing"), use the transcript
  window provided to choose concrete start_s/end_s.

## Guardrail: never substitute an unsupported command

If the user's request cannot be expressed with one of the actions listed in the
system prompt, DO NOT approximate it with a different, destructive action.
Instead:

- Ask with `ask_user` when a small clarification would let you proceed.
- Emit `task_failed` (with a brief reason in `expected_result`) when the
  capability genuinely does not exist yet.

Examples of requests to REFUSE rather than fake:

- "add background music", "speed it up 2x", "add a transition", "zoom in",
  "color grade", "rotate 90°" → `task_failed` ("that edit isn't supported yet"),
  unless/until a matching action exists.

It is always better to say "I can't do that yet" than to perform the wrong edit.
