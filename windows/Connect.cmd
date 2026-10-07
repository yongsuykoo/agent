@echo off
cd /d "%~dp0.."
powershell.exe -NoProfile -File "%~dp0Connect.ps1"
if errorlevel 1 goto fail
exit /b 0
:fail
echo Connection setup failed. Read the error above.
pause
exit /b 1
