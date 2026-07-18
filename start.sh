#!/usr/bin/env bash
# VoiceCut launcher (macOS / Linux / Git-Bash / WSL).
# On native Windows PowerShell use start.ps1 instead.
#
#   ./start.sh
#
# Checks local dependencies, installs backend + frontend deps on first run,
# starts the FastAPI backend and the Vite dev server, and prints the LAN URL.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

echo "VoiceCut — local voice-to-action video editor"
echo "Checking local dependencies..."

for bin in ffmpeg ffprobe; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    red "  [X] $bin not found on PATH. Install ffmpeg: https://ffmpeg.org/download.html"
    exit 1
  fi
  green "  [ok] $bin"
done

if ! command -v ollama >/dev/null 2>&1; then
  red "  [X] ollama not found. Install: https://ollama.com"
  exit 1
fi
if ! ollama list >/dev/null 2>&1; then
  red "  [X] ollama daemon not responding. Start Ollama and re-run."
  exit 1
fi
green "  [ok] ollama daemon"

MODEL="${VOICECUT_MODEL:-gemma4:12b}"
if ! ollama list | grep -q "$MODEL"; then
  yellow "  [..] Pulling $MODEL (first run only, several GB)..."
  ollama pull "$MODEL"
fi
green "  [ok] model $MODEL"

# Python venv + backend deps (3.11–3.12; piper-tts wheels are macOS-friendly on 1.3+)
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON=python3.11
else
  PYTHON=python3
fi
if [ -d "$ROOT/.venv" ]; then
  VENV_MINOR="$("$ROOT/.venv/bin/python" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo "")"
  if [ "$VENV_MINOR" = "13" ] || [ "$VENV_MINOR" = "14" ]; then
    yellow "  [..] Recreating venv ($PYTHON preferred; 3.13+ breaks piper on macOS)..."
    rm -rf "$ROOT/.venv"
  fi
fi
if [ ! -d "$ROOT/.venv" ]; then
  echo "Creating Python venv with $PYTHON..."
  "$PYTHON" -m venv "$ROOT/.venv"
fi
PY="$ROOT/.venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r "$ROOT/requirements.txt"
green "  [ok] backend deps"

# Piper voice (first run only)
VOICE="${VOICECUT_PIPER_VOICE:-en_US-lessac-medium}"
if [ ! -f "$ROOT/models/piper/$VOICE.onnx" ]; then
  yellow "  [..] Downloading Piper voice $VOICE..."
  mkdir -p "$ROOT/models/piper"
  # python.org macOS builds often lack system CA certs; certifi is installed via pip deps.
  export SSL_CERT_FILE="$("$PY" -c 'import certifi; print(certifi.where())')"
  "$PY" -m piper.download_voices --download-dir "$ROOT/models/piper" "$VOICE"
fi
green "  [ok] Piper voice $VOICE"
echo "  [i]  faster-whisper 'small' downloads on first transcription (~460 MB, one-time)"

# Frontend deps
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend deps..."
  (cd "$ROOT/frontend" && npm install --silent)
fi
green "  [ok] frontend deps"

# Stable JWT secret across restarts
if [ -z "${VOICECUT_JWT_SECRET:-}" ]; then
  mkdir -p "$ROOT/data"
  SECRET_FILE="$ROOT/data/.jwt_secret"
  [ -f "$SECRET_FILE" ] || (head -c 48 /dev/urandom | base64 | tr -d '\n/+=' > "$SECRET_FILE")
  export VOICECUT_JWT_SECRET="$(cat "$SECRET_FILE")"
fi

# Best-effort LAN IP
IP="$(python3 - <<'PY'
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("10.255.255.255", 1)); print(s.getsockname()[0])
except OSError:
    print("127.0.0.1")
finally:
    s.close()
PY
)"

echo
echo "Starting VoiceCut..."
green "  Backend : http://$IP:8000  (API)"
green "  App     : http://$IP:5173  (open this in Chrome)"
green "  Share the App URL with teammates/judges on the same network."
echo

"$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

# Vite proxies /api to :8000 — wait until Uvicorn is listening so the first page
# load doesn't hit ECONNREFUSED while the backend is still starting.
echo "  Waiting for backend on :8000..."
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8000/api/ping" >/dev/null 2>&1; then
    green "  [ok] backend ready"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    red "  [X] Backend exited during startup"
    exit 1
  fi
  sleep 0.25
done
if ! curl -sf "http://127.0.0.1:8000/api/ping" >/dev/null 2>&1; then
  red "  [X] Backend did not become ready on :8000"
  exit 1
fi

(cd "$ROOT/frontend" && npm run dev -- --host)
