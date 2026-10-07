"""Launch the Windows companion without requiring PowerShell script execution."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def find_tunnel_executable():
    found = shutil.which("cloudflared")
    if found:
        return found
    local = os.getenv("LOCALAPPDATA")
    if local:
        link = Path(local) / "Microsoft/WinGet/Links/cloudflared.exe"
        if link.is_file():
            return str(link)
    # Read refreshed PATH values after installation. Do not alter system policy
    # or environment settings, and do not require reopening the command window.
    if sys.platform == "win32":
        import winreg
        paths = [os.environ.get("PATH", "")]
        for hive, location in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                               (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(hive, location) as key:
                    value = winreg.QueryValueEx(key, "Path")[0]
                    if isinstance(value, str):
                        paths.append(os.path.expandvars(value))
            except OSError:
                continue
        return shutil.which("cloudflared", path=";".join(paths))
    return None


def ensure_tunnel_executable():
    found = find_tunnel_executable()
    if found:
        return found
    winget = shutil.which("winget")
    if not winget:
        raise RuntimeError("WinGet is unavailable. Install Cloudflare cloudflared using its official Windows instructions, then retry windows\\Connect.cmd.")
    print("Installing Cloudflare cloudflared through WinGet. Package integrity verification remains enabled.", flush=True)
    installed = subprocess.run([winget, "install", "--id", "Cloudflare.cloudflared", "--exact", "--source", "winget",
                                "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"])
    if installed.returncode:
        raise RuntimeError(f"Cloudflared installation failed (WinGet exit {installed.returncode}). Resolve the installation error before retrying.")
    found = find_tunnel_executable()
    if not found:
        raise RuntimeError("WinGet finished but cloudflared was not found. Reopen this folder and retry Connect.cmd; do not change PowerShell execution policy.")
    return found


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Start the Windows companion through Python")
    parser.add_argument("--controller-key", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "AppAgent")
    args = parser.parse_args(arguments)
    try:
        if sys.platform != "win32":
            raise RuntimeError("Start windows\\Connect.cmd on the Windows desktop.")
        # Validate the public pairing identity before installing anything.
        import json
        from .remote_protocol import fingerprint
        fingerprint(json.loads(args.controller_key.read_text(encoding="utf-8")))
        ensure_tunnel_executable()
        from .remote_ui import launch_connection
        launch_connection(args.data_dir, args.controller_key)
        return 0
    except Exception as error:
        print("Connection setup failed: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
