"""Fixed read-only Windows metadata probe; never runs a discovered command."""
import json
import subprocess
import sys

# Only selected machine/software facts. No documents, browsing history, command
# lines, account names, product keys, credentials or service executable arguments.
PROBE = r'''
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$warnings = @(); $os = @{}; $paths = @(); $com = @(); $services = @(); $extensions = @(); $surfaces = @()
foreach ($surface in @(@{id='settings';file="$env:windir\ImmersiveControlPanel\SystemSettings.exe"},@{id='file_explorer';file="$env:windir\explorer.exe"},@{id='task_manager';file="$env:windir\System32\taskmgr.exe"},@{id='control_panel';file="$env:windir\System32\control.exe"})) {
  if (Test-Path -LiteralPath $surface.file -PathType Leaf) { $surfaces += @{id=$surface.id; executable=$surface.file} }
}
try {
  $v = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
  $arch = $env:PROCESSOR_ARCHITEW6432; if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
  $os = @{name='Microsoft Windows'; version=$v.DisplayVersion; build="$($v.CurrentBuild).$($v.UBR)"; edition=$v.EditionID; architecture=$arch}
} catch { $warnings += 'Windows build metadata unavailable.' }
foreach ($root in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths')) {
  if (Test-Path $root) {
    try { $paths += @(Get-ChildItem $root -ErrorAction Stop | ForEach-Object { @{name=$_.PSChildName; executable=$_.GetValue('')} }) }
    catch { $warnings += 'An App Paths registration source is inaccessible.' }
  }
}
try {
  $keys = @(Get-ChildItem 'Registry::HKEY_CLASSES_ROOT' -ErrorAction Stop)
  if ($keys.Count -gt 12000) { $warnings += 'Class registration inspection truncated at 12000 entries.' }
  foreach ($k in ($keys | Select-Object -First 12000)) {
    $name = $k.PSChildName
    if ($name.StartsWith('.')) {
      $extensions += @{extension=$name; progid=$k.GetValue('')}; continue
    }
    if ($name -notmatch '^[A-Za-z][A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+$') { continue }
    $cls = $k.OpenSubKey('CLSID')
    if ($null -ne $cls) {
      try {
        $id = $cls.GetValue('')
        if ($id -match '^\{[0-9A-Fa-f-]{36}\}$') {
          $server = Get-Item -LiteralPath "Registry::HKEY_CLASSES_ROOT\CLSID\$id\LocalServer32" -ErrorAction SilentlyContinue
          if ($null -ne $server) { $com += @{progid=$name; clsid=$id; server=$server.GetValue('')}; $server.Close() }
        }
      } finally { $cls.Close() }
    }
  }
} catch { $warnings += 'Some class registrations could not be inspected.' }
try { $services = @(Get-Service -ErrorAction Stop | Select-Object -First 2000 | ForEach-Object { @{name=$_.Name; display_name=$_.DisplayName; status=$_.Status.ToString(); start_type=$_.StartType.ToString()} }) }
catch { $warnings += 'Service state inspection unavailable.' }
@{os=$os; app_paths=$paths; com_servers=$com; file_types=$extensions; services=$services; system_surfaces=$surfaces; warnings=$warnings} | ConvertTo-Json -Depth 6 -Compress
'''


def probe_windows():
    if sys.platform != 'win32':
        raise RuntimeError('Machine onboarding requires Windows.')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', PROBE],
                            capture_output=True, timeout=45, creationflags=0x08000000)
    if result.returncode or len(result.stdout) > 2_000_000:
        raise RuntimeError('Windows metadata probe did not complete within its output allowance.')
    value = json.loads(result.stdout.decode('utf-8-sig'))
    if not isinstance(value, dict) or not isinstance(value.get('os'), dict):
        raise ValueError('Invalid Windows metadata response.')
    for field in ('app_paths', 'com_servers', 'file_types', 'services', 'warnings'):
        if not isinstance(value.get(field), list):
            raise ValueError('Invalid Windows metadata list: ' + field)
    return value
