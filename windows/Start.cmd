@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\app-agent.exe (
    echo Run windows\Setup.cmd first.
    pause
    exit /b 1
)
.venv\Scripts\app-agent.exe ui
if errorlevel 1 pause
