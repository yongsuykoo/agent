@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run windows\Setup.cmd in this extracted folder first.
  pause
  exit /b 1
)
echo Automatic checks create disposable Notepad, Excel and Word files and clear Calculator.
echo Office checks use installed Microsoft Excel/Word. No API key or cloud charges.
echo Leave the desktop untouched while the tests run. Test documents remain open.
".venv\Scripts\python.exe" -m app_agent.cli self-test --with-office
if errorlevel 1 (
  echo One or more tests failed. Read the saved report path above.
  pause
  exit /b 1
)
pause
