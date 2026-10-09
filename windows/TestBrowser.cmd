@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd first.
  pause
  exit /b 1
)
echo Automatic isolated browser checks. Edge or Chrome required. No API key needed.
".venv\Scripts\python.exe" -m app_agent.cli browser-smoke
if errorlevel 1 (
  echo Browser checks failed. Read the report path above.
  pause
  exit /b 1
)
echo Browser checks passed. Report path is shown above.
pause
