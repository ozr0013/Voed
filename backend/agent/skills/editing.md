# Editing skill — the actions you can take

You edit by emitting ONE action per step. Pick the action whose meaning matches
the user's request. Read times off the timeline/state; never invent them. If a
request truly has no matching action, use `ask_user` or `task_failed` — never
substitute a different destructive edit.

All times are in seconds of the CURRENT timeline (what you see), not the source.

## Trimming & cutting (change length)
- `cut_range` (start_s, end_s) — remove the range [start_s, end_s]. "delete the
  first 10 seconds" → start_s=0, end_s=10. Shortens the video.
- `trim` (start_s, end_s) — keep ONLY [start_s, end_s], drop everything else.
  "keep just 0:05 to 0:20".
- `remove_silence` — auto-detect and cut every silent gap (uses the waveform).
  "cut the dead air", "remove pauses".
- `split` (start_s) — cut a clip into two at start_s (no content removed). Useful
  before reordering or deleting a piece.
- `delete_clip` (clip_id) — remove one clip block by its id (see the clips list).
- `reorder_clips` (clip_id, position) — move a clip to index `position` (0-based).

## Audio
- `mute_range` (start_s, end_s) — silence AUDIO over a range; video and length are
  unchanged. Use for "mute/silence/no audio HERE". NEVER use cut_range for muting.
- `silence_audio` — silence the ENTIRE video's audio.
- `change_volume` (factor) — factor>1 louder, <1 quieter. "make it twice as loud"
  → factor=2. "quieter" → factor=0.5.

## Speed
- `change_speed` (factor) — factor>1 faster, <1 slower. "2x speed" → factor=2,
  "slow-mo / half speed" → factor=0.5. Changes duration and pitch-corrects audio.

## Text on screen
- `add_caption` (text, start_s, end_s, align?, size?, color?) — burn a caption over
  a time range. Also shows in the Captions lane. align = top|center|bottom.
- `add_text` (text, align?, size?, color?, start_s?, end_s?) — a title/overlay.
  Omit start_s/end_s for the whole video. size = small|medium|large.
- `add_subtitles` — auto-generate & burn subtitles for the WHOLE video from the
  transcript. Requires transcript_status = ready. "add subtitles/captions to everything".

## Fades / transitions
- `fade_in` (duration_s?) — fade from black (and silence) at the start.
- `fade_out` (duration_s?) — fade to black (and silence) at the end.

## Colour & style (whole video)
- `grayscale` — black & white.       - `sepia` — warm vintage tone.
- `invert_colors` — negative.        - `vignette` — darkened edges.
- `sharpen` — crisper.               - `blur` (amount?) — soften/blur.
- `adjust_color` (brightness?, contrast?, saturation?) — brightness -1..1 (0
  neutral), contrast/saturation 0..3 (1 neutral). "brighter" → brightness=0.15,
  "more vivid/punchy" → saturation=1.5, "washed out" → saturation=0.5.

## Geometry
- `rotate` (degrees) — 90 | 180 | 270.
- `flip` (direction) — horizontal | vertical (mirror).
- `resize` (height) — scale to a target height, e.g. 720 or 1080.
- `crop` (w, h, x, y) — crop to a w×h box at (x, y).

## Meta
- `undo` — revert the most recent edit.
- `remove_effects` — strip all colour/text/speed/fade effects (cuts are kept).
- `seek_preview` (start_s) — just move the playhead (no edit).
- `add_caption`/effects stack — you can layer several effects (e.g. grayscale +
  fade_in + a title). Re-emitting the same colour/speed effect just updates it.
- `ask_user` (question) — when the request is ambiguous.
- `task_complete` — when the screen already shows the goal achieved.
- `task_failed` — when no available action can achieve it.

## Guardrails
- One action per step. After a real edit, the timeline re-renders; look again.
- "mute" ≠ "cut". Muting keeps length; cutting removes frames.
- Colour/speed/fade/flip/rotate/crop/resize/volume are single-instance: emitting
  one again replaces the previous setting rather than stacking.
- `expected_result` must be visually checkable on the editor screen.
