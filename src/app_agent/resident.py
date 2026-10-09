"""A local interactive-session supervisor, independent of the GUI and cloud relay."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from .catalog import Catalog
from .jobs import Jobs
from .schedules import Schedules
from .job_runtime import run_next
from .session_lock import SessionLock,ui_open
from .research import DeferredCloud,CloudResearcher
from .local_credentials import configured_key


def desktop_available():
    if sys.platform!='win32':return False
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];user.OpenInputDesktop.restype=wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
    user.CloseDesktop.argtypes=[wintypes.HANDLE]
    handle=user.OpenInputDesktop(0,False,1)
    if not handle:return False
    try:
        name=ctypes.create_unicode_buffer(256);size=wintypes.DWORD()
        return bool(user.GetUserObjectInformationW(handle,2,name,ctypes.sizeof(name),ctypes.byref(size))) and name.value.casefold()=='default'
    finally:user.CloseDesktop(handle)


class InstallationEvents:
    def __init__(self,directory,emit):
        from .inventory_events import InventoryEvents
        from .installation_watch import InstallationMonitor
        self.registry=InventoryEvents();self.installers=InstallationMonitor(directory,emit)
    def poll(self):return self.registry.poll() or self.installers.poll()
    def scanned(self):self.registry.scanned();self.installers.scanned()
    def close(self):self.registry.close();self.installers.close()


def background_study(catalog,cloud,emit,*,cancel,limit):
    from .campaign import study_campaign
    workers=max(1,min(4,int(catalog.setting('research_workers',3))))
    return study_campaign(catalog,cloud,emit,daily_limit=limit,max_apps=workers,max_plans=0,research_workers=workers,cancel=cancel)


class Supervisor:
    def __init__(self,directory,emit=print,*,cancel=None,available=desktop_available,
                 idle=None,clock=time.monotonic,run=run_next,key_reader=configured_key,
                 scanner=None,presence=ui_open,study=None):
        from .maintenance import idle_seconds
        from .machine import scan_machine
        self.directory=Path(directory);self.emit=emit;self.cancel=cancel or threading.Event()
        self.available,self.idle,self.clock,self.run=available,idle or idle_seconds,clock,run
        self.key_reader,self.scanner,self.presence,self.study=key_reader,scanner or scan_machine,presence,study
        self.key_fingerprint=None;self.wake_credentials=False;self.next_scan=0;self.next_study=0;self.last_state=None
        self.changed=None

    def status(self,state,**details):
        if self.last_state=={'state':state,**details}:return
        self.last_state={'state':state,**details}
        self.directory.mkdir(parents=True,exist_ok=True)
        # Atomic status contains IDs/outcomes only, never the API key or task text.
        path=self.directory/'worker-status.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({**self.last_state,'updated':time.time(),'pid':os.getpid()}),encoding='utf-8');temporary.replace(path)
        self.emit('Background worker: '+state+((' '+str(details)) if details else ''))

    def stop(self):
        self.cancel.set();jobs=Jobs(self.directory)
        try:jobs.pause()
        finally:jobs.close()

    def step(self):
        if self.cancel.is_set():self.status('stopped');return None
        schedules=Schedules(self.directory)
        try:
            schedules.tick();paused=schedules.jobs.paused()
        finally:schedules.close()
        if paused:self.status('queue_paused');return None
        if self.presence(self.directory):self.status('gui_open');return None
        if not self.available():self.status('waiting_desktop');return None
        if self.idle()<5:self.status('waiting_idle');return None
        now=self.clock()
        if now>=self.next_scan or self.changed and self.changed.poll():
            self.next_scan=now+300
            self.status('inspecting_installations');catalog=Catalog(self.directory)
            try:self.scanner(catalog,cancel=self.cancel)
            finally:catalog.close()
            if self.changed:self.changed.scanned()
        try:key=self.key_reader(self.directory)
        except Exception:
            key=None;self.status('credential_unavailable')
        fingerprint=hashlib.sha256(key.encode()).hexdigest() if key else None
        if fingerprint and fingerprint!=self.key_fingerprint:self.wake_credentials=True
        wake=self.wake_credentials
        self.key_fingerprint=fingerprint
        def provider():
            if not key:raise RuntimeError('Cloud research needs AGENT_API_KEY; configure a provider key locally.')
            return CloudResearcher(key=key)
        cloud=DeferredCloud(provider)
        jobs=Jobs(self.directory)
        try:ready=jobs.ready(credentials=wake,autonomous_only=True)
        finally:jobs.close()
        if ready:
            def guard():
                if self.cancel.is_set():raise RuntimeError('Background worker stopped.')
                if not self.available():raise RuntimeError('Interactive desktop unavailable; wait for Windows unlock.')
            self.status('running_goal')
            result=self.run(self.directory,cloud,
                lambda action,observation,automatic: automatic and not self.cancel.is_set() and self.available(),
                self.emit,self.cancel,credentials=wake,autonomous_only=True,execution_guard=guard,
                shutdown=lambda:self.cancel.is_set())
            if result:
                self.wake_credentials=False
                self.status('goal_'+result['status'],job_id=result['id'])
            return result
        # Documentation study is opt-in; local onboarding and queued goals are first.
        catalog=Catalog(self.directory)
        try:
            enabled=catalog.setting('resident_study',False)
            if key and enabled and self.study and now>=self.next_study:
                self.next_study=now+60;self.status('studying_documentation')
                self.study(catalog,cloud,self.emit,cancel=self.cancel,limit=catalog.setting('daily_limit',0))
            else:self.status('idle')
        finally:catalog.close()
        return None


def run_resident(directory,emit=print,once=False):
    if sys.platform!='win32':raise RuntimeError('The background worker requires a logged-in interactive Windows session.')
    from .automation_worker import initialize_com
    from .hotkey import register_stop
    cleanup=None;hotkey=None;changed=None
    with SessionLock(directory):
        supervisor=Supervisor(directory,emit,study=background_study)
        try:
            cleanup=initialize_com();changed=InstallationEvents(directory,emit);supervisor.changed=changed
            for value in (signal.SIGINT,signal.SIGTERM):signal.signal(value,lambda signum,frame:supervisor.stop())
            emit('Background worker started. It executes only submitted autonomous goals. Ctrl+Alt+F12 or pause-jobs stops the queue.')
            while not supervisor.cancel.is_set():
                try:
                    if ui_open(directory):
                        if hotkey:hotkey.set();hotkey=None
                    elif hotkey is None:hotkey=register_stop(supervisor.stop,emit)
                    supervisor.step()
                except Exception as error:
                    # Do not spin or leak provider/task contents into the status file.
                    supervisor.status('deferred',error_type=type(error).__name__)
                if once:break
                supervisor.cancel.wait(2)
        finally:
            supervisor.status('stopped')
            if hotkey:hotkey.set()
            if changed:changed.close()
            if cleanup:cleanup()
