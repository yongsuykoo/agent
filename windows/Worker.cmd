@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd first.
  pause
  exit /b 1
)
echo Runs saved autonomous goals locally. Ctrl+Alt+F12 pauses the queue.
echo Keep Windows logged in and unlocked. The worker waits while the GUI is open.
".venv\Scripts\python.exe" -m app_agent.cli worker
if errorlevel 1 pause
