# ITBIS endpoint agent — start the log listener.
#
#   Right-click this file -> "Run with PowerShell", or from a terminal:
#       powershell -ExecutionPolicy Bypass -File "C:\Users\vishw\Desktop\spring\2\project2\agent\start-agent.ps1"
#
# It relaunches itself as Administrator if needed: reading the Windows
# Security log (logons, privilege changes) requires it.
#
# Leave the window open — the agent runs until you press Ctrl+C or close it.
# Collected events upload to the backend; anything it can't send is queued on
# disk and sent later, so stopping the agent never loses events.

$ErrorActionPreference = "Stop"

# $PSScriptRoot is empty when these lines are pasted into a console rather than
# run as a file, so fall back to this script's own location.
$scriptPath = $PSCommandPath
if (-not $scriptPath) { $scriptPath = "C:\Users\vishw\Desktop\spring\2\project2\agent\start-agent.ps1" }
$agentDir = Split-Path -Parent $scriptPath
$python = Join-Path $agentDir "venv\Scripts\python.exe"
$config = Join-Path $agentDir "config.yaml"

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Restarting as Administrator..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptPath`""
    )
    exit
}

if (-not (Test-Path $python)) { throw "Agent virtualenv missing: $python" }
if (-not (Test-Path $config)) { throw "Agent config missing: $config (copy config.example.yaml and enroll the device)" }

Write-Host "ITBIS agent starting. Press Ctrl+C to stop." -ForegroundColor Cyan
Set-Location $agentDir
& $python -m itbis_agent --config $config
#powershell -ExecutionPolicy Bypass -File "C:\Users\vishw\Desktop\spring\2\project2\agent\start-agent.ps1"
