import threading
import unittest
from app_agent.automation_worker import AutomationWorker


class WorkerTests(unittest.TestCase):
    def test_initialize_tasks_and_cleanup_share_one_thread(self):
        records = []
        errors = []
        def initialize():
            records.append(("init", threading.get_ident()))
            return lambda: records.append(("cleanup", threading.get_ident()))
        worker = AutomationWorker(lambda fn: fn(), errors.append, initialize)
        worker.submit(lambda: records.append(("refresh", threading.get_ident())))
        worker.submit(lambda: records.append(("observe", threading.get_ident())))
        worker.close()
        worker.thread.join(timeout=2)
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual([name for name, ident in records], ["init", "refresh", "observe", "cleanup"])
        self.assertEqual(len({ident for name, ident in records}), 1)
        self.assertNotEqual(records[0][1], threading.get_ident())
        self.assertEqual(errors, [])

    def test_failed_task_does_not_destroy_com_owner(self):
        errors, completed = [], []
        worker = AutomationWorker(lambda fn: fn(), errors.append, lambda: lambda: None)
        def fail():
            raise RuntimeError("temporary UI failure")
        worker.submit(fail)
        worker.submit(lambda: completed.append(True))
        worker.close()
        worker.thread.join(timeout=2)
        self.assertEqual(len(errors), 1)
        self.assertEqual(completed, [True])
