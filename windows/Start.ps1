$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run windows\Setup.ps1 first.' }
if (-not $env:AGENT_API_KEY -and -not $env:OPENAI_API_KEY) {
    $secret = Read-Host 'OpenAI API key (hidden; kept only in this process)' -AsSecureString
    $env:AGENT_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
}
try { & .\.venv\Scripts\python.exe -m app_agent.cli ui }
finally { Remove-Item Env:AGENT_API_KEY -ErrorAction SilentlyContinue }
