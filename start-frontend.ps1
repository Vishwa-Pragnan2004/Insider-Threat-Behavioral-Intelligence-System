# ITBIS web app — start it.
#
#   Right-click -> "Run with PowerShell", or:
#       powershell -ExecutionPolicy Bypass -File "C:\Users\vishw\Desktop\spring\2\project2\start-frontend.ps1"
#
# Serves http://localhost:5173 and talks to the backend on port 8000, so start
# the backend first. Leave the window open; Ctrl+C stops it.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "frontend")

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies (first run only)..." -ForegroundColor Yellow
    npm install
}

Write-Host "Web app starting on http://localhost:5173 — Ctrl+C to stop." -ForegroundColor Cyan
npm run dev
