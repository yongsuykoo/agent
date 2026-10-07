@echo off
cd /d "%~dp0.."
.venv\Scripts\app-agent.exe doctor
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto fail
echo Calculator smoke test clears its current calculation and leaves it open.
.venv\Scripts\app-agent.exe windows-smoke
if errorlevel 1 goto fail
echo Windows checks passed.
pause
exit /b 0
:fail
echo A check failed. Keep the output for troubleshooting.
pause
exit /b 1
