"""Durable local goals, fenced desktop ownership and write-ahead action evidence.

SQLite transactions survive process loss. Unverified actions are never blindly
replayed: an abandoned step with any action requires review.
"""
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path


class LeaseLost(RuntimeError):
    pass


def process_alive(pid):
    """Only confirmed process death permits early recovery; errors mean unknown."""
    if not pid:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            return ctypes.get_last_error() not in (87,1168)
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


class Jobs:
    LEASE_SECONDS = 600

    def __init__(self, directory, clock=time.time, alive=process_alive):
        self.clock = clock
        self.alive = alive
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(directory) / 'jobs.sqlite3', timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, task TEXT NOT NULL, options TEXT NOT NULL,
            status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
            due REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            owner TEXT, owner_pid INTEGER, lease REAL, plan TEXT, verified TEXT NOT NULL DEFAULT '[]',
            result TEXT, detail TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS effects (
            id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
            step INTEGER NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL,
            created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS checkpoints (
            job_id TEXT NOT NULL REFERENCES jobs(id), step INTEGER NOT NULL,
            result TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(job_id, step));
          CREATE TABLE IF NOT EXISTS desktop_lease (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), job_id TEXT, owner TEXT, expires REAL);
          INSERT OR IGNORE INTO desktop_lease VALUES (1,NULL,NULL,0);
          CREATE TABLE IF NOT EXISTS queue_settings (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
          INSERT OR IGNORE INTO queue_settings VALUES ('paused',0);
          CREATE INDEX IF NOT EXISTS job_due ON jobs(status,due,created);
          CREATE INDEX IF NOT EXISTS effect_step ON effects(job_id,step,state);
        ''')

    def close(self):
        self.db.close()

    def submit(self, task, *, use_vision=False, autonomous=False, window=None):
        if not isinstance(task, str) or not task.strip() or len(task) > 8000:
            raise ValueError('A saved goal must contain 1–8000 characters.')
        if type(use_vision) is not bool or type(autonomous) is not bool:
            raise ValueError('Task permissions must be explicit booleans.')
        if window is not None and (not isinstance(window, dict) or set(window) != {'handle','process_id'}
                or any(type(v) is not int or v <= 0 for v in window.values())):
            raise ValueError('Selected-window tasks need a positive window handle and process ID.')
        identity, stamp = uuid.uuid4().hex, self.clock()
        with self.db:
            self.db.execute('INSERT INTO jobs(id,task,options,status,created,updated,due) VALUES (?,?,?,?,?,?,?)',
                (identity, task.strip(), json.dumps({'use_vision':use_vision, 'autonomous':autonomous,
                    'window':window}), 'queued', stamp, stamp, stamp))
        return identity

    def get(self, identity):
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError('Saved task not found.')
        item = dict(row)
        for field in ('options','plan','verified','result'):
            item[field] = json.loads(item[field]) if item[field] is not None else None
        return item

    def list(self, limit=100):
        return [self.get(r[0]) for r in self.db.execute('SELECT id FROM jobs ORDER BY created DESC LIMIT ?', (limit,))]

    def paused(self):
        return bool(self.db.execute("SELECT value FROM queue_settings WHERE key='paused'").fetchone()[0])

    def pause(self):
        # A running owner is fenced out before its next action. Queued goals stay saved.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("UPDATE queue_settings SET value=1 WHERE key='paused'")
            for row in self.db.execute("SELECT id FROM jobs WHERE status='running'").fetchall():
                dirty = self.db.execute("SELECT 1 FROM effects WHERE job_id=? AND state!='verified' LIMIT 1",(row[0],)).fetchone()
                self.db.execute('UPDATE jobs SET status=?,updated=?,detail=? WHERE id=?',
                    ('needs_review' if dirty else 'paused',self.clock(),
                     'Stopped with an unverified action; no automatic replay.' if dirty else 'Stopped locally; safe checkpoints retained.',row[0]))
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise

    def resume(self):
        with self.db:
            self.db.execute("UPDATE queue_settings SET value=0 WHERE key='paused'")
            self.db.execute("UPDATE jobs SET status='queued',due=?,updated=? WHERE status='paused' AND owner IS NULL",
                            (self.clock(), self.clock()))

    def cancel(self, identity):
        with self.db:
            changed = self.db.execute("UPDATE jobs SET status='cancelled',updated=?,detail='Cancelled locally.' "
                "WHERE id=? AND status NOT IN ('completed','cancelled')", (self.clock(),identity)).rowcount
        return bool(changed)

    def _recover(self, stamp):
        for row in self.db.execute("SELECT id,owner,owner_pid,lease,status FROM jobs WHERE owner IS NOT NULL").fetchall():
            if row['lease'] > stamp and self.alive(row['owner_pid']):
                continue
            dirty = self.db.execute("SELECT 1 FROM effects WHERE job_id=? AND state!='verified' LIMIT 1", (row[0],)).fetchone()
            status = 'needs_review' if dirty else 'queued'
            if row['status'] != 'running':
                status = 'queued' if row['status']=='paused' and not self.paused() else row['status']
            self.db.execute('UPDATE jobs SET status=?,owner=NULL,lease=NULL,detail=?,due=?,updated=? WHERE id=?',
                (status,
                 'Interrupted step has an unverified action; automatic replay stopped.' if dirty else
                 'Interrupted before an action or after a verified checkpoint; resuming.', stamp, stamp, row[0]))
            self.db.execute('UPDATE desktop_lease SET expires=0 WHERE owner=?', (row['owner'],))

    def ready(self, credentials=False):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            stamp = self.clock()
            self._recover(stamp)
            idle = self.db.execute('SELECT expires FROM desktop_lease WHERE singleton=1').fetchone()[0] <= stamp
            available = idle and not self.paused() and bool(self.db.execute(
                "SELECT 1 FROM jobs WHERE (status IN ('queued','retry_wait') AND due<=?) "
                "OR (status='waiting_credentials' AND ?) LIMIT 1", (stamp,int(credentials))).fetchone())
            self.db.commit()
            return available
        except BaseException:
            self.db.rollback(); raise

    def claim(self, identity=None, credentials=False):
        stamp, owner = self.clock(), uuid.uuid4().hex
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._recover(stamp)
            if credentials:
                self.db.execute("UPDATE jobs SET status='queued',due=? WHERE status='waiting_credentials'", (stamp,))
            lock = self.db.execute('SELECT * FROM desktop_lease WHERE singleton=1').fetchone()
            if self.paused() or lock['expires'] > stamp:
                self.db.commit(); return None
            where, params = (" AND id=?", (identity,)) if identity else ('', ())
            row = self.db.execute("SELECT id FROM jobs WHERE status IN ('queued','retry_wait') AND due<=?" + where +
                ' ORDER BY created,id LIMIT 1', (stamp, *params)).fetchone()
            if row is None:
                self.db.commit(); return None
            self.db.execute("UPDATE jobs SET status='running',owner=?,owner_pid=?,lease=?,attempts=attempts+1,updated=? WHERE id=?",
                            (owner, os.getpid(), stamp+self.LEASE_SECONDS, stamp, row[0]))
            self.db.execute('UPDATE desktop_lease SET job_id=?,owner=?,expires=? WHERE singleton=1',
                            (row[0], owner, stamp+self.LEASE_SECONDS))
            self.db.commit()
            return Checkpoint(self, row[0], owner)
        except BaseException:
            self.db.rollback(); raise

    def settle(self, checkpoint, result, *, shutdown=False):
        stamp = self.clock()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            item = self.get(checkpoint.id)
            # STOP/cancel or a replacement owner cannot be undone by late results.
            if item['owner'] != checkpoint.owner:
                self.db.rollback(); return item
            if item['status'] != 'running':
                status = 'queued' if item['status']=='paused' and not self.paused() else item['status']
                self.db.execute('UPDATE jobs SET status=?,owner=NULL,lease=NULL,result=?,updated=? WHERE id=?',
                                (status,json.dumps(result),stamp,item['id']))
                self.db.execute('UPDATE desktop_lease SET job_id=NULL,owner=NULL,expires=0 WHERE owner=?',(checkpoint.owner,))
                self.db.commit()
                return self.get(item['id'])
            dirty = self.db.execute("SELECT 1 FROM effects WHERE job_id=? AND state!='verified' LIMIT 1", (item['id'],)).fetchone()
            errors = ' '.join(str(e.get('error','')) for e in result.get('steps',[]) if isinstance(e,dict))
            errors += ' ' + str(result.get('error',''))
            for entry in result.get('steps',[]):
                if isinstance(entry,dict):
                    errors += ' ' + ' '.join(str(h.get('error','')) for h in entry.get('record',{}).get('history',[]) if isinstance(h,dict))
            outcome = result.get('outcome')
            due, detail = stamp, errors.strip()[:1500]
            complete = bool(item['plan']) and len(item['verified']) == len(item['plan']['steps'])
            if outcome in ('steps_verified','artifacts_verified') and not dirty and complete:
                status, detail = 'completed', 'All planned outputs verified.'
            elif dirty:
                status, detail = 'needs_review', 'Unverified action in the unfinished step; no automatic replay.'
            elif self.paused() or outcome == 'cancelled' and not shutdown:
                status, detail = 'paused', 'Stopped locally; safe checkpoints retained.'
            elif shutdown:
                status, detail = 'queued', 'Application closed; safe checkpoints retained for restart.'
            elif re.search(r'HTTP (?:401|403)\b|needs AGENT_API_KEY|API key', errors, re.I):
                status = 'waiting_credentials'
            elif item['attempts'] < 5 and re.search(r'HTTP (?:408|429|5\d\d)\b|timed?\s*out|timeout|connection|network|temporar|offline', errors, re.I):
                status = 'retry_wait'; due = stamp + min(300, 5 * 2 ** (item['attempts']-1))
            else:
                status = 'failed'
            self.db.execute('UPDATE jobs SET status=?,result=?,detail=?,due=?,updated=?,owner=NULL,lease=NULL WHERE id=?',
                            (status,json.dumps(result),detail,due,stamp,item['id']))
            self.db.execute('UPDATE desktop_lease SET job_id=NULL,owner=NULL,expires=0 WHERE owner=?', (checkpoint.owner,))
            self.db.commit()
            return self.get(item['id'])
        except BaseException:
            self.db.rollback(); raise


class Checkpoint:
    def __init__(self, jobs, identity, owner):
        self.jobs, self.id, self.owner, self.step = jobs, identity, owner, 1

    def _touch(self):
        stamp = self.jobs.clock()
        item = self.jobs.get(self.id)
        lock = self.jobs.db.execute('SELECT * FROM desktop_lease WHERE singleton=1').fetchone()
        if (self.jobs.paused() or item['status'] != 'running' or item['owner'] != self.owner
                or lock['owner'] != self.owner or lock['expires'] <= stamp):
            raise LeaseLost('Saved task stopped or desktop ownership expired; no further action.')
        self.jobs.db.execute('UPDATE jobs SET lease=?,updated=? WHERE id=?', (stamp+self.jobs.LEASE_SECONDS,stamp,self.id))
        self.jobs.db.execute('UPDATE desktop_lease SET expires=? WHERE owner=?', (stamp+self.jobs.LEASE_SECONDS,self.owner))

    def touch(self):
        self.jobs.db.execute('BEGIN IMMEDIATE')
        try:
            self._touch(); self.jobs.db.commit()
        except BaseException:
            self.jobs.db.rollback(); raise

    def save_plan(self, plan):
        self.jobs.db.execute('BEGIN IMMEDIATE')
        try:
            self._touch()
            self.jobs.db.execute('UPDATE jobs SET plan=? WHERE id=?', (json.dumps(plan),self.id))
            self.jobs.db.commit()
        except BaseException:
            self.jobs.db.rollback(); raise

    def pending_actions(self):
        return bool(self.jobs.db.execute("SELECT 1 FROM effects WHERE job_id=? AND step=? AND state!='verified' LIMIT 1",
                                        (self.id,self.step)).fetchone())

    def begin_effect(self, action):
        identity = uuid.uuid4().hex
        self.jobs.db.execute('BEGIN IMMEDIATE')
        try:
            self._touch()
            self.jobs.db.execute('INSERT INTO effects VALUES (?,?,?,?,?,?)',
                (identity,self.id,self.step,json.dumps(action),'pending',self.jobs.clock()))
            self.jobs.db.commit()
        except BaseException:
            self.jobs.db.rollback(); raise
        return identity

    def applied(self, identity):
        self.jobs.db.execute('BEGIN IMMEDIATE')
        try:
            self._touch()
            changed = self.jobs.db.execute("UPDATE effects SET state='applied' WHERE id=? AND job_id=? AND state='pending'",
                                           (identity,self.id)).rowcount
            if changed != 1:
                raise ValueError('Applied effect must refer to one pending action.')
            self.jobs.db.commit()
        except BaseException:
            self.jobs.db.rollback(); raise

    def verified(self, value, result):
        self.jobs.db.execute('BEGIN IMMEDIATE')
        try:
            self._touch()
            item = self.jobs.get(self.id)
            if len(item['verified']) != self.step-1:
                raise ValueError('Checkpoint must follow the preceding verified step.')
            self.jobs.db.execute('INSERT INTO checkpoints VALUES (?,?,?,?)',
                                (self.id,self.step,json.dumps(result),self.jobs.clock()))
            self.jobs.db.execute('UPDATE jobs SET verified=? WHERE id=?', (json.dumps([*item['verified'],value]),self.id))
            self.jobs.db.execute("UPDATE effects SET state='verified' WHERE job_id=? AND step=?", (self.id,self.step))
            self.jobs.db.commit()
        except BaseException:
            self.jobs.db.rollback(); raise

    def records(self):
        return [json.loads(r[0]) for r in self.jobs.db.execute('SELECT result FROM checkpoints WHERE job_id=? ORDER BY step', (self.id,))]

    def desktop(self, desktop):
        return JournalDesktop(desktop, self)


class JournalDesktop:
    def __init__(self, desktop, checkpoint):
        self.wrapped, self.checkpoint, self.uncertain = desktop, checkpoint, False

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def observe(self):
        self.checkpoint.touch()
        if self.uncertain:
            raise LeaseLost('An action failed after dispatch; its effect is unknown. Automatic replay stopped.')
        return self.wrapped.observe()

    def act(self, action):
        if self.uncertain:
            raise LeaseLost('Uncertain action cannot be dispatched again.')
        effect = self.checkpoint.begin_effect(action)
        self.uncertain = True
        self.checkpoint.touch()
        self.wrapped.act(action)
        self.checkpoint.applied(effect)
        self.uncertain = False
