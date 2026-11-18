# Starts the EvalNova Core backend and frontend in separate windows.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -ApiPort 8001
#
# If the API port is already held, this stops rather than starting a second
# server behind the same port. Windows will happily let two processes bind
# 8000, and the symptom is baffling: the interface loads, but half the
# requests are answered by whichever server is older, so new endpoints return
# 405 and edits appear not to save.

param(
    [int]$ApiPort = 8000,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No virtual environment found at .venv" -ForegroundColor Red
    Write-Host "Run:  python -m venv .venv ; .venv\Scripts\activate ; pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Frontend dependencies are missing." -ForegroundColor Red
    Write-Host "Run:  cd frontend ; npm install"
    exit 1
}

# -- is the port already taken? --------------------------------------------

$held = @(Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)

if ($held.Count -gt 0) {
    Write-Host ""
    Write-Host "Port $ApiPort is already in use." -ForegroundColor Yellow

    $ours = @()
    foreach ($connection in $held) {
        $proc = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  PID $($proc.Id)  $($proc.ProcessName)"
            if ($proc.Path -and $proc.Path.StartsWith($root)) { $ours += $proc }
        } else {
            Write-Host "  PID $($connection.OwningProcess)  (not visible to this account)"
        }
    }

    if ($Force -and $ours.Count -gt 0) {
        foreach ($proc in $ours) {
            Write-Host "Stopping $($proc.Id) ..." -ForegroundColor Cyan
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3
    } else {
        Write-Host ""
        Write-Host "A second server behind the same port serves stale code, so this" -ForegroundColor Yellow
        Write-Host "script will not start one. Pick one of:" -ForegroundColor Yellow
        Write-Host "  - close the PowerShell window running the old server"
        Write-Host "  - re-run with -Force to stop servers started from this folder"
        Write-Host "  - use another port:  -ApiPort 8001"
        Write-Host ""
        Write-Host "If the PID above is 'not visible to this account', it belongs to" -ForegroundColor Yellow
        Write-Host "another Windows user session; log that session out, or use -ApiPort." -ForegroundColor Yellow
        exit 1
    }
}

# -- start ------------------------------------------------------------------

Write-Host "Starting the API on http://localhost:$ApiPort ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload --port $ApiPort"
)

Start-Sleep -Seconds 2

Write-Host "Starting the interface ..." -ForegroundColor Cyan
# The dev server proxies /api to the port chosen here, so the browser never
# needs to know it changed.
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\frontend'; `$env:EVALNOVA_API_PORT='$ApiPort'; npm run dev"
)

Write-Host ""
Write-Host "API docs : http://localhost:$ApiPort/docs" -ForegroundColor Green
Write-Host "Interface: the Vite window prints its URL (usually http://localhost:5173)" -ForegroundColor Green
