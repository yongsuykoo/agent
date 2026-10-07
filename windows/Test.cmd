@echo off
cd /d "%~dp0.."
.venv\Scripts\app-agent.exe doctor
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto fail
.venv\Scripts\app-agent.exe scan
if errorlevel 1 goto fail
echo Automatic checks use disposable Notepad data and clear Calculator. Leave the desktop untouched.
.venv\Scripts\app-agent.exe self-test
if errorlevel 1 goto fail
echo Native Windows checks passed. AI checks require the Self-test button or windows\SelfTest.cmd.
pause
exit /b 0
:fail
echo A check failed. Keep the output for troubleshooting.
pause
exit /b 1
