# Starts the EvalNova Core backend and frontend in separate windows.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#
# The backend loads the handwriting model in the background at startup, so give
# it a minute before the first upload; the header badge says when it is ready.

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

Write-Host "Starting the API on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload --port 8000"
)

Start-Sleep -Seconds 2

Write-Host "Starting the interface ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)

Write-Host ""
Write-Host "API docs : http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Interface: the Vite window prints its URL (usually http://localhost:5173)" -ForegroundColor Green
