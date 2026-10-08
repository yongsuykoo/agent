"""Windows Photoshop COM adapter; executes only the reviewed Adobe DOM scripts."""
import json
import ntpath
import re
import threading
from .photoshop_script import PROBE, render_script


def photoshop_app(app):
    return bool(re.search(r'\b(?:adobe\s+)?photoshop\b', app.get('name', ''), re.I)) and not re.search(r'\b(help|uninstall|update|manual)\b', app.get('name', ''), re.I)


def validate_native_identity(app, info):
    if not isinstance(info, dict) or any(not isinstance(info.get(k), str) or not info[k] or len(info[k]) > 500 for k in ('name', 'version', 'path')):
        raise ValueError('Photoshop native identity is incomplete.')
    if not isinstance(info.get('fonts'), list) or len(info['fonts']) > 300:
        raise ValueError('Photoshop did not return a bounded installed font list.')
    expected = re.match(r'(\d+)', app.get('version', ''))
    actual = re.match(r'(\d+)', info['version'])
    if expected and int(expected[1]) < 100 and (not actual or int(actual[1]) != int(expected[1])):
        raise ValueError('Native Photoshop edition does not match the installed catalog version.')
    executable = app.get('launch_executable', '')
    if executable and ntpath.dirname(executable) and ntpath.normcase(ntpath.normpath(ntpath.dirname(executable))) != ntpath.normcase(ntpath.normpath(info['path'])):
        raise ValueError('Native Photoshop installation path does not match the selected installed executable.')
    return info


def select_photoshop(apps):
    candidates = [a for a in apps if photoshop_app(a)]
    # Discovery can record the same executable in the registry and Start menu.
    by_installation = {}
    for app in candidates:
        executable = app.get('launch_executable') or next((p for p in app.get('executables', [])
            if ntpath.basename(p).casefold() == 'photoshop.exe'), '')
        key = ntpath.normcase(ntpath.normpath(ntpath.dirname(executable) or app.get('location') or app['id']))
        previous = by_installation.get(key)
        def rank(a):
            return (bool(a.get('app_id') or a.get('launch_executable')), len(a.get('automation_registrations', [])), bool(a.get('version')))
        if previous is None or rank(app) > rank(previous):
            by_installation[key] = app
    if len(by_installation) != 1:
        raise RuntimeError('A logo requires one identifiable installed Photoshop edition; found ' + str(len(by_installation)) + '.')
    return next(iter(by_installation.values()))


class Photoshop:
    def __init__(self, app, observation):
        import pythoncom
        import win32com.client
        import win32gui
        import win32process
        pythoncom.CoInitialize()
        self._pythoncom = pythoncom
        self.application = None
        try:
            progids = [r['progid'] for r in app.get('automation_registrations', [])
                       if re.fullmatch(r'Photoshop\.Application(?:\.\d+)?', r.get('progid', ''), re.I)]
            # The unversioned Adobe ProgID is documented, never invented by a model.
            progids = sorted(set(progids), key=lambda s: (s.casefold() == 'photoshop.application', s)) or ['Photoshop.Application']
            for progid in progids:
                try:
                    try:
                        candidate = win32com.client.GetActiveObject(progid)
                    except Exception:
                        candidate = win32com.client.Dispatch(progid)
                    candidate.DoJavaScript('app.bringToFront();')
                    _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
                    if pid != observation.get('process_id'):
                        continue
                    info = json.loads(candidate.DoJavaScript(PROBE))
                    if not re.search(r'photoshop', info.get('name', ''), re.I):
                        continue
                    validate_native_identity(app, info)
                    self.application, self.info = candidate, info
                    break
                except Exception:
                    continue
            if self.application is None:
                raise RuntimeError('Photoshop did not expose an active documented COM interface bound to the selected process.')
            self.info['fonts'] = [f for f in self.info['fonts'] if isinstance(f, str) and 0 < len(f) <= 150]
        except BaseException:
            self.close()
            raise

    def close(self):
        self.application = None
        self._pythoncom.CoUninitialize()

    def render(self, design, directory, name, cancel):
        if cancel.is_set():
            raise RuntimeError('Logo task cancelled.')
        latest = json.loads(self.application.DoJavaScript(PROBE))
        if any(latest.get(k) != self.info.get(k) for k in ('name', 'version', 'path')):
            raise RuntimeError('Photoshop instance changed; native task discarded.')
        stopped = threading.Event()
        def watch():
            while not stopped.wait(.1):
                if cancel.is_set():
                    (directory/'.cancel').touch()
                    return
        watcher = threading.Thread(target=watch, name='logo-cancellation', daemon=True)
        watcher.start()
        try:
            script = render_script(design, directory, name, latest['fonts'])
            observed = json.loads(self.application.DoJavaScript(script))
            if cancel.is_set():
                raise RuntimeError('Logo task cancelled; outputs are not certified.')
            return observed
        finally:
            stopped.set(); watcher.join(timeout=1)
