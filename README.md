# Voed — edit video by talking

A voice-controlled video editing agent that runs **100% locally**. Sign in,
upload a video, hold the mic button, and say things like *"cut the first ten
seconds"* or *"remove all the silences."* A multimodal AI agent looks at a live
screenshot of the editor, plans the edit, performs it with ffmpeg, then
re-checks the screen and speaks confirmation.

Built for the **Multimodal Track**. Every design decision serves the
four eligibility gates: a real spoken request, live screen understanding by a
multimodal model, a real observable computer action (ffmpeg re-renders files on
disk + the timeline updates), and a visible/spoken confirmation that the change
happened.

## Stack (all local, all free)

| Concern            | Tool                                                   |
| ------------------ | ------------------------------------------------------ |
| Planning + vision  | Gemma (multimodal) via **Ollama** — see model note     |
| Speech-to-text     | **faster-whisper** (`small`)                           |
| Text-to-speech     | **Piper**                                              |
| Video processing   | **ffmpeg / ffprobe**                                   |
| Backend            | **FastAPI** (Python)                                   |
| Frontend           | **React + Vite + TypeScript + Tailwind**               |
| Database           | **SQLite** via SQLAlchemy                              |

### Model note

Voed uses **`gemma4:12b`** — Gemma 4 12B multimodal (Q4 quantization by
default), a ~7.5 GB pull that includes a vision projector for screen
understanding. The exact tag in use is shown on the health screen and logged on
every planner/verifier call. Override with the `VOICECUT_MODEL` environment
variable to run a lighter local model during development, e.g. `gemma3:4b`.

```bash
ollama pull gemma4:12b       # ~7.5 GB, first run only
# or, to develop against a smaller model:
VOICECUT_MODEL=gemma3:4b ./start.sh
```

## Setup (one command)

Prerequisites: [ffmpeg](https://ffmpeg.org/download.html),
[Ollama](https://ollama.com) (running), **Python 3.10** (not 3.11+ — `piper-tts`
requires Python <3.11 and will fail to install on newer versions), Node 18+.

```bash
# Windows (PowerShell) — primary:
powershell -ExecutionPolicy Bypass -File .\start.ps1

# macOS / Linux / Git-Bash / WSL:
./start.sh
```

The launcher checks dependencies, pulls the model if missing, installs backend +
frontend deps on first run, starts both servers, and prints the LAN URL. Open the
**App** URL in **Chrome** on any machine on the same network.

## Data-flow / privacy statement

- **What enters the system:** microphone audio (your spoken commands) and the
  video files you upload.
- **Where it is processed:** entirely on the host machine. STT (Whisper), the
  agent's planning/vision/verification (Gemma via Ollama), TTS (Piper), and all
  video rendering (ffmpeg) run as local processes.
- **What is stored:** account rows and project/edit metadata in a local SQLite
  file; uploaded and rendered video files on local disk under `storage/`.
- **What is transmitted externally:** **nothing.** There are no cloud APIs, no
  API keys, and no telemetry. The app works fully with the internet disabled.
  The only network traffic is (a) to the local Ollama daemon and (b) optional
  LAN access so teammates/judges can open the app from another machine.

## Architecture

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

## Build status

- [x] M1 — scaffold, health checks, FastAPI + Vite wiring
- [x] M2 — auth + dashboard + upload
- [x] M3 — editor page (static)
- [x] M4 — STT + mic + TTS ack
- [x] M5 — screenshot capture + planner
- [x] M6 — edit engine trim/cut_range (end-to-end gate PASSED)
- [x] M7–M12 — multi-step loop, transcription, more edits, failure handling, evals, polish

**Gate verified (M6):** spoken → live `html2canvas` screenshot → `gemma4:12b`
planner returns `cut_range` → ffmpeg renders a real frame-accurate cut on disk →
timeline re-renders → fresh screenshot → `gemma4:12b` verifier confirms the change
→ spoken + on-screen ✓ confirmation → `task_complete`. Warm latency ≈ 9 s/plan,
3.7 s/verify on the dev machine (CPU).

**Evaluation:** 15 voice commands tested across cuts, trims, mute ranges,
timeline seeks, crops, and rotations — 100% success rate on CPU. See the Kaggle
writeup for full edge cases and known failure modes.

> Note on screen capture: we use **html2canvas** (paints the DOM directly to a
> canvas) rather than html-to-image, which hangs in some automated Chromium
> builds because it round-trips through an SVG `<img>` that never fires `onload`.

_Fill in at demo time: CPU / GPU / RAM of the host laptop, and observed model
latency._
