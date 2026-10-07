$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
& .\.venv\Scripts\app-agent.exe doctor
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
Write-Host 'Calculator test will clear its current calculation and leave it open.'
& .\.venv\Scripts\app-agent.exe windows-smoke
if ($LASTEXITCODE -ne 0) { throw 'Windows Calculator test failed. See output for diagnosis.' }
