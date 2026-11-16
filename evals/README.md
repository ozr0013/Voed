# VoiceCut evals

Reproducible, model-agnostic evals for the plan → act loop. Everything runs against the
**real** planner, edit engine and ffmpeg; nothing is mocked except the browser screenshot
(see Limitations).

```bash
# from the repo root, with the project venv
python -m evals.run --suite selftest              # are the oracles trustworthy? (no LLM)
python -m evals.run --suite exec                  # engine correctness (no LLM)
python -m evals.run --suite planner --agent gold  # harness self-test (no LLM)
python -m evals.run --suite planner --model gemma3:4b   # the real eval (needs Ollama)
python -m evals.run --suite planner --model gemma3:4b --screenshot blank   # ablation
python -m evals.compare evals/results/A.json evals/results/B.json
python -m unittest evals.test_scoring
```

Evals run in an isolated temp DB/storage dir, so they never touch your projects.
`--only <substr>` filters cases; `--fail-under 0.9` makes the run exit 1 below that outcome
rate (CI gate). `VOICECUT_EVAL_KEEP=1` keeps the temp dir (rendered videos) for debugging.

## How it works

A 20 s synthetic fixture (640x360, 440 Hz tone, silent from 8-11 s, optional word-level
transcript) is turned into a project the same way `upload.py` does it. Each case then:

1. optionally applies `prior` gold actions through the engine (e.g. split, to get 2 clips),
2. asks the agent for an action (planner suite) or applies a gold action (exec suite),
3. executes it with `engine.apply_action` (real ffmpeg render),
4. checks the **rendered file** with deterministic oracles: ffprobe duration/dimensions,
   RMS loudness in a time window, frame-level checks (grayscale, invert, flip, sepia, blur,
   brightness, "pixels changed in this region/time").

The oracle is what makes this honest: a case passes only if the *video is actually right*,
not because the model said so. Planner cases also score the **action chosen** against a list
of acceptable alternatives (`cut_range 0-10` and `trim 10-20` are both correct for "cut the
first ten seconds"), so you can see *outcome pass* vs *action match* separately.

## Suites and metrics

| Suite | What it tests | Needs LLM |
|---|---|---|
| `selftest` | Every oracle **rejects a do-nothing run** (an oracle a no-op can pass is meaningless) | no |
| `exec` | Gold action → engine → oracle. Validates engine + oracles | no |
| `planner` | Goal + state + screenshot → planner → engine → oracle | yes (or `--agent gold`) |

Planner categories: cut, cut-semantic (uses transcript), mute-vs-cut (guardrail), audio,
speed, text, fade, style, geometry, structure (clip ids), meta (undo), **behavior** (vague /
unsupported / out-of-range requests must not edit), **safety** (prompt injection inside the
transcript must not change the plan), **multi-step** (closed loop up to `--max-steps`).

Reported per category: outcome pass rate, action match rate, schema-valid rate, forbidden-action
hits, planner latency p50/p95, and **Wilson 95% confidence intervals**. With ~3-10 cases per
category the intervals are wide (3/3 is "44-100%"): treat per-category numbers as smoke
signals and only believe a model-vs-model gap when the intervals don't overlap.

## Adding a case

Append to `cases.json`. Planner case = `goal`, `gold` (reference solution, used by the gold agent),
`expect` (`any_of` action alternatives with optional `params`/`tol`, `forbid`, `forbid_edits`, or
`all_of` for multi-step), and `assert` (oracle list). Then run `selftest` and `--agent gold`: a new case
must be rejected by the no-op agent and passed by the gold agent before it's worth trusting.

## Gotchas when running against Ollama

- **Thinking models vs `planner_max_tokens`.** The app caps generation at 250 tokens. A model that
  "thinks" (e.g. `gemma4:12b`, capability `thinking`) spends part of that budget on reasoning, hits
  `done_reason=length`, and returns empty or truncated JSON. On one machine this made the default
  config score 37% (16/43 schema-valid) while the same model finished cleanly at 1500 tokens. If
  `schema-valid` is far below 100%, check this before blaming the model:
  `VOICECUT_PLANNER_MAX_TOKENS=1500 python -m evals.run --suite planner --model <tag>`.
- **Infra errors are not model failures.** If Ollama drops mid-run, transport errors are retried 3x
  and then excluded from every rate (reported as `infra errors (excluded)`).
- **Run on an idle machine, one model at a time.** CPU inference is slow (12B: ~20-30 s per call), and
  concurrent runs distort latency numbers.
- A model that scores *better* with `--screenshot blank` is not using the image.

## Limitations (read before quoting numbers)

- **Synthetic screenshot.** Headless runs can't use the app's html2canvas capture, so
  `render_screenshot` draws an approximation of the editor (preview readout, clip blocks labelled with
  source ranges, muted badges, playhead, captions lane). `--screenshot blank` measures how much the
  model actually relies on the image. Treat results as planner-on-state, not a UI test.
- **No VLM verifier.** The verify step is not evaluated here; planner + engine only. Next step: score
  the verifier's verdict against these same oracles (ground truth) to get its precision/recall.
- **Small n, one fixture, temperature 0.** Not a benchmark; no variance across fixtures or samples yet.
- Gold-agent passing proves the cases are *solvable and checkable*, not that they are *hard*.
