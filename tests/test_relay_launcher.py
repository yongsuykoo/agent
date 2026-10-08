"""Unrelated Cloudflared configuration cannot redirect this helper's origin."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from app_agent.relay_launcher import start_relay, stop_relay


class RelayLauncherTests(unittest.TestCase):
    def test_launch_selects_own_empty_config_and_preserves_proxy_trust(self):
        captured = {}
        process = Mock()
        process.poll.return_value = 0
        def launch(arguments, **options):
            captured['arguments'] = arguments
            captured['options'] = options
            captured['config'] = Path(arguments[arguments.index('--config') + 1])
            self.assertEqual(captured['config'].read_text(), '{}\n')
            return process
        environment = {'TUNNEL_TOKEN': 'unrelated-account', 'TUNNEL_URL': 'http://wrong-origin',
                       'NO_TLS_VERIFY': 'true', 'AGENT_API_KEY': 'fake-provider-key',
                       'HTTPS_PROXY': 'http://proxy:8080', 'SSL_CERT_FILE': '/trusted/ca.pem'}
        with patch.dict(os.environ, environment, clear=True), patch('app_agent.relay_launcher.subprocess.Popen', side_effect=launch):
            tunnel, directory = start_relay('C:/Folder With Spaces/cloudflared.exe', 1234)
            try:
                arguments, options = captured['arguments'], captured['options']
                self.assertEqual(arguments[0], 'C:/Folder With Spaces/cloudflared.exe')
                self.assertEqual(arguments[arguments.index('--url') + 1], 'http://127.0.0.1:1234')
                self.assertEqual(options['env'], {'HTTPS_PROXY': 'http://proxy:8080', 'SSL_CERT_FILE': '/trusted/ca.pem'})
                self.assertEqual(os.environ['TUNNEL_TOKEN'], 'unrelated-account')
                self.assertNotIn('--no-tls-verify', arguments)
            finally:
                stop_relay(tunnel, directory)
        self.assertFalse(captured['config'].exists())

    def test_failed_launch_cleans_only_its_temporary_config(self):
        config = []
        def failed(arguments, **options):
            config.append(Path(arguments[arguments.index('--config') + 1]))
            raise OSError('Launch failed')
        with patch('app_agent.relay_launcher.subprocess.Popen', side_effect=failed):
            with self.assertRaisesRegex(OSError, 'Launch failed'):
                start_relay('cloudflared', 1234)
        self.assertFalse(config[0].exists())

    def test_stop_waits_for_exit_before_removing_config(self):
        process, directory = Mock(), Mock()
        process.poll.side_effect = [None, 0]
        process.wait.side_effect = [subprocess.TimeoutExpired('cloudflared', 5), 0]
        stop_relay(process, directory)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        directory.cleanup.assert_called_once()

    def test_invalid_ports_do_not_launch_a_child(self):
        with patch('app_agent.relay_launcher.subprocess.Popen') as process:
            for port in (False, '1234', 0, 65536):
                with self.assertRaises(ValueError):
                    start_relay('cloudflared', port)
            process.assert_not_called()
