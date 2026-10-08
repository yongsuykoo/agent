"""Real SQLite/restart tests; desktop/model adapters below are simulations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from app_agent.catalog import Catalog
from app_agent.jobs import Jobs, LeaseLost
from app_agent.job_runtime import run_next
from app_agent.task_director import TaskDirector
from test_catalog import app, snapshot
from test_task_director import Cloud, Desktop, PLAN, reply


class JobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.stamp = 1000
        self.jobs = Jobs(self.temp.name,clock=lambda:self.stamp)

    def tearDown(self):
        self.jobs.close()
        self.temp.cleanup()

    def goal(self):
        return self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)

    def plan(self, checkpoint):
        checkpoint.save_plan({'steps':PLAN['steps'],'os_build':None,'generations':{'start:calculator':1,'start:editor':1}})

    def test_goal_and_authorized_options_survive_database_reopen(self):
        identity = self.jobs.submit('Type exactly: hello',use_vision=True,autonomous=True,window={'handle':2,'process_id':22})
        second = Jobs(self.temp.name)
        try:
            value = second.get(identity)
            self.assertEqual(value['task'],'Type exactly: hello')
            self.assertEqual(value['options'],{'use_vision':True,'autonomous':True,'window':{'handle':2,'process_id':22}})
        finally:
            second.close()

    def test_invalid_permissions_and_unbound_window_rejected_before_queueing(self):
        for options in ({'autonomous':1},{'window':{'handle':2}},{'window':{'handle':2,'process_id':0}},{'use_vision':'yes'}):
            with self.assertRaises(ValueError): self.jobs.submit('Goal',**options)
        for task in ('',None,'x'*8001):
            with self.assertRaises(ValueError): self.jobs.submit(task)
        self.assertEqual(self.jobs.list(),[])

    def test_only_one_desktop_job_across_database_connections(self):
        first,second = self.goal(),self.goal()
        lease = self.jobs.claim(first)
        other = Jobs(self.temp.name,clock=lambda:self.stamp)
        try:
            self.assertIsNone(other.claim(second))
            self.jobs.settle(lease,{'outcome':'blocked'})
            self.assertEqual(other.claim(second).id,second)
        finally:
            other.close()

    def test_expired_owner_cannot_act_after_replacement_claim(self):
        identity = self.goal();old = self.jobs.claim(identity)
        self.stamp += Jobs.LEASE_SECONDS+1
        new = self.jobs.claim(identity)
        with self.assertRaises(LeaseLost): old.begin_effect({'kind':'invoke'})
        self.assertEqual(self.jobs.get(identity)['owner'],new.owner)

    def test_confirmed_dead_process_recovers_without_waiting_ten_minutes(self):
        identity = self.goal();self.jobs.claim(identity)
        reopened = Jobs(self.temp.name,clock=lambda:self.stamp,alive=lambda pid:False)
        try:
            self.assertTrue(reopened.ready())
            self.assertIsNotNone(reopened.claim(identity))
        finally:
            reopened.close()

    def test_action_is_committed_before_actuator_and_recovered_as_uncertain(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        control = Mock()
        def crash(action):
            other = Jobs(self.temp.name)
            try:
                self.assertEqual(other.db.execute('SELECT state FROM effects').fetchone()[0],'pending')
            finally: other.close()
            raise RuntimeError('Actuator lost its connection after dispatch')
        control.act.side_effect = crash
        adapter = lease.desktop(control)
        with self.assertRaises(RuntimeError): adapter.act({'kind':'invoke','target':1})
        with self.assertRaises(LeaseLost): adapter.observe()
        self.stamp += Jobs.LEASE_SECONDS+1
        self.assertIsNone(self.jobs.claim(identity))
        self.assertEqual(self.jobs.get(identity)['status'],'needs_review')
        self.jobs.resume()
        self.assertIsNone(self.jobs.claim(identity))
        control.act.assert_called_once()

    def test_applied_but_unverified_action_is_not_replayed_on_restart(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        lease.desktop(Mock()).act({'kind':'click','target':1})
        self.stamp += Jobs.LEASE_SECONDS+1
        self.assertFalse(self.jobs.ready())
        self.assertEqual(self.jobs.get(identity)['status'],'needs_review')

    def test_verified_checkpoint_is_atomic_and_reusable_after_owner_loss(self):
        identity = self.goal();lease = self.jobs.claim(identity);self.plan(lease)
        effect = lease.begin_effect({'kind':'invoke'});lease.applied(effect)
        lease.verified('42',{'step':1,'record':{'outcome':'result_observed'}})
        self.stamp += Jobs.LEASE_SECONDS+1
        resumed = self.jobs.claim(identity)
        self.assertEqual(self.jobs.get(identity)['verified'],['42'])
        self.assertEqual(resumed.records()[0]['step'],1)
        self.assertEqual(self.jobs.db.execute('SELECT state FROM effects').fetchone()[0],'verified')

    def test_duplicate_checkpoint_cannot_overwrite_proof(self):
        identity=self.goal();lease=self.jobs.claim(identity);self.plan(lease)
        lease.verified('42',{'evidence':'first'})
        with self.assertRaises(ValueError): lease.verified('wrong',{})
        self.assertEqual(self.jobs.get(identity)['verified'],['42'])
        self.assertEqual(lease.records(),[{'evidence':'first'}])

    def test_stop_fences_actions_and_queue_survives_reopen_paused(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        self.jobs.pause()
        with self.assertRaises(LeaseLost): lease.begin_effect({'kind':'type','text':'hello'})
        self.assertEqual(self.jobs.settle(lease,{'outcome':'cancelled'})['status'],'paused')
        self.assertIsNone(self.jobs.claim())
        self.jobs.resume()
        self.assertIsNotNone(self.jobs.claim(identity))

    def test_resume_before_stopped_worker_returns_cannot_revive_its_permissions(self):
        identity=self.goal();lease=self.jobs.claim(identity)
        second=self.goal()
        self.jobs.pause();self.jobs.resume()
        with self.assertRaises(LeaseLost): lease.begin_effect({'kind':'invoke'})
        self.assertIsNone(self.jobs.claim(second))  # In-flight owner has not returned.
        self.assertEqual(self.jobs.settle(lease,{'outcome':'cancelled'})['status'],'queued')
        self.assertIsNotNone(self.jobs.claim(identity))

    def test_cancelled_worker_holds_desktop_until_it_returns_but_cannot_act(self):
        identity=self.goal();lease=self.jobs.claim(identity);second=self.goal()
        self.jobs.cancel(identity)
        self.assertIsNone(self.jobs.claim(second))
        with self.assertRaises(LeaseLost): lease.begin_effect({'kind':'invoke'})
        self.assertEqual(self.jobs.settle(lease,{'outcome':'steps_verified'})['status'],'cancelled')
        self.assertIsNotNone(self.jobs.claim(second))

    def test_stop_after_dispatch_leaves_review_state_even_if_immediately_resumed(self):
        identity=self.goal();lease=self.jobs.claim(identity)
        lease.begin_effect({'kind':'invoke'})
        self.jobs.pause();self.jobs.resume()
        with self.assertRaises(LeaseLost): lease.applied('unknown')
        self.assertEqual(self.jobs.settle(lease,{'outcome':'cancelled'})['status'],'needs_review')
        self.assertIsNone(self.jobs.claim(identity))

    def test_late_worker_cannot_undo_user_cancellation(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        self.jobs.cancel(identity)
        with self.assertRaises(LeaseLost): lease.touch()
        self.assertEqual(self.jobs.settle(lease,{'outcome':'steps_verified'})['status'],'cancelled')

    def test_cloud_network_failure_retries_with_delay_without_desktop_actions(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        result = self.jobs.settle(lease,{'outcome':'error','steps':[{'error':'Cloud HTTP 503 temporarily unavailable'}]})
        self.assertEqual(result['status'],'retry_wait');self.assertEqual(result['due'],1005)
        self.assertIsNone(self.jobs.claim(identity))
        self.stamp = 1005
        self.assertIsNotNone(self.jobs.claim(identity))

    def test_five_incident_attempts_stop_an_endless_paid_retry_loop(self):
        identity = self.goal()
        for attempt in range(5):
            lease = self.jobs.claim(identity)
            result = self.jobs.settle(lease,{'outcome':'error','error':'HTTP 429'})
            self.stamp = result['due']
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['attempts'],5)
        self.assertIsNone(self.jobs.claim(identity))

    def test_missing_key_waits_without_polling_paid_calls(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        self.assertEqual(self.jobs.settle(lease,{'outcome':'error','error':'Cloud needs AGENT_API_KEY'})['status'],'waiting_credentials')
        self.assertFalse(self.jobs.ready());self.assertIsNone(self.jobs.claim())
        self.assertTrue(self.jobs.ready(credentials=True))
        self.assertIsNotNone(self.jobs.claim(credentials=True))

    def test_shutdown_requeues_only_safe_work_and_never_dirty_actions(self):
        identity = self.goal();lease = self.jobs.claim(identity)
        self.assertEqual(self.jobs.settle(lease,{'outcome':'cancelled'},shutdown=True)['status'],'queued')
        lease = self.jobs.claim(identity);lease.begin_effect({'kind':'invoke'})
        self.assertEqual(self.jobs.settle(lease,{'outcome':'cancelled'},shutdown=True)['status'],'needs_review')

    def test_completion_claim_requires_all_durable_checkpoints(self):
        identity = self.goal();lease = self.jobs.claim(identity);self.plan(lease)
        self.assertEqual(self.jobs.settle(lease,{'outcome':'steps_verified'})['status'],'failed')

    def test_real_child_process_exit_recovers_persisted_uncertain_effect_immediately(self):
        script = """import os,sys
