# ITBIS backend API — start it.
#
#   Right-click -> "Run with PowerShell", or:
#       powershell -ExecutionPolicy Bypass -File "C:\Users\vishw\Desktop\spring\2\project2\start-backend.ps1"
#
# Needs Docker running first (PostgreSQL, MongoDB and Redis):
#       docker compose up -d
#
# Serves http://localhost:8000 (API docs at /docs) and runs the detection
# pipeline every 5 minutes. Leave the window open; Ctrl+C stops it.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$python = Join-Path $backend "venv\Scripts\python.exe"

if (-not (Test-Path $python)) { throw "Backend virtualenv missing: $python" }

Set-Location $backend
Write-Host "Applying database migrations..." -ForegroundColor Cyan
& $python -m alembic upgrade head

Write-Host "Backend starting on http://localhost:8000 — Ctrl+C to stop." -ForegroundColor Cyan
& $python -m uvicorn app.main:app --reload --port 8000
