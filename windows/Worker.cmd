@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd first.
  pause
  exit /b 1
)
echo Starts a bounded unattended session (up to 10 hours) and restarts the worker if it exits.
echo Documentation study can continue while Windows is locked; desktop actions wait for unlock.
".venv\Scripts\python.exe" -m app_agent.cli start-unattended --hours 10
if errorlevel 1 pause
