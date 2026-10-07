$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer from python.org, then retry.' }
& .\.venv\Scripts\python.exe -m pip install -e '.[windows]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
Write-Host 'Setup complete. Run windows\Start.ps1 from this project folder.'
