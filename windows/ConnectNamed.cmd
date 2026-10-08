@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe goto setup_required
.venv\Scripts\python.exe -m app_agent.connection_launcher --controller-key "%~dp0cloud-controller.json" --hostname "agent.papaprint.store"
if errorlevel 1 goto fail
exit /b 0
:setup_required
echo Run windows\Setup.cmd in this extracted folder first.
goto fail
:fail
echo Named connection setup failed. Read the error above.
pause
exit /b 1
