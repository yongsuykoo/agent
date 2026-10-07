@echo off
cd /d "%~dp0.."
py -3 -m venv .venv
if errorlevel 1 goto python_fail
.venv\Scripts\python.exe -m pip install -e ".[windows]"
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
goto fail
:tests_fail
echo Setup tests failed. Python and dependencies were installed; read the test errors above.
goto fail
:fail
pause
exit /b 1
