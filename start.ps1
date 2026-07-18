# VoiceCut launcher (Windows / PowerShell) - primary entry point on Windows.
#
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# Checks local dependencies, installs backend + frontend deps on first run,
# starts the FastAPI backend and the Vite dev server, and prints the LAN URL.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host "VoiceCut - local voice-to-action video editor" -ForegroundColor Cyan
Write-Host "Checking local dependencies..." -ForegroundColor Cyan

# --- ffmpeg / ffprobe ---
foreach ($bin in @("ffmpeg", "ffprobe")) {
  if (-not (Have $bin)) {
    Write-Host "  [X] $bin not found on PATH. Install ffmpeg: https://ffmpeg.org/download.html" -ForegroundColor Red
    exit 1
  }
  Write-Host "  [ok] $bin" -ForegroundColor Green
}

# --- ollama daemon ---
if (-not (Have "ollama")) {
  Write-Host "  [X] ollama not found. Install: https://ollama.com" -ForegroundColor Red
  exit 1
}
try { ollama list *> $null } catch {
  Write-Host "  [X] ollama daemon not responding. Start Ollama and re-run." -ForegroundColor Red
  exit 1
}
Write-Host "  [ok] ollama daemon" -ForegroundColor Green

# --- model ---
$model = if ($env:VOICECUT_MODEL) { $env:VOICECUT_MODEL } else { "gemma4:12b" }
$tags = (ollama list) -join "`n"
if ($tags -notmatch [regex]::Escape($model)) {
  Write-Host "  [..] Pulling $model (first run only, several GB)..." -ForegroundColor Yellow
  ollama pull $model
}
Write-Host "  [ok] model $model" -ForegroundColor Green

# --- Python venv + backend deps ---
if (-not (Test-Path "$root\.venv")) {
  Write-Host "Creating Python venv..." -ForegroundColor Cyan
  python -m venv "$root\.venv"
}
$py = "$root\.venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r "$root\requirements.txt"
Write-Host "  [ok] backend deps" -ForegroundColor Green

# --- Piper voice (first run only) ---
$voice = if ($env:VOICECUT_PIPER_VOICE) { $env:VOICECUT_PIPER_VOICE } else { "en_US-lessac-medium" }
if (-not (Test-Path "$root\models\piper\$voice.onnx")) {
  Write-Host "  [..] Downloading Piper voice $voice..." -ForegroundColor Yellow
  New-Item -ItemType Directory -Force -Path "$root\models\piper" | Out-Null
  & $py -m piper.download_voices --download-dir "$root\models\piper" $voice
}
Write-Host "  [ok] Piper voice $voice" -ForegroundColor Green
Write-Host "  [i]  faster-whisper 'small' downloads on first transcription (~460 MB, one-time)" -ForegroundColor DarkGray

# --- Frontend deps ---
if (-not (Test-Path "$root\frontend\node_modules")) {
  Write-Host "Installing frontend deps..." -ForegroundColor Cyan
  Push-Location "$root\frontend"; npm install --silent; Pop-Location
}
Write-Host "  [ok] frontend deps" -ForegroundColor Green

# --- Stable JWT secret across restarts (per-machine) ---
if (-not $env:VOICECUT_JWT_SECRET) {
  $secretFile = "$root\data\.jwt_secret"
  if (-not (Test-Path $secretFile)) {
    New-Item -ItemType Directory -Force -Path "$root\data" | Out-Null
    [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N") |
      Out-File -Encoding ascii $secretFile
  }
  $env:VOICECUT_JWT_SECRET = (Get-Content $secretFile -Raw).Trim()
}

# --- Launch ---
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.PrefixOrigin -in @("Dhcp", "Manual") -and $_.IPAddress -ne "127.0.0.1" } |
  Select-Object -First 1 -ExpandProperty IPAddress)
if (-not $ip) { $ip = "127.0.0.1" }

Write-Host ""
Write-Host "Starting VoiceCut..." -ForegroundColor Cyan
Write-Host "  Backend : http://${ip}:8000  (API)" -ForegroundColor Green
Write-Host "  App     : http://${ip}:5173  (open this in Chrome)" -ForegroundColor Green
Write-Host "  Share the App URL with teammates/judges on the same network." -ForegroundColor Green
Write-Host ""

$backend = Start-Process -PassThru -NoNewWindow $py -ArgumentList `
  "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"
try {
  Push-Location "$root\frontend"
  npm run dev -- --host
} finally {
  Pop-Location
  if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
