# One-command QuietCue hub startup for Windows (PowerShell 5.1 compatible).
#
# Examples:
#   .\scripts\run_demo.ps1                                  # dependency-free demo classifier
#   .\scripts\run_demo.ps1 -Classifier yamnet               # real YAMNet classifier (installs TensorFlow)
#   .\scripts\run_demo.ps1 -SpeechModel tiny.en             # add gated Faster-Whisper speech path
#   .\scripts\run_demo.ps1 -BindHost 0.0.0.0                # accept the Uno Q over the LAN/Tailscale
[CmdletBinding()]
param(
    [ValidateSet("demo", "yamnet")]
    [string]$Classifier = "demo",

    [ValidateSet("home", "work", "driving", "sleep", "emergency")]
    [string]$AlertProfile = "home",

    [string]$SpeechModel = "",

    [string]$BindHost = "127.0.0.1",

    [int]$Port = 8765,

    [int]$StatePort = 8787
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# --- Python virtual environment -------------------------------------------------
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment in .venv ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv (is Python 3.10+ on PATH?)" }
}

# The demo classifier and hub run on the standard library alone. Heavy
# dependencies are installed only when the selected mode needs them.
if ($Classifier -eq "yamnet") {
    Write-Host "Installing YAMNet dependencies (backend\requirements.txt) ..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r backend\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
}
if ($SpeechModel -ne "") {
    Write-Host "Installing speech dependencies (backend\requirements-speech.txt) ..."
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r backend\requirements-speech.txt
    if ($LASTEXITCODE -ne 0) { throw "Speech dependency installation failed" }
}

# --- Pairing token warning ------------------------------------------------------
if (-not $env:QUIETCUE_PAIRING_TOKEN) {
    Write-Warning "QUIETCUE_PAIRING_TOKEN is not set. The hub will accept any Uno Q client."
    Write-Warning "Use this only on a trusted development network. To set one:"
    Write-Warning '  $env:QUIETCUE_PAIRING_TOKEN = "<shared-development-token>"'
}

if ($BindHost -eq "0.0.0.0") {
    Write-Host "Binding to 0.0.0.0: only do this on a trusted LAN or Tailscale network." -ForegroundColor Yellow
}

# --- Launch the hub -------------------------------------------------------------
$hubArgs = @(
    "-m", "backend.app.hub_server",
    "--host", $BindHost,
    "--port", "$Port",
    "--state-host", $BindHost,
    "--state-port", "$StatePort",
    "--classifier", $Classifier,
    "--profile", $AlertProfile
)
if ($SpeechModel -ne "") {
    $hubArgs += @("--speech-model", $SpeechModel, "--speech-device", "cpu", "--speech-compute-type", "int8")
}

Write-Host ""
Write-Host "Starting QuietCue hub: classifier=$Classifier profile=$AlertProfile audio=${BindHost}:$Port state=${BindHost}:$StatePort"
Write-Host "Stop with Ctrl+C."
Write-Host ""
& $venvPython @hubArgs
