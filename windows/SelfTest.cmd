@echo off
cd /d "%~dp0.."
echo Automatic tests use disposable Notepad data and clear Calculator.
echo Leave the desktop untouched. AI tests use your OpenAI API key and incur provider usage charges.
.venv\Scripts\app-agent.exe self-test --with-cloud
if errorlevel 1 goto fail
echo Tests finished. Read the pass, fail, and skipped counts and report location above.
pause
exit /b 0
:fail
echo Tests did not pass. The saved report identifies the failing checks.
pause
exit /b 1
