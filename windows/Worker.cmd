@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd first.
  pause
  exit /b 1
)
echo Runs saved autonomous goals and enabled background study without a session timer.
echo Documentation study can continue while Windows is locked; desktop actions wait for unlock.
".venv\Scripts\python.exe" -m app_agent.cli worker
if errorlevel 1 pause
