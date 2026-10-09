import tempfile
import threading
import unittest
from unittest.mock import Mock
from app_agent.unattended import Sessions,SessionCancellation,start_session,watch_session


class UnattendedSessionTests(unittest.TestCase):
    def test_ten_hour_bound_and_restart_resume(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[100.0]
            store=Sessions(root,clock=lambda:clock[0])
            session=store.start(10)
            self.assertEqual(session['deadline'],36100.0)
            self.assertEqual(store.start(1)['id'],session['id'])
            store.close()
            resumed=Sessions(root,clock=lambda:clock[0]).current()
            self.assertEqual(resumed['state'],'active');self.assertEqual(resumed['remaining_seconds'],36000.0)

    def test_expiry_fences_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[100.0];store=Sessions(root,clock=lambda:clock[0]);session=store.start(1/3600);store.close()
            clock[0]=104.0
            token=SessionCancellation(root,session,wall=lambda:clock[0],monotonic=lambda:clock[0])
            self.assertTrue(token.is_set())
            self.assertEqual(Sessions(root,clock=lambda:clock[0]).current()['state'],'elapsed')

    def test_external_stop_cancels_without_replaying_actions(self):
        with tempfile.TemporaryDirectory() as root:
            store=Sessions(root);session=store.start(.01);store.close()
            stop=threading.Event();token=SessionCancellation(root,session,event=stop)
            stop.set();self.assertTrue(token.is_set())

    def test_watchdog_restarts_dead_child_and_stops_at_deadline(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[100.0];store=Sessions(root,clock=lambda:clock[0]);session=store.start(.01);store.close()
            class Child:
                def __init__(self):self.dead=False
                def poll(self):return 1 if self.dead else None
                def terminate(self):self.dead=True
                def wait(self,timeout=None):return 0
            children=[]
            def spawn():
                child=Child();children.append(child);return child
            stop=threading.Event()
            # The watchdog's normal two-second wait is replaced with a clock advance.
            def monotonic():
                clock[0]+=2;return clock[0]
            watch_session(root,session['id'],spawn=spawn,cancel=stop,wall=lambda:clock[0],monotonic=monotonic)
            self.assertGreaterEqual(len(children),1)
            self.assertEqual(Sessions(root,clock=lambda:clock[0]).current()['state'],'elapsed')

    def test_start_session_refuses_paused_queue(self):
        with tempfile.TemporaryDirectory() as root:
            from app_agent.jobs import Jobs
            jobs=Jobs(root);jobs.pause();jobs.close()
            with self.assertRaisesRegex(RuntimeError,'queue is paused'):start_session(root,launch=False)


if __name__=='__main__':unittest.main()
