$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run windows\Setup.cmd first.' }
& .\.venv\Scripts\python.exe -m app_agent.connection_launcher --controller-key (Join-Path $PSScriptRoot 'cloud-controller.json')
if ($LASTEXITCODE -ne 0) { throw 'The Windows connection helper failed.' }
