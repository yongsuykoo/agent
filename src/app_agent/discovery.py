"""Discover desktop registrations, Start menu apps, and Store packages."""
import hashlib
import json
import re
import subprocess
import sys
from .local_inspection import executable_path


def normalized_name(name):
    return " ".join(re.findall(r"[\w]+", name.casefold()))


def merge_inventory(registry, starts, packages):
    apps = {}
    names = {normalized_name(app["name"]): app for app in registry}
    families = {app["family"].casefold(): app for app in packages}
    used_names, used_families = set(), set()
    for item in starts:
        name, app_id = item.get("Name", ""), item.get("AppID", "")
        if not isinstance(name, str) or not isinstance(app_id, str) or not name.strip() or not app_id:
            continue
        family = app_id.split("!", 1)[0].casefold()
        package = families.get(family, {})
        registered = names.get(normalized_name(name), {})
        identity = "start:" + app_id.casefold()
        apps[identity] = {"id": identity, "name": name, "app_id": app_id,
            "version": package.get("version") or registered.get("version", ""),
            "publisher": package.get("publisher") or registered.get("publisher", ""),
            "location": package.get("location") or registered.get("location", ""),
            "help_url": registered.get("help_url", ""), "source": "start_menu",
            "executables": list(dict.fromkeys([*registered.get("executables", []), *item.get("executables", [])])),
            "aliases": sorted({name, registered.get("name", name), package.get("name", name)})}
        used_names.add(normalized_name(name))
        used_families.add(family)
    for item in registry:
        if normalized_name(item["name"]) not in used_names:
            identity = "registry:" + hashlib.sha256(normalized_name(item["name"]).encode()).hexdigest()[:24]
            apps.setdefault(identity, {**item, "id": identity, "app_id": "", "source": "registry", "aliases": [item["name"]]})
    for item in packages:
        if item["family"].casefold() not in used_families:
            identity = "package:" + item["family"].casefold()
            apps[identity] = {**item, "id": identity, "app_id": "", "help_url": "", "source": "store", "aliases": [item["name"]]}
    return sorted(apps.values(), key=lambda app: app["name"].casefold())


def scan_apps():
    if sys.platform != "win32":
        raise RuntimeError("Installed app discovery requires Windows.")
    import winreg
    registry, warnings = [], []
    complete = {"registry", "start_menu", "store"}
    path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            except OSError:
                complete.discard("registry")
                warnings.append("A desktop app registry location is inaccessible.")
                continue
            with root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, index)) as key:
                            def value(name):
                                try:
                                    return str(winreg.QueryValueEx(key, name)[0])
                                except FileNotFoundError:
                                    return ""
                            name = value("DisplayName")
                            if name and value("SystemComponent") != "1":
                                registry.append({"name": name, "version": value("DisplayVersion"),
                                    "publisher": value("Publisher"), "location": value("InstallLocation"), "help_url": value("HelpLink"),
                                    "executables": [exe] if (exe := executable_path(re.sub(r",\s*-?\d+$", "", value("DisplayIcon")))) else []})
                    except OSError:
                        complete.discard("registry")
                        warnings.append("An app registry entry changed or was inaccessible.")
    # Fixed read-only script. No user/model text is interpolated.
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$warnings = @(); $complete = @(); $starts = @(); $packages = @()
try {
  $starts = @(Get-StartApps -ErrorAction Stop | Select-Object Name,AppID)
  $links = @{}; $shell = New-Object -ComObject WScript.Shell
  foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('CommonPrograms'))) {
    if (-not $folder -or -not (Test-Path $folder)) { continue }
    foreach ($file in (Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1024)) {
      $target = $shell.CreateShortcut($file.FullName).TargetPath
      if ($target -and $target.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
        if (-not $links.ContainsKey($file.BaseName)) { $links[$file.BaseName] = @() }
        $links[$file.BaseName] += $target
      }
    }
  }
  $starts = @($starts | ForEach-Object { @{Name=$_.Name; AppID=$_.AppID; executables=@($links[$_.Name] | Select-Object -Unique)} })
  $complete += 'start_menu'
}
catch { $warnings += 'Start shortcut inspection incomplete.'; if ($starts.Count -gt 0) { $complete += 'start_menu' } }
try { $packages = @(Get-AppxPackage -ErrorAction Stop | Where-Object { -not $_.IsFramework -and -not $_.IsResourcePackage } | ForEach-Object { @{ name=$_.Name; family=$_.PackageFamilyName; version=$_.Version.ToString(); publisher=$_.Publisher; location=$_.InstallLocation } }); $complete += 'store' }
catch { $warnings += 'Store discovery unavailable.' }
@{ starts=$starts; packages=$packages; warnings=$warnings; complete=$complete } | ConvertTo-Json -Depth 5 -Compress
"""
    starts, packages = [], []
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, timeout=45, creationflags=0x08000000)
        if result.returncode:
            raise RuntimeError("PowerShell discovery failed.")
        payload = json.loads(result.stdout.decode("utf-8-sig"))
        starts, packages = payload.get("starts", []), payload.get("packages", [])
        warnings.extend(payload.get("warnings", []))
        for source in ("start_menu", "store"):
            if source not in payload.get("complete", []):
                complete.discard(source)
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError):
        complete -= {"start_menu", "store"}
        warnings.append("Start menu and Store scanning failed; registry results retained.")
    return {"apps": merge_inventory(registry, starts, packages), "warnings": sorted(set(warnings)), "complete_sources": sorted(complete)}


def installed_apps():
    return scan_apps()["apps"]
