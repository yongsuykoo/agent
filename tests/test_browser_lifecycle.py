"""Browser startup races, bounded ownership checks and Windows Unicode output."""
import io
import unittest
from unittest.mock import Mock,patch
from app_agent.browser import read_endpoint,Browser
from app_agent.cli import prepare_output


class LifecycleTests(unittest.TestCase):
    def test_locked_and_partial_endpoint_are_retried_before_connecting(self):
        path=Mock();process=Mock();process.poll.return_value=None;guard=Mock()
        path.open.side_effect=[PermissionError('Browser still writing'),io.BytesIO(b'9222\n'),io.BytesIO(b'9222\n/devtools/browser/owned-token\n')]
        with patch('app_agent.browser.time.sleep'):
            self.assertEqual(read_endpoint(path,process,guard),(9222,'/devtools/browser/owned-token'))
        self.assertEqual(guard.call_count,3)

    def test_invalid_or_oversized_endpoint_cannot_connect_and_wait_is_bounded(self):
        for data in (b'0\n/devtools/browser/owned',b'65536\n/devtools/browser/owned',b'9222\n/not-owned',b'9222\n/devtools/browser/owned\nextra',b'x'*4097):
            path=Mock();path.open.side_effect=lambda *args:io.BytesIO(data);process=Mock();process.poll.return_value=None
            with self.subTest(data=data[:40]),self.assertRaises(TimeoutError):read_endpoint(path,process,lambda:None,timeout=0)

    def test_exited_browser_or_stop_does_not_wait_for_an_endpoint(self):
        path=Mock();process=Mock();process.poll.return_value=1
        with self.assertRaises(RuntimeError):read_endpoint(path,process,lambda:None)
        path.open.assert_not_called()
        process.poll.return_value=None
        with self.assertRaisesRegex(RuntimeError,'stopped'):read_endpoint(path,process,Mock(side_effect=RuntimeError('stopped')))
        path.open.assert_not_called()

    def test_disposable_cleanup_retries_a_temporary_windows_sharing_violation(self):
        browser=Browser(check_url=lambda url:None);profile=Mock();profile.cleanup.side_effect=[PermissionError('Closing child'),None];browser.profile=profile
        with patch('app_agent.browser.time.sleep') as pause:browser.close()
        self.assertIsNone(browser.profile);self.assertEqual(profile.cleanup.call_count,2);pause.assert_called_once_with(.05)

    def test_unicode_result_printing_survives_legacy_console_encoding(self):
        raw=io.BytesIO();stream=io.TextIOWrapper(raw,encoding='cp1252',newline='\n')
        with patch('app_agent.cli.sys.stdout',stream),patch('app_agent.cli.sys.stderr',io.StringIO()):
            prepare_output();print('Saved: Hello 世界');stream.flush()
        self.assertEqual(raw.getvalue().decode('utf-8'),'Saved: Hello 世界\n')
