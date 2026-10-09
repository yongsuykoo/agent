"""Actual SQLite timing, concurrency and fencing; no native app actions."""
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import threading
import unittest
from app_agent.jobs import Jobs,LeaseLost
from app_agent.schedules import Schedules,timestamp


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=1000
        self.schedules=Schedules(self.temp.name,clock=lambda:self.now)
    def tearDown(self):self.schedules.close();self.temp.cleanup()
    def create(self,**kwargs):return self.schedules.create('Create a requested workbook',at=1000,autonomous=True,**kwargs)
    def complete(self,job_id):
        checkpoint=self.schedules.jobs.claim(job_id)
        checkpoint.save_plan({'steps':[{'app_id':'fixture'}]})
        checkpoint.verified('result',{'output':'result'})
        return self.schedules.jobs.settle(checkpoint,{'outcome':'steps_verified','steps':[]})
    def test_future_and_one_shot_runs_survive_reopen(self):
        identity=self.schedules.create('Goal',at=1100)
        self.assertEqual(self.schedules.tick(),[]);self.now=1100
        job_id=self.schedules.tick()[0];self.assertFalse(self.schedules.jobs.get(job_id)['options']['autonomous'])
        second=Schedules(self.temp.name,clock=lambda:self.now)
        try:
            self.assertEqual(second.tick(),[]);self.assertEqual(second.get(identity)['active_job'],job_id)
        finally:second.close()
        self.complete(job_id);self.schedules.tick();self.assertEqual(self.schedules.get(identity)['state'],'completed')
    def test_missed_slots_coalesce_and_busy_occurrence_does_not_overlap(self):
        identity=self.create(interval=60);self.now=10000
        job_id=self.schedules.tick()[0]
        self.assertEqual(self.schedules.get(identity)['next_run'],10060)
        self.assertEqual(self.schedules.get(identity)['occurrences'],1)
        self.now=20000;self.assertEqual(self.schedules.tick(),[])
        self.complete(job_id);self.assertEqual(len(self.schedules.tick()),1)
        self.assertEqual(self.schedules.get(identity)['next_run'],20020)
        self.assertEqual(len(self.schedules.jobs.list()),2)
    def test_waiting_credentials_review_and_failed_outputs_never_duplicate(self):
        for status in ('waiting_credentials','needs_review','failed'):
            identity=self.create(interval=60);job_id=self.schedules.tick()[0]
            with self.schedules.db:self.schedules.db.execute('UPDATE jobs SET status=? WHERE id=?',(status,job_id))
            self.now+=600;self.assertEqual(self.schedules.tick(),[])
            self.assertEqual(self.schedules.get(identity)['state'],'enabled' if status=='waiting_credentials' else 'paused')
            self.schedules.cancel(identity)
    def test_global_stop_prevents_enqueue_and_resume_coalesces(self):
        identity=self.create(interval=60);self.schedules.jobs.pause();self.now=2000
        self.assertEqual(self.schedules.tick(),[])
        self.schedules.jobs.resume();self.assertEqual(len(self.schedules.tick()),1)
        self.assertEqual(self.schedules.get(identity)['next_run'],2020)
    def test_schedule_pause_stops_queued_occurrence_without_pausing_others(self):
        identity=self.create(interval=60);job_id=self.schedules.tick()[0]
        other=self.schedules.jobs.submit('Other goal',autonomous=True)
        self.schedules.pause(identity)
        self.assertEqual(self.schedules.jobs.get(job_id)['status'],'paused_schedule')
        self.assertFalse(self.schedules.jobs.paused());self.assertIsNone(self.schedules.jobs.claim(job_id))
        lease=self.schedules.jobs.claim(other);self.schedules.jobs.settle(lease,{'outcome':'blocked'})
        self.assertTrue(self.schedules.resume(identity));self.assertIsNotNone(self.schedules.jobs.claim(job_id))
    def test_pause_fences_active_owner_and_immediate_resume_cannot_revive_it(self):
        identity=self.create(interval=60);job_id=self.schedules.tick()[0];lease=self.schedules.jobs.claim(job_id)
        self.schedules.pause(identity);self.schedules.resume(identity)
        with self.assertRaises(LeaseLost):lease.begin_effect({'kind':'type'})
        self.assertEqual(self.schedules.jobs.settle(lease,{'outcome':'cancelled'})['status'],'paused_schedule')
        self.schedules.tick();self.assertEqual(self.schedules.jobs.get(job_id)['status'],'queued')
    def test_dirty_pause_and_cancelled_effect_cannot_be_replayed(self):
        identity=self.create(interval=60);job_id=self.schedules.tick()[0];lease=self.schedules.jobs.claim(job_id)
        lease.begin_effect({'kind':'create_artifact'});self.schedules.pause(identity)
        with self.assertRaises(ValueError):self.schedules.resume(identity)
        self.schedules.jobs.cancel(job_id)
        with self.assertRaises(ValueError):self.schedules.resume(identity)
        self.assertEqual(self.schedules.jobs.get(job_id)['status'],'cancelled')
    def test_failed_clean_occurrence_can_resume_future_runs_only(self):
        identity=self.create(interval=60);old=self.schedules.tick()[0]
        lease=self.schedules.jobs.claim(old);self.schedules.jobs.settle(lease,{'outcome':'error'})
        self.schedules.tick();self.assertTrue(self.schedules.resume(identity));self.assertEqual(self.schedules.tick(),[])
        self.now+=60;new=self.schedules.tick()[0]
        self.assertNotEqual(old,new);self.assertEqual(self.schedules.jobs.get(old)['status'],'failed')
    def test_cancel_schedule_cancels_outstanding_job_and_future_runs(self):
        identity=self.create(interval=60);job_id=self.schedules.tick()[0]
        self.assertTrue(self.schedules.cancel(identity));self.assertFalse(self.schedules.resume(identity));self.now+=10000
        self.assertEqual(self.schedules.tick(),[]);self.assertEqual(self.schedules.jobs.get(job_id)['status'],'cancelled')
    def test_schedule_and_job_creation_roll_back_together(self):
        identity=self.create();self.schedules.db.execute("CREATE TRIGGER reject_runs BEFORE INSERT ON schedule_runs BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(Exception):self.schedules.tick()
        self.assertEqual(self.schedules.jobs.list(),[]);self.assertIsNone(self.schedules.get(identity)['active_job'])
        self.assertEqual(self.schedules.get(identity)['occurrences'],0)
    def test_competing_connections_enqueue_once(self):
        identity=self.create(interval=60);barrier=threading.Barrier(2)
        def tick():
            schedules=Schedules(self.temp.name,clock=lambda:self.now)
            try:barrier.wait(timeout=5);return schedules.tick()
            finally:schedules.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(tick);second=pool.submit(tick);results=[first.result(),second.result()]
        self.assertEqual(sum(map(len,results)),1);self.assertEqual(len(self.schedules.jobs.list()),1)
    def test_timezone_and_invalid_values_are_rejected(self):
        self.assertEqual(timestamp('2026-10-08T08:00:00+08:00'),timestamp('2026-10-08T00:00:00Z'))
        for value in ('2026-10-08T08:00:00',True,float('nan'),-1):
            with self.subTest(value=value),self.assertRaises(ValueError):timestamp(value)
        for value in (True,0,59,float('inf'),2678401):
            with self.subTest(value=value),self.assertRaises(ValueError):self.create(interval=value)
        with self.assertRaises(ValueError):self.schedules.create('Goal',at=1000,autonomous='yes')
    def test_autonomous_worker_filter_leaves_manual_goals_queued(self):
        manual=self.schedules.jobs.submit('Manual goal');auto=self.schedules.jobs.submit('Automatic goal',autonomous=True)
        self.assertTrue(self.schedules.jobs.ready(autonomous_only=True));lease=self.schedules.jobs.claim(autonomous_only=True)
        self.assertEqual(lease.id,auto);self.schedules.jobs.settle(lease,{'outcome':'blocked'})
        self.assertFalse(self.schedules.jobs.ready(autonomous_only=True));self.assertEqual(self.schedules.jobs.get(manual)['status'],'queued')


if __name__=='__main__':unittest.main()
