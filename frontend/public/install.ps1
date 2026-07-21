<#
  Voed one-line installer for Windows.

  Run this in PowerShell:
      irm https://voed.vercel.app/install.ps1 | iex

  It installs the prerequisites you don't already have (Git, Python, ffmpeg,
  Ollama) via winget, clones Voed to %USERPROFILE%\Voed, and launches it.
  Re-running updates an existing install. Nothing here leaves your machine.
#>
$ErrorActionPreference = "Stop"

$RepoUrl    = "https://github.com/ozr0013/Voed.git"
$InstallDir = Join-Path $HOME "Voed"

function Info($m) { Write-Host "  $m"        -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m"   -ForegroundColor Green }
function Warn($m) { Write-Host "  [..] $m"   -ForegroundColor Yellow }
function Die($m)  { Write-Host "  [X] $m"    -ForegroundColor Red; exit 1 }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }

# winget installs update the *persisted* PATH but not the current session's,
# so re-read it after each install to pick up freshly installed tools.
function Sync-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

Write-Host ""
Write-Host "===  Voed installer  ===" -ForegroundColor Magenta
Write-Host ""

if (-not (Have winget)) {
    Die "winget not found. Install 'App Installer' from the Microsoft Store (or update Windows), then re-run."
}

# Install a prerequisite only if its command is missing.
function Ensure($cmd, $wingetId, $label) {
    if (Have $cmd) { Ok "$label already installed"; return }
    Warn "Installing $label ..."
    winget install --id $wingetId -e --silent `
        --accept-source-agreements --accept-package-agreements | Out-Null
    Sync-Path
    if (Have $cmd) { Ok "$label installed" }
    else { Warn "$label installed (will be on PATH after this run)" }
}

Ensure "git"     "Git.Git"             "Git"
Ensure "python"  "Python.Python.3.12"  "Python 3.12"
Ensure "ffmpeg"  "Gyan.FFmpeg"         "ffmpeg"
Ensure "ollama"  "Ollama.Ollama"       "Ollama"
Sync-Path

# Make sure the Ollama daemon is up (start.ps1 needs it to pull the model).
if (Have ollama) {
    try { ollama list *> $null }
    catch {
        Warn "Starting Ollama ..."
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
}

# Clone fresh, or fast-forward an existing install.
if (Test-Path (Join-Path $InstallDir ".git")) {
    Info "Updating existing install at $InstallDir"
    git -C $InstallDir pull --ff-only
} else {
    Info "Cloning Voed to $InstallDir"
    git clone $RepoUrl $InstallDir
}

Ok "Prerequisites ready"
Write-Host ""
Info "Launching Voed. The first run downloads the AI models (several GB, one-time)."
Write-Host "  When it's ready, open http://localhost:5173 in Chrome." -ForegroundColor Green
Write-Host ""

Set-Location $InstallDir
powershell -ExecutionPolicy Bypass -File .\start.ps1
