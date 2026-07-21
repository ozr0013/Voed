#!/usr/bin/env bash
#
# Voed one-line installer for macOS.
#
# Run this in Terminal:
#     curl -fsSL https://voed.vercel.app/install.sh | bash
#
# It installs the prerequisites you don't already have (Homebrew, Git, ffmpeg,
# Ollama, Python) via Homebrew, clones Voed to ~/Voed, and launches it.
# Re-running updates an existing install. Nothing here leaves your machine.
set -euo pipefail

REPO_URL="https://github.com/ozr0013/Voed.git"
INSTALL_DIR="$HOME/Voed"

info() { printf "\033[36m  %s\033[0m\n" "$1"; }
ok()   { printf "\033[32m  [ok] %s\033[0m\n" "$1"; }
warn() { printf "\033[33m  [..] %s\033[0m\n" "$1"; }
die()  { printf "\033[31m  [X] %s\033[0m\n" "$1"; exit 1; }

echo ""
echo "===  Voed installer  ==="
echo ""

# --- Homebrew (the macOS package manager) ---
if ! command -v brew >/dev/null 2>&1; then
  warn "Installing Homebrew (you may be prompted for your password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
# Ensure brew is on PATH for the rest of this script (Apple Silicon vs Intel).
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"
fi
command -v brew >/dev/null 2>&1 || die "Homebrew install failed. See https://brew.sh and re-run."
ok "Homebrew ready"

# --- Prerequisites ---
for pkg in git ffmpeg ollama python@3.12; do
  cmd="$pkg"
  [ "$pkg" = "python@3.12" ] && cmd="python3.12"
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$pkg already installed"
  else
    warn "Installing $pkg ..."
    brew install "$pkg"
  fi
done
ok "Prerequisites installed"

# --- Make sure the Ollama daemon is up (start.sh needs it to pull the model) ---
if ! ollama list >/dev/null 2>&1; then
  warn "Starting Ollama ..."
  ( ollama serve >/dev/null 2>&1 & ) || true
  sleep 3
fi

# --- Clone fresh, or fast-forward an existing install ---
if [ -d "$INSTALL_DIR/.git" ]; then
  info "Updating existing install at $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only || true
else
  info "Cloning Voed to $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

ok "Prerequisites ready"
echo ""
info "Launching Voed. The first run downloads the AI models (several GB, one-time)."
printf "\033[32m  When it's ready, open http://localhost:5173 in Chrome.\033[0m\n"
echo ""

cd "$INSTALL_DIR"
chmod +x ./start.sh
./start.sh
