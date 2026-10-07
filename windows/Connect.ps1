$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run windows\Setup.cmd in this freshly extracted folder first.' }
if (-not (Test-Path 'windows\cloud-controller.json')) { throw 'The pinned controller public key is missing. Download the current repository ZIP.' }
$tunnelPath = Get-Command cloudflared -ErrorAction SilentlyContinue
$portableLink = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\cloudflared.exe'
if (-not $tunnelPath -and -not (Test-Path $portableLink)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'WinGet is unavailable. Install Cloudflare cloudflared from the official Cloudflare Windows instructions, then retry Connect.cmd.'
    }
    Write-Host 'Installing Cloudflare cloudflared through WinGet. Package integrity verification remains enabled.'
    & winget install --id Cloudflare.cloudflared --exact --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Cloudflared installation failed. Resolve the WinGet error before retrying.' }
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
& .\.venv\Scripts\python.exe -m app_agent.cli connect --controller-key windows\cloud-controller.json
if ($LASTEXITCODE -ne 0) { throw 'The Windows connection helper failed.' }
