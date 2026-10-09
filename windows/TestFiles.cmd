@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd first.
  pause
  exit /b 1
)
echo Automatic disposable file tests. No API key or desktop supervision required.
".venv\Scripts\python.exe" -m app_agent.cli file-smoke
if errorlevel 1 (
  echo File checks failed. Read the saved report path above.
  pause
  exit /b 1
)
echo File checks passed. Report path is shown above.
pause
