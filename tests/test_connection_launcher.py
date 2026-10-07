import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from app_agent import connection_launcher as launcher
from app_agent.remote_protocol import ControllerKeys


class ConnectionLauncherTests(unittest.TestCase):
    def test_existing_tunnel_skips_installation(self):
        with patch.object(launcher, "find_tunnel_executable", return_value="cloudflared.exe"), patch.object(launcher.subprocess, "run") as install:
            self.assertEqual(launcher.ensure_tunnel_executable(), "cloudflared.exe")
            install.assert_not_called()

    def test_installation_uses_verified_winget_and_finds_new_executable(self):
        with patch.object(launcher, "find_tunnel_executable", side_effect=[None, "new cloudflared.exe"]), \
             patch.object(launcher.shutil, "which", return_value="winget.exe"), \
             patch.object(launcher.subprocess, "run", return_value=Mock(returncode=0)) as install:
            self.assertEqual(launcher.ensure_tunnel_executable(), "new cloudflared.exe")
            arguments = install.call_args.args[0]
            self.assertEqual(arguments[:4], ["winget.exe", "install", "--id", "Cloudflare.cloudflared"])
            self.assertNotIn("--ignore-security-hash", arguments)
            self.assertFalse(install.call_args.kwargs.get("shell", False))

    def test_installation_failure_does_not_claim_connection_readiness(self):
        with patch.object(launcher, "find_tunnel_executable", return_value=None), \
             patch.object(launcher.shutil, "which", return_value="winget.exe"), \
             patch.object(launcher.subprocess, "run", return_value=Mock(returncode=5)):
            with self.assertRaisesRegex(RuntimeError, "WinGet exit 5"):
                launcher.ensure_tunnel_executable()

    def test_no_winget_produces_actionable_error_without_attempting_an_install(self):
        with patch.object(launcher, "find_tunnel_executable", return_value=None), \
             patch.object(launcher.shutil, "which", return_value=None), patch.object(launcher.subprocess, "run") as install:
            with self.assertRaisesRegex(RuntimeError, "WinGet is unavailable"):
                launcher.ensure_tunnel_executable()
            install.assert_not_called()

    def test_portable_winget_link_is_found_when_current_path_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "Microsoft/WinGet/Links/cloudflared.exe"
            link.parent.mkdir(parents=True)
            link.write_bytes(b"test fixture")
            with patch.dict("os.environ", {"LOCALAPPDATA": directory}), patch.object(launcher.shutil, "which", return_value=None):
                self.assertEqual(launcher.find_tunnel_executable(), str(link))

    def test_refreshed_registry_path_is_read_without_running_powershell(self):
        registry = types.ModuleType("winreg")
        registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER = 1, 2
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=None)
        registry.OpenKey = Mock(return_value=key)
        registry.QueryValueEx = Mock(side_effect=[("C:\\New Tunnel", 1), ("C:\\User Tunnel", 1)])
        with patch.object(launcher, "sys", Mock(platform="win32")), patch.dict("sys.modules", {"winreg": registry}), \
             patch.dict("os.environ", {"LOCALAPPDATA": "", "PATH": "C:\\Old"}), \
             patch.object(launcher.shutil, "which", side_effect=[None, "C:\\New Tunnel\\cloudflared.exe"]) as which:
            self.assertEqual(launcher.find_tunnel_executable(), "C:\\New Tunnel\\cloudflared.exe")
            self.assertEqual(which.call_args.kwargs["path"], "C:\\Old;C:\\New Tunnel;C:\\User Tunnel")

    def test_python_entrypoint_starts_gui_with_a_path_containing_spaces(self):
        with tempfile.TemporaryDirectory(prefix="agent with spaces ") as directory:
            public = Path(directory) / "controller public.json"
            public.write_text(json.dumps(ControllerKeys().public()), encoding="utf-8")
            with patch.object(launcher, "sys", Mock(platform="win32")), \
                 patch.object(launcher, "ensure_tunnel_executable", return_value="cloudflared.exe"), \
                 patch("app_agent.remote_ui.launch_connection") as launch:
                self.assertEqual(launcher.main(["--controller-key", str(public), "--data-dir", directory]), 0)
                launch.assert_called_once_with(Path(directory), public)
