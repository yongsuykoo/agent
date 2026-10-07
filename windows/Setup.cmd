@echo off
cd /d "%~dp0.."
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -e ".[windows]"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto fail
echo Setup complete. Double-click windows\Start.cmd.
pause
exit /b 0
:fail
echo Setup failed. Install Python 3.11 or newer with the Python launcher, then retry. Read the error above.
pause
exit /b 1
