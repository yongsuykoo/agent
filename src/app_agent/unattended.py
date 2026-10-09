"""Durable bounded learning sessions and a local worker watchdog."""
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from .session_lock import SessionLock

COUNTERS=('worker_starts','worker_restarts','scans','study_cycles','goals_completed','errors')


class Sessions:
    def __init__(self,directory,clock=time.time):
        root=Path(directory);root.mkdir(parents=True,exist_ok=True);self.clock=clock
        self.db=sqlite3.connect(root/'unattended.sqlite3',timeout=5)
        self.db.row_factory=sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY,
            state TEXT NOT NULL,started REAL NOT NULL,deadline REAL NOT NULL,
            updated REAL NOT NULL,phase TEXT NOT NULL,counters TEXT NOT NULL,error_type TEXT)''')
        self.db.commit()

    def close(self):self.db.close()

    def current(self):
        row=self.db.execute('SELECT * FROM sessions ORDER BY started DESC,rowid DESC LIMIT 1').fetchone()
        if row is None:return None
        result=dict(row);result['counters']=json.loads(result['counters'])
        if result['state']=='active' and self.clock()>=result['deadline']:
            with self.db:self.db.execute("UPDATE sessions SET state='elapsed',phase='time_budget_elapsed',updated=? WHERE id=? AND state='active'",(self.clock(),result['id']))
            result.update(state='elapsed',phase='time_budget_elapsed')
        result['remaining_seconds']=max(0,result['deadline']-self.clock()) if result['state']=='active' else 0
        return result

    def start(self,hours=10):
        if type(hours) not in (int,float) or not math.isfinite(hours) or not 0<hours<=10:
            raise ValueError('Unattended duration must be greater than zero and at most ten hours.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current=self.current()
            if current and current['state']=='active':self.db.commit();return current
            stamp=self.clock();identity=uuid.uuid4().hex
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)',
                (identity,'active',stamp,stamp+hours*3600,stamp,'starting',json.dumps(dict.fromkeys(COUNTERS,0)),None))
            # Keep a bounded session summary history; app/job evidence is separate.
            self.db.execute('DELETE FROM sessions WHERE id NOT IN (SELECT id FROM sessions ORDER BY started DESC,rowid DESC LIMIT 100)')
            self.db.commit();return self.current()
        except BaseException:self.db.rollback();raise

    def record(self,identity,phase,*,counter=None,error_type=None):
        if counter is not None and counter not in COUNTERS:raise ValueError('Unknown session counter.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current=self.current()
            if not current or current['id']!=identity or current['state']!='active':self.db.commit();return False
            if counter:current['counters'][counter]+=1
            self.db.execute('UPDATE sessions SET updated=?,phase=?,counters=?,error_type=? WHERE id=? AND state=\'active\'',
                (max(self.clock(),current['updated']),phase,json.dumps(current['counters']),error_type,identity))
            self.db.commit();return True
        except BaseException:self.db.rollback();raise

    def finish(self,identity,state='stopped'):
        if state not in ('stopped','elapsed'):raise ValueError('Invalid session terminal state.')
        with self.db:return bool(self.db.execute('UPDATE sessions SET state=?,phase=?,updated=? WHERE id=? AND state=\'active\'',
            (state,'stopped' if state=='stopped' else 'time_budget_elapsed',self.clock(),identity)).rowcount)


class SessionCancellation:
    """All existing research and action checkpoints share the same deadline."""
    def __init__(self,directory,session,event=None,wall=time.time,monotonic=time.monotonic):
        self.directory=directory;self.identity=session['id'];self.deadline=session['deadline']
        self.event=event or threading.Event();self.wall=wall;self.monotonic=monotonic
        self.until=monotonic()+max(0,self.deadline-wall())

    def set(self):self.event.set()

    def is_set(self):
        if self.event.is_set():return True
        store=Sessions(self.directory,clock=self.wall)
        try:
            if self.wall()>=self.deadline or self.monotonic()>=self.until:
                store.finish(self.identity,'elapsed');self.event.set();return True
            current=store.current()
            if not current or current['id']!=self.identity or current['state']!='active':self.event.set();return True
            return False
        finally:store.close()

    def wait(self,timeout=None):
        end=self.monotonic()+timeout if timeout is not None else float('inf')
        while not self.is_set():
            remaining=end-self.monotonic()
            if remaining<=0:return False
            self.event.wait(min(2,remaining,max(0,self.until-self.monotonic())))
        return True


def record(directory,identity,phase,**kwargs):
    store=Sessions(directory)
    try:return store.record(identity,phase,**kwargs)
    finally:store.close()


def stop_session(directory):
    store=Sessions(directory)
    try:
        current=store.current()
        if current:store.finish(current['id'])
    finally:store.close()
    from .jobs import Jobs
    jobs=Jobs(directory)
    try:jobs.pause()
    finally:jobs.close()


def start_session(directory,hours=10,*,launch=True,login=True):
    if launch and sys.platform!='win32':raise RuntimeError('Unattended deployment requires Windows; tests use owned fixture adapters.')
    from .jobs import Jobs
    jobs=Jobs(directory)
    try:
        if jobs.paused():raise RuntimeError('The queue is paused. Resume safe jobs before starting a new unattended session.')
    finally:jobs.close()
    # Configure login recovery first; a failed setup cannot arm a session.
    if launch and login:
        from .startup import set_startup
        set_startup(directory,True)
    store=Sessions(directory)
    try:session=store.start(hours)
    finally:store.close()
    if launch:
        subprocess.Popen([sys.executable,'-m','app_agent.cli','--data-dir',str(Path(directory).absolute()),
            'watch-unattended','--session-id',session['id']],creationflags=0x08000000,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return session


def watch_session(directory,identity,*,spawn=None,cancel=None,wall=time.time,monotonic=time.monotonic):
    """Restart only our child; no remote shell or arbitrary app execution."""
    spawn=spawn or (lambda:subprocess.Popen([sys.executable,'-m','app_agent.cli','--data-dir',str(Path(directory).absolute()),'worker','--session-id',identity],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0))
    store=Sessions(directory,clock=wall)
    try:current=store.current()
    finally:store.close()
    if not current or current['id']!=identity or current['state']!='active':return
    cancellation=SessionCancellation(directory,current,event=cancel,wall=wall,monotonic=monotonic)
    process=None;failures=0
    with SessionLock(directory,'watchdog'):
        try:
            while not cancellation.is_set():
                if process is None:
                    try:process=spawn();record(directory,identity,'worker_starting',counter='worker_starts')
                    except OSError as error:
                        failures+=1;record(directory,identity,'worker_launch_deferred',counter='errors',error_type=type(error).__name__)
                        cancellation.wait(min(60,2**min(failures,6)));continue
                    launched=monotonic()
                if process.poll() is not None:
                    process=None;failures+=1
                    record(directory,identity,'worker_restart_wait',counter='worker_restarts')
                    cancellation.wait(min(60,2**min(failures,6)));continue
                # Long provider calls can take minutes. A ten-minute heartbeat
                # gap is a stalled child, not a reason to repeat an app action.
                status=Path(directory)/'worker-status.json'
                try:
                    state=json.loads(status.read_text(encoding='utf-8'))
                    heartbeat=state.get('updated',0) if state.get('pid')==process.pid else 0
                except (OSError,ValueError):heartbeat=0
                if monotonic()-launched>600 and wall()-heartbeat>600:
                    process.terminate();process.wait(timeout=5);process=None
                    failures+=1;record(directory,identity,'worker_unresponsive',counter='errors',error_type='HeartbeatTimeout')
                    cancellation.wait(min(60,2**min(failures,6)));continue
                cancellation.wait(2)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
