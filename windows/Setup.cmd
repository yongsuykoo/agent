@echo off
cd /d "%~dp0.."
echo Close App Agent before installing or updating this folder.
if exist .venv\Scripts\python.exe goto install
py -3 -m venv .venv
if errorlevel 1 goto python_fail
:install
.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto python_fail
.venv\Scripts\python.exe -m pip install -e ".[windows,bridge]"
if errorlevel 1 goto dependencies_fail
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto tests_fail
echo Setup complete. Double-click windows\Start.cmd.
pause
exit /b 0
:python_fail
echo Python environment creation failed. Check the Python launcher and Python 3.11 or newer. Read the error above.
goto fail
:dependencies_fail
echo Dependency installation failed. Read the pip error above.
echo If it says Access is denied, close the old agent and use a freshly extracted folder.
goto fail
:tests_fail
echo Setup tests failed. Python and dependencies were installed; read the test errors above.
goto fail
:fail
pause
exit /b 1
