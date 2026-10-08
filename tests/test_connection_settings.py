import unittest
from app_agent.connection_settings import public_hostname, tunnel_token


class NamedConnectionSettingsTests(unittest.TestCase):
    def test_public_hostname_normalizes_without_accepting_urls_or_wildcards(self):
        self.assertEqual(public_hostname(' Agent.PapaPrint.Store '), 'agent.papaprint.store')
        for host in ('https://agent.papaprint.store', '*.papaprint.store', 'agent.papaprint.store/path',
                     '127.0.0.1', 'localhost', 'foo.local', 'user@papaprint.store', 'agent.papaprint.store:443',
                     'bad_label.papaprint.store', '-invalid.papaprint.store', 'a' * 64 + '.store', None):
            with self.subTest(host=host), self.assertRaises(ValueError):
                public_hostname(host)

    def test_dashboard_commands_are_parsed_as_text_without_executing_them(self):
        token = 'A' * 60 + '=_-'
        for value in (token, 'cloudflared.exe service install ' + token,
                      'sudo cloudflared service install ' + token,
                      'cloudflared service install "' + token + '"'):
            self.assertEqual(tunnel_token(value), token)

    def test_token_errors_never_echo_credentials_or_accept_commands_to_execute(self):
        token = 'A' * 60
        for value in ('', 'tiny', 'cloudflared.exe service install tiny', token[:30] + '\n' + token[30:],
                      'cloudflared.exe service install ' + token + ' && evil-command', 'wrong-program service install ' + token):
            with self.subTest(value=value), self.assertRaises(ValueError) as error:
                tunnel_token(value)
            self.assertNotIn(token, str(error.exception))
