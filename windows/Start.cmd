@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    echo Run windows\Setup.cmd first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m app_agent.cli ui
if errorlevel 1 pause
