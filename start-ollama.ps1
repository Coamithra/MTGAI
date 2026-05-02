# MTGAI Ollama "boost" launcher
#
# Restarts the local Ollama service with OLLAMA_KV_CACHE_TYPE=q4_0 in process
# scope, overriding the User-scope default of q8_0. q4_0 saves ~30-50 s per
# 58K-token theme extraction on vlad-gemma4-26b-dynamic at 128K context vs
# q8_0 (and ~107 s vs f16). It's safe for MTGAI because we standardize on
# Gemma 4 (sliding-window attention is empirically robust to q4_0 KV cache
# per TC-1f). Don't use this if you'll switch the system to a non-Gemma-4
# model afterwards without restarting Ollama again.
#
# Asks for confirmation before killing existing Ollama processes — if Ollama
# is currently servicing a request, this will interrupt it.

$ErrorActionPreference = 'Continue'

Write-Host '=== MTGAI Ollama boost launcher ==='
Write-Host ''
Write-Host 'About to:'
Write-Host '  1. Stop all running Ollama processes (tray app, serve, runner)'
Write-Host '  2. Start a fresh "ollama serve" with OLLAMA_KV_CACHE_TYPE=q4_0'
Write-Host ''
Write-Host 'Currently running Ollama processes:'
$existing = Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue
if ($existing) {
    $existing | ForEach-Object { Write-Host "  PID $($_.Id) ($($_.Name))" }
    Write-Host ''
    Write-Host 'If Ollama is currently processing a request (e.g. a long-context'
    Write-Host 'extraction), killing it will lose that work.'
} else {
    Write-Host '  (none)'
}
Write-Host ''
$confirm = Read-Host 'Proceed? [y/N]'
if ($confirm -ne 'y' -and $confirm -ne 'Y') {
    Write-Host 'Aborted.'
    exit 0
}

Write-Host ''
Write-Host '==> Stopping existing Ollama processes'
Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "    stopping PID $($_.Id) ($($_.Name))"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

Write-Host ''
Write-Host '==> Starting ollama serve with OLLAMA_KV_CACHE_TYPE=q4_0'
$env:OLLAMA_KV_CACHE_TYPE = 'q4_0'

# Redirect stderr/stdout to disk so failures during a boost-mode session
# (connection drops, crashes, repetition loops) are forensically recoverable.
# The tray-managed C:\Users\coami\AppData\Local\Ollama\server.log goes silent
# the moment we kill its serve process, so without this the entire boost
# session is logging into the void.
# Overwrites on each launch — copy the file aside if you want to keep it.
$logDir = Join-Path $PSScriptRoot 'output'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logStderr = Join-Path $logDir 'ollama-boost.log'
$logStdout = Join-Path $logDir 'ollama-boost.stdout.log'

$proc = Start-Process -FilePath 'ollama' -ArgumentList 'serve' `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardError $logStderr `
    -RedirectStandardOutput $logStdout
Write-Host "    ollama serve started, PID = $($proc.Id)"
Write-Host "    log: $logStderr"

Start-Sleep -Seconds 3
try {
    $health = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 5
    Write-Host "    health check: $($health.StatusCode) OK"
} catch {
    Write-Host "    health check failed: $($_.Exception.Message)"
}
