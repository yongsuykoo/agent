import io
import json
from email.parser import Parser
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, Mock
import zipfile

from app_agent.remote_protocol import ControllerKeys, canonical, encode
from app_agent.worker_update import WorkerUpdates, verify_manifest, verify_wheel, MANIFEST_URL, WHEEL_URL
from app_agent.worker_process import run_worker


def wheel(version='0.7.1', dependency=''):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('app_agent/__init__.py', '')
        z.writestr('app_agent/worker_process.py', Path('src/app_agent/worker_process.py').read_text())
        z.writestr('app_agent/automation_worker.py', Path('src/app_agent/automation_worker.py').read_text())
        z.writestr('app_agent/self_test.py', '')
        z.writestr('app_agent/remote_bridge.py', '''def execute_job(job, directory, cancel, emit, permission):
    emit('Worker executed')
    if job['operation'] == 'task':
        grant = permission({'id': 'A'}, {'window_handle': 1}, 'Disposable task', cancel)
        return {'actions': list(grant['controls'].values())[0], 'identity': list(grant['controls'])[0]}
    return {'worker_fixture': True}
''')
        z.writestr('app_agent-'+version+'.dist-info/METADATA', 'Name: app-agent\nVersion: '+version+'\nRequires-Python: >=3.11\n'+dependency)
    return buffer.getvalue()


def manifest(keys, data, version='0.7.1'):
    import hashlib
    release = {'version': version, 'minimum_host': '0.7.0', 'protocol': 1,
               'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    return {'release': release, 'signature': encode(keys.signing.sign(canonical(release)))}


class WorkerUpdateTests(unittest.TestCase):
    def test_signed_update_runs_in_a_real_child_and_keeps_local_permission_identity(self):
        keys = ControllerKeys(); data = wheel(); signed = manifest(keys, data)
        baseline = Parser().parsestr('Requires-Python: >=3.11\n')
        with tempfile.TemporaryDirectory(prefix='worker updates with spaces ') as directory:
            manager = WorkerUpdates(directory, keys.public(), fetch=lambda url, limit: json.dumps(signed).encode() if url == MANIFEST_URL else data, host_version='0.7.0')
            manager.baseline = baseline
            logs = []
            manager.check(logs.append)
            self.assertEqual(manager.version, '0.7.1')
            result = run_worker(manager.wheel, {'operation': 'task'}, directory, threading.Event(), logs.append,
                                lambda *args: {'controls': {('edit', 'Edit', 'Editor'): ('type',)}})
            self.assertEqual(result, {'actions': ['type'], 'identity': ['edit', 'Edit', 'Editor']})
            self.assertIn('Worker executed', logs)

    def test_forged_release_and_changed_hash_cannot_replace_current_worker(self):
        keys = ControllerKeys(); data = wheel(); signed = manifest(keys, data)
        with self.assertRaises(Exception):
            verify_manifest(signed, ControllerKeys().public(), '0.7.0', '0.7.0')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify_wheel(data+b'changed', signed['release'], Parser().parsestr('Requires-Python: >=3.11\n'))

    def test_rollback_and_dependency_changes_are_rejected(self):
        keys = ControllerKeys(); data = wheel()
        self.assertIsNone(verify_manifest(manifest(keys, data), keys.public(), '0.7.2', '0.7.0'))
        newer = wheel(dependency='Requires-Dist: unknown-package\n')
        with self.assertRaisesRegex(ValueError, 'Dependency changes'):
            verify_wheel(newer, manifest(keys, newer)['release'], Parser().parsestr('Requires-Python: >=3.11\n'))

    def test_failed_preflight_retains_previous_version_and_does_not_retry_immediately(self):
        keys = ControllerKeys(); data = wheel(); signed = manifest(keys, data)
        fetch = Mock(side_effect=[json.dumps(signed).encode(), data])
        with tempfile.TemporaryDirectory() as directory, patch('app_agent.worker_update.subprocess.run', return_value=Mock(returncode=1, stdout='')):
            manager = WorkerUpdates(directory, keys.public(), fetch=fetch, host_version='0.7.0')
            manager.baseline = Parser().parsestr('Requires-Python: >=3.11\n')
            manager.check(lambda text: None); manager.check(lambda text: None)
            self.assertIsNone(manager.wheel); self.assertEqual(manager.version, '0.7.0')
            self.assertEqual(fetch.call_count, 2)

    def test_stopped_session_does_not_fetch_or_execute_an_update(self):
        with tempfile.TemporaryDirectory() as directory:
            fetch = Mock(); manager = WorkerUpdates(directory, ControllerKeys().public(), fetch=fetch, host_version='0.7.0')
            stopped = threading.Event(); stopped.set()
            with self.assertRaisesRegex(RuntimeError, 'stopped'):
                manager.execute({}, directory, stopped, lambda text: None)
            fetch.assert_not_called()

    def test_real_child_receives_stop_while_waiting_for_a_local_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'worker.whl'; artifact.write_bytes(wheel())
            stopped = threading.Event()
            def permission(*args):
                stopped.set()
                return None
            started = time.monotonic()
            with self.assertRaises(RuntimeError):
                run_worker(artifact, {'operation': 'task'}, directory, stopped, lambda text: None, permission)
            self.assertLess(time.monotonic() - started, 5)
