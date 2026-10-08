"""Transport logs cannot establish an authenticated Windows connection."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from app_agent.relay_diagnostics import RelayDiagnostics, check_local_helper


class RelayReadinessTests(unittest.TestCase):
    def test_advertised_url_alone_is_not_ready(self):
        relay = RelayDiagnostics()
        relay.observe('| https://example.trycloudflare.com |')
        self.assertEqual(relay.url, 'https://example.trycloudflare.com')
        self.assertFalse(relay.ready)
        relay.observe('ERR failed to dial edge connIndex=0')
        self.assertFalse(relay.ready)

    def test_registration_and_url_are_both_required_in_either_order(self):
        for reversed_order in (False, True):
            relay = RelayDiagnostics()
            lines = ['https://example.trycloudflare.com', 'INF Registered tunnel connection connIndex=0']
            if reversed_order:
                lines.reverse()
            relay.observe(lines[0])
            self.assertFalse(relay.ready)
            relay.observe(lines[1])
            self.assertTrue(relay.ready)

    def test_disconnect_only_removes_the_affected_connection(self):
        relay = RelayDiagnostics()
        relay.observe('https://example.trycloudflare.com')
        for index in (0, 1):
            relay.observe(f'INF Registered tunnel connection connIndex={index}')
        relay.observe('INF Unregistered tunnel connection connIndex=0')
        self.assertTrue(relay.ready)
        relay.observe('ERR failed to serve tunnel connection connIndex=1')
        self.assertFalse(relay.ready)
        relay.observe('INF Registered tunnel connection connIndex=1')
        self.assertTrue(relay.ready)

    def test_diagnostics_are_bounded_redacted_and_do_not_claim_controller_verification(self):
        relay = RelayDiagnostics()
        for index in range(20):
            relay.observe(f'line {index}')
        relay.observe('ERR token=private-value password="private words" Bearer private-bearer sk-private-provider')
        report = relay.report('test', 'public-fingerprint', 1234, True, True)
        self.assertEqual(len(relay.lines), 12)
        for secret in ('private-value', 'private words', 'private-bearer', 'sk-private-provider'):
            self.assertNotIn(secret, report)
        self.assertIn('[redacted]', report)
        self.assertIn('not established', report)
        self.assertIn('http://127.0.0.1:1234/info', report)

    def test_local_check_requires_a_valid_integer_port(self):
        for port in (True, '1234', 0, -1, 65536):
            with self.assertRaises(ValueError):
                check_local_helper(port)

    def test_other_local_web_server_is_not_reported_as_the_bridge(self):
        class WrongServer(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Not found')
        server = ThreadingHTTPServer(('127.0.0.1', 0), WrongServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertFalse(check_local_helper(server.server_port))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
