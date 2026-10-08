"""Fixed local child worker protocol; keeps the parent connection unchanged."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

BOOT = "import sys,runpy; sys.path.insert(0,sys.argv[1]); runpy.run_module('app_agent.worker_process',run_name='__main__')"
PREFLIGHT = "import sys; sys.path.insert(0,sys.argv[1]); from app_agent import worker_process,remote_bridge,self_test; print('worker-ready')"


def command(wheel, preflight=False):
    return [sys.executable, '-I', '-u', '-c', PREFLIGHT if preflight else BOOT, str(wheel)]


def run_worker(wheel, job, directory, cancel, emit, permission=None):
    """Only execute a validated job in a verified, locally selected wheel."""
    child = subprocess.Popen(command(wheel), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
    lock = threading.Lock()
    finished = threading.Event()
    def send(value):
        with lock:
            child.stdin.write(json.dumps(value, ensure_ascii=True) + '\n')
            child.stdin.flush()
    def cancellation():
        while not finished.wait(.1):
            if cancel.is_set():
                try:
                    send({'type': 'cancel'})
                except (OSError, ValueError):
                    pass
                # Provider requests are bounded at 90s; terminate a hung child.
                if not finished.wait(100):
                    child.kill()
                return
    try:
        send({'type': 'job', 'job': job, 'directory': str(Path(directory))})
        threading.Thread(target=cancellation, daemon=True).start()
        while True:
            line = child.stdout.readline(12_000_001)
            if not line:
                raise RuntimeError('Automation worker exited without a result.')
            if len(line) > 12_000_000 or not line.endswith('\n'):
                raise RuntimeError('Automation worker message exceeds the limit.')
            packet = json.loads(line)
            kind = packet.get('type')
            if kind == 'log':
                emit(packet['text'])
            elif kind == 'permission':
                grant = permission(packet['app'], packet['observation'], packet['task'], cancel) if permission and not cancel.is_set() else None
                if grant:
                    grant = {**grant, 'controls': [[list(identity), list(actions)] for identity, actions in grant['controls'].items()]}
                send({'type': 'grant', 'grant': grant})
            elif kind == 'result':
                return packet['value']
            elif kind == 'error':
                raise RuntimeError(packet['error'])
            else:
                raise RuntimeError('Unsupported automation worker message.')
    finally:
        finished.set()
        child.stdin.close()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(timeout=5)
        child.stdout.close()


def main():
    protocol = sys.stdout
    sys.stdout = sys.stderr
    first = json.loads(sys.stdin.readline(32769))
    if first.get('type') != 'job':
        raise ValueError('A fixed job is required.')
    cancel = threading.Event()
    grants = __import__('queue').Queue()
    def read():
        for line in sys.stdin:
            value = json.loads(line)
            if value.get('type') == 'cancel':
                cancel.set()
            elif value.get('type') == 'grant':
                grants.put(value.get('grant'))
        cancel.set()
    threading.Thread(target=read, daemon=True).start()
    def write(value):
        protocol.write(json.dumps(value, ensure_ascii=True) + '\n'); protocol.flush()
    def permission(app, observation, task, event):
        write({'type': 'permission', 'app': app, 'observation': observation, 'task': task})
        import queue
        while not event.is_set():
            try:
                grant = grants.get(timeout=.1)
                if grant:
                    grant['controls'] = {tuple(identity): tuple(actions) for identity, actions in grant['controls']}
                return grant
            except queue.Empty:
                continue
        return None
    cleanup = None
    try:
        if sys.platform == 'win32':
            from .automation_worker import initialize_com
            cleanup = initialize_com()
        from .remote_bridge import execute_job
        result = execute_job(first['job'], Path(first['directory']), cancel,
                             lambda text: write({'type': 'log', 'text': str(text)}), permission)
        write({'type': 'result', 'value': result})
    except Exception as error:
        detail = str(error)
        for name in ('AGENT_API_KEY', 'OPENAI_API_KEY'):
            if os.environ.get(name):
                detail = detail.replace(os.environ[name], '[redacted]')
        write({'type': 'error', 'error': detail[:2000]})
    finally:
        if cleanup:
            cleanup()


if __name__ == '__main__':
    main()
