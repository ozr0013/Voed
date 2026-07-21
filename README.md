<div align="center">

<img width="412" height="416" alt="Voed logo" src="https://github.com/user-attachments/assets/4016393b-b76a-4682-ad2b-d802debbf48f" />

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=32&pause=1000&color=F75C7E&center=true&vCenter=true&width=600&lines=Voed+%F0%9F%8E%99%EF%B8%8F%E2%9C%82%EF%B8%8F;You+talk.+It+edits.;100%25+local.+0%25+cloud.;%F0%9F%A5%87+1st+Place+%E2%80%94+Multimodal+Track)](https://git.io/typing-svg)

![Status](https://img.shields.io/badge/status-shipped-brightgreen?style=for-the-badge&logo=checkmarx)
![Runs Locally](https://img.shields.io/badge/runs-100%25%20locally-blueviolet?style=for-the-badge&logo=ollama)
![Eval Pass Rate](https://img.shields.io/badge/eval%20pass%20rate-100%25-success?style=for-the-badge&logo=target)
[![Live Demo](https://img.shields.io/badge/live%20demo-voed1.vercel.app-orange?style=for-the-badge&logo=vercel)](https://voed1.vercel.app/)

![wave divider](https://capsule-render.vercel.app/api?type=waving&height=120&color=gradient&customColorList=6,11,20&section=header&text=&fontSize=0)

</div>

You talk, it edits. Hold the mic, say "cut the first ten seconds" or "remove all the silences," and Voed actually does it — no timeline dragging, no keyboard shortcuts to memorize. Everything runs on your own machine. No cloud, no API keys, no internet required.

Under the hood, a multimodal model *looks at your screen*, figures out what you mean, runs the edit with real ffmpeg calls, checks the result against what you asked for, and tells you it's done. Out loud.

We built this for the Multimodal Track and walked away with 1st place.

## Why this isn't just "Whisper + ffmpeg"

Lots of voice-to-action demos fake the "AI actually did something" part. Ours doesn't. Every command has to clear four bars or it doesn't count:

1. **You actually said it out loud** — real mic input, real STT.
2. **The model actually sees the screen** — a live screenshot goes into the planner every time, not just the transcript.
3. **A real action happens on disk** — ffmpeg re-renders the file, the timeline updates. Not a mocked state change.
4. **You get proof it worked** — spoken confirmation + the UI reflecting the new state, verified by a second screenshot pass.

That loop — plan → act → re-check the screen → confirm — is the whole point of the project.

<div align="center">

```mermaid
sequenceDiagram
    autonumber
    participant You
    participant Mic as 🎙️ Mic
    participant Model as 🧠 Gemma (Ollama)
    participant Editor as 🎬 ffmpeg / Timeline
    You->>Mic: "cut the first ten seconds"
    Mic->>Model: transcript + live screenshot
    Model->>Editor: plan → cut_range
    Editor-->>Model: new screenshot (re-check)
    Model-->>You: 🔊 "Done — trimmed to 0:10"
```

</div>

## What's running under the hood

| Piece | Tool |
|---|---|
| Vision + planning | Gemma (multimodal) via **Ollama** |
| Speech-to-text | **faster-whisper** (small) |
| Text-to-speech | **Piper** |
| Video processing | **ffmpeg / ffprobe** |
| Backend | **FastAPI** |
| Frontend | **React + Vite + TypeScript + Tailwind** |
| Storage | **SQLite** (SQLAlchemy) |

### Model

We default to `gemma4:12b` (Q4 quant, ~7.5 GB, ships with a vision projector so it can actually read the editor screen). Swap in something lighter for dev work:

```bash
ollama pull gemma4:12b          # first run only, ~7.5 GB
VOICECUT_MODEL=gemma3:4b ./start.sh   # lighter model for local dev
```

Whichever tag is active shows up on the health screen and gets logged on every planner/verifier call — no guessing what model made a given edit.

## Getting it running

You'll need [ffmpeg](https://ffmpeg.org/download.html), [Ollama](https://ollama.com) running locally, **Python 3.10** (not 3.11+ — `piper-tts` won't install on newer Pythons), and Node 18+.

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File .\start.ps1

# macOS / Linux / Git-Bash / WSL
./start.sh
```

One command. It checks your dependencies, pulls the model if it's missing, installs both the backend and frontend, spins up both servers, and prints the LAN URL. Open it in **Chrome** — works across any machine on your network, not just localhost.

## Your data never leaves your machine

- **In:** your mic audio and whatever video you upload.
- **Processed:** entirely locally — Whisper for STT, Gemma via Ollama for planning/vision/verification, Piper for TTS, ffmpeg for rendering.
- **Stored:** account and project metadata in a local SQLite file; your videos live on local disk under `storage/`.
- **Sent out to the internet:** nothing. No cloud APIs, no keys, no telemetry. Kill your wifi and it still works — the only traffic is to your local Ollama daemon and, optionally, over your LAN so teammates or judges can open it from another machine.

## How it's wired together

```
              ┌─────────────────────────── Browser (Chrome) ───────────────────────────┐
              │  MicButton ──hold──> MediaRecorder ──webm──> /stt                        │
              │  Editor (Timeline + VideoPreview + AgentPanel)                           │
              │  screenshot.ts ──PNG of live editor──> agent loop                        │
              └───────────────▲───────────────────────────────────┬─────────────────────┘
                              │ WebSocket (agent events, per-step) │ HTTP (auth, upload, stt, tts)
              ┌───────────────┴───────────────────────────────────▼─────────────────────┐
              │ FastAPI backend                                                          │
              │   auth · upload(ffprobe) · transcribe(whisper) · stt · tts(piper)        │
              │   agent loop:  plan ─> act(edit engine / ffmpeg) ─> verify               │
              │        planner  ──screenshot+goal+state──>  Gemma (Ollama)               │
              │        verifier ──screenshot+expected──>    Gemma (Ollama)               │
              │   SQLite (users, projects, clips, edit versions, agent runs/steps)       │
              │   storage/ (originals, proxies, rendered edit versions)                  │
              └──────────────────────────────────────────────────────────────────────────┘
```

## Where we landed

![progress](https://progress-bar.xyz/100/?title=Milestones%20shipped&width=500&color=6c5ce7)

- [x] M1 — scaffold, health checks, FastAPI + Vite wiring
- [x] M2 — auth + dashboard + upload
- [x] M3 — editor page (static)
- [x] M4 — STT + mic + TTS ack
- [x] M5 — screenshot capture + planner
- [x] M6 — edit engine trim/cut_range (**end-to-end gate passed**)
- [x] M7–M12 — multi-step loop, transcription, more edit types, failure handling, evals, polish

**The gate that mattered:** you speak → a live `html2canvas` screenshot goes to `gemma4:12b` → it returns a `cut_range` plan → ffmpeg renders a real, frame-accurate cut on disk → the timeline updates → a fresh screenshot goes back to `gemma4:12b` to verify the change actually happened → you get a spoken + on-screen ✓. Warm latency on our dev machine (CPU, no GPU): ~9s to plan, ~3.7s to verify.

**Evals:** 15 voice commands across cuts, trims, mute ranges, timeline seeks, crops, and rotations — 100% success rate, all on CPU. Full breakdown and known edge cases are in the Kaggle writeup.

> **Why html2canvas and not html-to-image:** html-to-image round-trips through an SVG `<img>` that never fires `onload` in some automated Chromium builds, so it just hangs. html2canvas paints the DOM straight to a canvas and doesn't have that problem.

<div align="center">

![wave divider](https://capsule-render.vercel.app/api?type=waving&height=100&color=gradient&customColorList=6,11,20&section=footer&text=&fontSize=0)

Built with 🎙️, ffmpeg, and way too much CPU-bound inference — **JustBuild Hackathon, Multimodal Track, 🥇 1st Place**

</div>
