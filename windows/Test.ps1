$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
& .\.venv\Scripts\app-agent.exe doctor
if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
& .\.venv\Scripts\app-agent.exe scan
if ($LASTEXITCODE -ne 0) { throw 'App inventory scan failed.' }
Write-Host 'Automatic checks use disposable Notepad data and clear Calculator. Leave the desktop untouched.'
& .\.venv\Scripts\app-agent.exe self-test
if ($LASTEXITCODE -ne 0) { throw 'Windows self-test failed. See the saved report for diagnosis.' }
Write-Host 'Native checks passed. AI checks require the Self-test button or windows\SelfTest.cmd.'
