"""Bounded unattended work; records failures and never turns them into passes."""
from datetime import datetime
import json
from pathlib import Path
import time


def idle_seconds():
    import ctypes
    from ctypes import wintypes
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount.restype = wintypes.DWORD
    value = LASTINPUTINFO(); value.cbSize = ctypes.sizeof(value)
    if not user32.GetLastInputInfo(ctypes.byref(value)):
        return 0
    return ((kernel32.GetTickCount() - value.dwTime) & 0xffffffff) / 1000


class Maintenance:
    def __init__(self, directory, enabled=True, emit=print):
        self.path = Path(directory) / 'automatic-progress.json'
        self.enabled, self.emit = enabled, emit
        self.pending = None
        from .inventory_events import InventoryEvents
        self.inventory_events = InventoryEvents()
        self.next_inventory, self.next_study = 0, 0
        try:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.state.get('tests'), dict) or not isinstance(self.state.get('history'), list):
                raise ValueError('Invalid progress file.')
        except (OSError, ValueError, AttributeError):
            self.state = {'tests': {}, 'history': []}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def tick(self, session, worker_version, idle=0):
        if not self.enabled or not session.active():
            return
        now = time.monotonic()
        if self.inventory_events.poll():
            self.next_inventory = 0
        if self.pending:
            identity, operation, test_key, started_version = self.pending
            result = session.get(identity)
            if result['status'] in ('queued', 'running'):
                return
            evidence = {'job_id': identity, 'operation': operation, 'status': result['status'],
                        'worker_version': result.get('result', {}).get('agent_version', started_version)}
            if operation == 'self_test':
                counts = result.get('result', {}).get('counts', {})
                evidence['counts'] = counts
                evidence['report_path'] = result.get('result', {}).get('report_path')
                entry = self.state['tests'][test_key]
                entry['last_counts'] = counts
                entry['failed'] = result['status'] != 'completed' or not counts or counts.get('failed', 0) > 0 or counts.get('cancelled', 0) > 0
                if entry['failed']:
                    self.emit('Automatic tests retained a failure; waiting for a new worker version before retesting.')
            if result.get('error'):
                evidence['error'] = result['error']
            self.state['history'] = (self.state['history'] + [evidence])[-100:]
            self.pending = None
            self.save()
        with session.lock:
            if any(job['status'] in ('queued', 'running') for job in session.jobs.values()):
                return
        # Both authorization and desktop inactivity must hold before self-tests.
        day = datetime.now().astimezone().date().isoformat()
        key = worker_version + '/' + day + ('/cloud' if session.allow_cloud else '/native')
        entry = self.state['tests'].get(key, {'attempts': 0, 'failed': False})
        if now >= self.next_inventory:
            operation, parameters = 'inventory', {}
            self.next_inventory = now + 300
            self.inventory_events.scanned()
        elif session.allow_tests and idle >= 60 and entry['attempts'] < 2 and not entry['failed']:
            operation, parameters = 'self_test', {'with_cloud': session.allow_cloud, 'with_voice': session.allow_cloud}
            entry['attempts'] += 1
            self.state['tests'][key] = entry
        elif session.allow_cloud and now >= self.next_study:
            operation, parameters = 'study', {'daily_limit': 5, 'max_apps': 3, 'max_plans': 1}
            self.next_study = now + 300
        else:
            return
        try:
            job = session.enqueue({'operation': operation, 'parameters': parameters})
        except ValueError as error:
            self.emit('Automatic work deferred: ' + str(error))
            return
        self.pending = (job['id'], operation, key, worker_version)
        self.save()
        self.emit('Automatic work started: ' + operation + '. Results are saved locally; STOP remains available.')

    def close(self):
        self.inventory_events.close()