from app_agent.jobs import Jobs
j=Jobs(sys.argv[1]);identity=j.submit('Send the prepared message',autonomous=True)
lease=j.claim(identity);lease.begin_effect({'kind':'invoke','target':1})
print(identity,flush=True)
os._exit(0)
"""
        identity = subprocess.check_output([sys.executable,'-c',script,self.temp.name],text=True).strip()
        # This owner's process is really gone; no fabricated clock expiry.
        self.assertFalse(self.jobs.ready())
        self.assertEqual(self.jobs.get(identity)['status'],'needs_review')
        self.assertIsNone(self.jobs.claim(identity))


class JobRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name
        catalog = Catalog(self.path)
        catalog.sync(snapshot([app(),{**app(identity='start:editor'),'name':'Editor','aliases':['Editor']}]))
        catalog.save_blueprint('start:calculator',1,{})
        catalog.save_blueprint('start:editor',1,{})
        catalog.close()
        self.jobs = Jobs(self.path)
        self.calc,self.doc = Desktop(True),Desktop()

    def tearDown(self):
        self.jobs.close();self.temp.cleanup()

    def execute(self, identity, cloud=None, **kwargs):
        return run_next(self.path,cloud or Cloud(),lambda action,obs,automatic:True,lambda text:None,
                        identity=identity,resolve=lambda selected,event:self.calc if selected['id']=='start:calculator' else self.doc,**kwargs)

    def test_real_runner_executes_two_apps_and_retains_two_step_checkpoints(self):
        identity = self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        result = self.execute(identity)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['verified'],['42','42'])
        self.assertEqual(self.doc.value,'42')
        self.assertEqual(self.jobs.db.execute('SELECT count(*) FROM checkpoints').fetchone()[0],2)
        self.assertTrue(all(r[0]=='verified' for r in self.jobs.db.execute('SELECT state FROM effects')))
        self.assertIsNone(self.execute(identity))
        self.assertEqual(len(self.calc.actions),1);self.assertEqual(len(self.doc.actions),1)

    def test_process_restart_after_first_checkpoint_does_not_repeat_calculator(self):
        identity = self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        lease = self.jobs.claim(identity)
        catalog = Catalog(self.path)
        def resolve(app,event):
            if app['id']=='start:calculator': return self.calc
            raise KeyboardInterrupt('simulated abrupt process loss between app steps')
        with self.assertRaises(KeyboardInterrupt):
            TaskDirector(catalog,Cloud(),lambda *args:True,lambda text:None,self.path,resolve=resolve,checkpoint=lease).run(
                self.jobs.get(identity)['task'])
        catalog.close()
        self.assertEqual(self.jobs.get(identity)['verified'],['42'])
        with self.jobs.db:
            self.jobs.db.execute('UPDATE jobs SET lease=0 WHERE id=?',(identity,))
            self.jobs.db.execute('UPDATE desktop_lease SET expires=0')
        result = self.execute(identity)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(self.calc.actions),1);self.assertEqual(self.doc.value,'42')
        self.assertEqual([e['step'] for e in result['result']['steps']],[1,2])

    def test_version_change_preserves_checkpoint_without_replaying_stale_plan(self):
        identity = self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        lease = self.jobs.claim(identity)
        lease.save_plan({'steps':PLAN['steps'],'os_build':None,'generations':{'start:calculator':1,'start:editor':1}})
        lease.verified('42',{'app_id':'start:calculator','generation':1,'step':1,'record':{'outcome':'result_observed'}})
        self.jobs.settle(lease,{'outcome':'error','error':'network timeout'})
        with self.jobs.db: self.jobs.db.execute('UPDATE jobs SET due=0')
        catalog=Catalog(self.path);catalog.sync(snapshot([app(),{**app(version='2',identity='start:editor'),'name':'Editor'}]));catalog.close()
        result=self.execute(identity)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['verified'],['42']);self.assertEqual(self.doc.actions,[])

    def test_app_update_before_any_action_automatically_replans_current_generation(self):
        identity=self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        checkpoint=self.jobs.claim(identity)
        checkpoint.save_plan({'steps':PLAN['steps'],'os_build':None,'generations':{'start:calculator':1,'start:editor':1}})
        self.jobs.settle(checkpoint,{'outcome':'error','error':'network timeout'})
        with self.jobs.db: self.jobs.db.execute('UPDATE jobs SET due=0')
        catalog=Catalog(self.path)
        catalog.sync(snapshot([app(),{**app(version='2',identity='start:editor'),'name':'Editor','aliases':['Editor']}]))
        catalog.close()
        with patch('app_agent.task_director.ensure_blueprint',return_value={}):
            result=self.execute(identity)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['plan']['generations']['start:editor'],2)
        self.assertEqual(len(self.calc.actions),1);self.assertEqual(self.doc.value,'42')

    def test_network_loss_after_an_action_never_retries_that_step(self):
        identity=self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        base=Cloud();calls=0
        def request(**payload):
            nonlocal calls
            calls+=1
            if calls==3: raise RuntimeError('Cloud request timed out')
            return base.request(**payload)
        cloud=Mock();cloud.request.side_effect=request
        result=self.execute(identity,cloud)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(len(self.calc.actions),1);self.assertEqual(self.doc.actions,[])
        self.assertIsNone(self.execute(identity,cloud))

    def test_replaced_selected_window_is_never_automatically_reattached(self):
        identity=self.jobs.submit('Type exactly: hello',window={'handle':2,'process_id':22},autonomous=True)
        factory=Mock();factory.return_value.observe.return_value={**self.doc.observe(),'process_id':99}
        result=self.execute(identity,desktop=factory)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.doc.actions,[])

    def test_selected_editor_uses_persisted_scope_and_exact_output_without_plan_call(self):
        identity=self.jobs.submit('Type exactly: hello',window={'handle':2,'process_id':22},autonomous=True)
        factory=Mock(return_value=self.doc)
        result=self.execute(identity,desktop=factory)
        self.assertEqual(result['status'],'completed');self.assertEqual(self.doc.value,'hello')
        self.assertEqual(result['plan']['steps'][0]['app_id'],'start:editor')

    def test_false_runner_success_cannot_create_durable_verified_output(self):
        identity=self.jobs.submit('Calculate 23 plus 19 and write result in Editor.',autonomous=True)
        runner=Mock();runner.return_value.run.return_value={'outcome':'result_observed','history':[]}
        result=self.execute(identity,runner=runner)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['verified'],[])

    def test_cli_submits_and_reads_saved_goals_without_provider_or_windows(self):
        base=[sys.executable,'-m','app_agent.cli','--data-dir',self.path]
        identity=json.loads(subprocess.check_output([*base,'submit','Type exactly: hello','--autonomous'],text=True))['id']
        result=json.loads(subprocess.check_output([*base,'jobs'],text=True))
        self.assertEqual(result[0]['id'],identity)
        self.assertEqual(result[0]['status'],'queued')
        subprocess.check_call([*base,'pause-jobs'],stdout=subprocess.DEVNULL)
        self.assertTrue(self.jobs.paused())
        subprocess.check_call([*base,'cancel-job',identity],stdout=subprocess.DEVNULL)
        self.assertEqual(self.jobs.get(identity)['status'],'cancelled')


if __name__=='__main__':
    unittest.main()
