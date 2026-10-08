import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from app_agent.maintenance import Maintenance, idle_seconds


class Session:
    allow_tests = True
    allow_cloud = True
    def __init__(self):
        self.lock = threading.Lock(); self.jobs = {}; self.requests = []; self.stopped = False
    def active(self): return not self.stopped
    def enqueue(self, value):
        identity = str(len(self.requests));self.requests.append(value)
        self.jobs[identity] = {'id': identity, 'status': 'queued'}
        return self.jobs[identity]
    def get(self, identity):return self.jobs[identity]
    def finish(self, counts=None):
        self.jobs[str(len(self.requests)-1)].update(status='completed', result={'counts': counts or {'passed':14,'failed':0,'skipped':0,'cancelled':0}})


class MaintenanceTests(unittest.TestCase):
    def test_native_idle_clock_handles_tick_rollover_and_failed_observation(self):
        user32, kernel32 = Mock(), Mock()
        def last_input(pointer):
            pointer._obj.dwTime = 0xfffffff0
            return 1
        user32.GetLastInputInfo.side_effect = last_input
        kernel32.GetTickCount.return_value = 0x10
        with patch('ctypes.WinDLL', side_effect=[user32, kernel32], create=True):
            self.assertEqual(idle_seconds(), .032)
        user32.GetLastInputInfo.side_effect = None
        user32.GetLastInputInfo.return_value = 0
        with patch('ctypes.WinDLL', side_effect=[user32, kernel32], create=True):
            self.assertEqual(idle_seconds(), 0)

    def test_active_user_is_never_given_an_automatic_desktop_test(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session();m=Maintenance(directory,emit=lambda text:None)
            m.tick(s,'0.7.0',0);s.finish();m.tick(s,'0.7.0',0)
            self.assertEqual([r['operation'] for r in s.requests],['inventory','study'])
            self.assertEqual(s.requests[-1]['parameters']['daily_limit'],5)

    def test_failed_test_is_retained_across_restart_and_new_version_can_retest(self):
        with tempfile.TemporaryDirectory() as directory, patch('app_agent.maintenance.time.monotonic',return_value=100):
            s=Session();m=Maintenance(directory,emit=lambda text:None)
            m.tick(s,'0.7.0',60);s.finish();m.tick(s,'0.7.0',60)
            self.assertEqual(s.requests[-1]['operation'],'self_test')
            s.finish({'passed':12,'failed':2});m.tick(s,'0.7.0',60)
            s.finish();m.tick(s,'0.7.0',60)
            self.assertEqual(sum(r['operation']=='self_test' for r in s.requests),1)
            restarted=Maintenance(directory,emit=lambda text:None);restarted.next_inventory=999;restarted.next_study=999
            restarted.tick(s,'0.7.0',60)
            self.assertEqual(sum(r['operation']=='self_test' for r in s.requests),1)
            restarted.tick(s,'0.7.1',60)
            self.assertEqual(s.requests[-1]['operation'],'self_test')
            self.assertTrue(any(i.get('counts',{}).get('failed')==2 for i in restarted.state['history']))

    def test_busy_or_stopped_session_never_starts_duplicate_work(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session();m=Maintenance(directory,emit=lambda text:None)
            m.tick(s,'0.7.0',90);m.tick(s,'0.7.0',90)
            self.assertEqual(len(s.requests),1)
            s.finish();s.stopped=True;m.tick(s,'0.7.0',90)
            self.assertEqual(len(s.requests),1)

    def test_result_is_attributed_to_the_worker_that_started_it(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Session();m=Maintenance(directory,emit=lambda text:None)
            m.tick(s,'0.7.0',0);s.finish();m.tick(s,'0.7.1',0)
            self.assertEqual(m.state['history'][0]['worker_version'],'0.7.0')
