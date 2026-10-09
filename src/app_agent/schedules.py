"""Atomic local schedules: one outstanding occurrence, no missed-run avalanche."""
from datetime import datetime
import math
import json
import uuid
from .jobs import Jobs


def timestamp(value):
    if isinstance(value,str):
        try:date=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError as error:raise ValueError('Schedule time must be ISO 8601 with a time zone.') from error
        if date.tzinfo is None:raise ValueError('Schedule time needs a UTC offset or Z; no ambiguous local time.')
        value=date.timestamp()
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=253402300799:
        raise ValueError('Schedule time is outside the supported timestamp range.')
    return float(value)


class Schedules:
    def __init__(self,directory,**kwargs):
        self.jobs=Jobs(directory,**kwargs);self.db=self.jobs.db
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,task TEXT NOT NULL,options TEXT NOT NULL,
            interval REAL,state TEXT NOT NULL,next_run REAL,
            active_job TEXT REFERENCES jobs(id),created REAL NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 0,detail TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS schedule_runs (
            schedule_id TEXT NOT NULL REFERENCES schedules(id),slot REAL NOT NULL,
            job_id TEXT NOT NULL REFERENCES jobs(id),PRIMARY KEY(schedule_id,slot));
        ''')

    def close(self):self.jobs.close()

    def create(self,task,*,at,interval=None,autonomous=False,use_vision=False):
        at=timestamp(at);options=self.jobs.options(task,use_vision,autonomous)
        if interval is not None and (type(interval) not in (int,float) or not math.isfinite(interval) or not 60<=interval<=2678400):
            raise ValueError('Repeat interval must be between one minute and 31 days.')
        identity=uuid.uuid4().hex
        with self.db:self.db.execute('INSERT INTO schedules(id,task,options,interval,state,next_run,created) VALUES (?,?,?,?,?,?,?)',
            (identity,task.strip(),json.dumps(options),interval,'enabled',at,self.jobs.clock()))
        return identity

    def get(self,identity):
        row=self.db.execute('SELECT * FROM schedules WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError('Schedule not found.')
        item=dict(row);item['options']=json.loads(item['options']);return item

    def list(self):return [self.get(row[0]) for row in self.db.execute('SELECT id FROM schedules ORDER BY created,id')]

    def pause(self,identity):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            item=self.get(identity)
            if item['state']!='enabled':self.db.commit();return False
            if item['active_job']:
                previous=self.jobs.get(item['active_job'])
                if previous['status'] not in ('completed','failed','cancelled','needs_review'):
                    dirty=self.db.execute("SELECT 1 FROM effects WHERE job_id=? AND state!='verified' LIMIT 1",(previous['id'],)).fetchone()
                    self.db.execute('UPDATE jobs SET status=?,updated=?,detail=? WHERE id=?',
                        ('needs_review' if dirty else 'paused_schedule',self.jobs.clock(),'Scheduled occurrence paused locally.',previous['id']))
            self.db.execute("UPDATE schedules SET state='paused',detail='Paused locally.' WHERE id=?",(identity,))
            self.db.commit();return True
        except BaseException:self.db.rollback();raise

    def resume(self,identity):
        # Keep an uncertain/failed occurrence visible; resume is never a replay grant.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            item=self.get(identity)
            if item['state']!='paused':self.db.commit();return False
            if item['active_job']:
                previous=self.jobs.get(item['active_job'])
                if previous['status']=='paused_schedule':
                    if previous['owner'] is None:
                        self.db.execute("UPDATE jobs SET status='queued',due=? WHERE id=?",(self.jobs.clock(),previous['id']))
                elif previous['status']!='completed':
                    dirty=self.db.execute("SELECT 1 FROM effects WHERE job_id=? AND state!='verified' LIMIT 1",(previous['id'],)).fetchone()
                    if previous['status'] not in ('failed','cancelled') or item['interval'] is None or dirty:
                        raise ValueError('Outstanding occurrence needs review; it cannot be replayed by resuming the schedule.')
                    self.db.execute('UPDATE schedules SET active_job=NULL,next_run=? WHERE id=?',
                        (max(item['next_run'] or 0,self.jobs.clock()+item['interval']),identity))
            self.db.execute("UPDATE schedules SET state='enabled',detail='Future work resumed; previous evidence retained.' WHERE id=?",(identity,))
            self.db.commit();return True
        except BaseException:self.db.rollback();raise

    def cancel(self,identity):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            item=self.get(identity)
            if item['active_job']:
                self.db.execute("UPDATE jobs SET status='cancelled',updated=?,detail='Schedule cancelled locally.' WHERE id=? AND status!='completed'",(self.jobs.clock(),item['active_job']))
            changed=self.db.execute("UPDATE schedules SET state='cancelled',detail='Cancelled locally.' WHERE id=? AND state NOT IN ('cancelled','completed')",(identity,)).rowcount
            self.db.commit();return bool(changed)
        except BaseException:self.db.rollback();raise

    def tick(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            stamp=self.jobs.clock();created=[]
            if not self.jobs.paused():
                for row in self.db.execute("SELECT * FROM schedules WHERE state='enabled' ORDER BY next_run,id").fetchall():
                    item=dict(row)
                    if item['active_job']:
                        previous=self.jobs.get(item['active_job'])
                        if previous['status']=='completed':
                            if item['interval'] is None:
                                self.db.execute("UPDATE schedules SET state='completed',detail='Scheduled output verified.' WHERE id=?",(item['id'],));continue
                            self.db.execute('UPDATE schedules SET active_job=NULL WHERE id=?',(item['id'],))
                        elif previous['status']=='paused_schedule' and previous['owner'] is None:
                            self.db.execute("UPDATE jobs SET status='queued',due=? WHERE id=?",(stamp,previous['id']));continue
                        elif previous['status'] in ('failed','cancelled','needs_review'):
                            self.db.execute("UPDATE schedules SET state='paused',detail=? WHERE id=?",('Previous occurrence '+previous['status']+'; no automatic repeat.',item['id']));continue
                        else:continue
                    if item['next_run'] is None or item['next_run']>stamp:continue
                    slot=item['next_run']
                    if item['interval'] is not None:slot+=math.floor((stamp-slot)/item['interval'])*item['interval']
                    job_id=self.jobs._insert(item['task'],json.loads(item['options']),stamp)
                    self.db.execute('INSERT INTO schedule_runs VALUES (?,?,?)',(item['id'],slot,job_id))
                    self.db.execute('UPDATE schedules SET active_job=?,next_run=?,occurrences=occurrences+1,detail=? WHERE id=?',
                        (job_id,slot+item['interval'] if item['interval'] else None,'Occurrence queued; missed slots coalesced.',item['id']))
                    created.append(job_id)
            self.db.commit();return created
        except BaseException:self.db.rollback();raise
