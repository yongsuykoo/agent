$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
Write-Host 'Close App Agent before installing or updating this folder.'
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer from python.org, then retry.' }
}
& .\.venv\Scripts\python.exe -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The existing Python environment cannot run Python 3.11 or newer. Close the agent and use a freshly extracted folder.' }
& .\.venv\Scripts\python.exe -m pip install -e '.[windows]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. If Access is denied, close the old agent and use a freshly extracted folder.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
Write-Host 'Setup complete. Run windows\Start.ps1 from this project folder.'
