"""Real persistence/process locks; Windows desktop and native credentials simulated."""
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,MagicMock,patch
from app_agent.catalog import Catalog
from app_agent.jobs import Jobs,LeaseLost
from app_agent.job_runtime import run_next
from app_agent.resident import Supervisor,desktop_available,run_resident,background_study
from app_agent.session_lock import SessionLock,ui_open
from app_agent.local_credentials import save_key,load_key,forget_key,configured_key
from app_agent.startup import command,set_startup,startup_enabled
from app_agent.cli import main


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.run=Mock(return_value=None);self.available=Mock(return_value=True);self.key=Mock(return_value=None)
        self.scan=Mock();self.presence=Mock(return_value=False);self.study=Mock();self.now=100
        self.worker=Supervisor(self.temp.name,lambda _:None,available=self.available,idle=lambda:10,clock=lambda:self.now,
            run=self.run,key_reader=self.key,scanner=self.scan,presence=self.presence,study=self.study)
    def tearDown(self):self.temp.cleanup()
    def job(self,autonomous=True):
        jobs=Jobs(self.temp.name)
        try:return jobs.submit('A requested goal',autonomous=autonomous)
        finally:jobs.close()
    def state(self):return json.loads((Path(self.temp.name)/'worker-status.json').read_text())['state']
    def test_paused_locked_busy_and_gui_sessions_do_not_dispatch_or_scan(self):
        self.job();self.available.return_value=False;self.worker.step();self.assertEqual(self.state(),'waiting_desktop')
        self.available.return_value=True;self.presence.return_value=True;self.worker.step();self.assertEqual(self.state(),'gui_open')
        self.presence.return_value=False;self.worker.idle=lambda:0;self.worker.step();self.assertEqual(self.state(),'waiting_idle')
        self.worker.stop();self.worker.cancel.clear();self.worker.step();self.assertEqual(self.state(),'queue_paused')
        self.run.assert_not_called();self.scan.assert_not_called()
    def test_worker_executes_autonomous_jobs_only_and_checks_desktop_at_every_checkpoint(self):
        self.job(False);identity=self.job();self.run.return_value={'id':identity,'status':'completed'}
        self.worker.step();self.assertTrue(self.run.call_args.kwargs['autonomous_only']);self.scan.assert_called_once()
        permit=self.run.call_args.args[2];self.assertTrue(permit({}, {},True));self.assertFalse(permit({}, {},False))
        self.available.return_value=False
        with self.assertRaisesRegex(RuntimeError,'Interactive desktop unavailable'):self.run.call_args.kwargs['execution_guard']()
        self.assertEqual(self.state(),'goal_completed')
    def test_no_credentials_still_permit_local_cached_goals_and_no_background_cloud_call(self):
        self.job();self.worker.step();cloud=self.run.call_args.args[1]
        self.assertIsNone(cloud.client);self.study.assert_not_called()
        with self.assertRaisesRegex(RuntimeError,'AGENT_API_KEY'):cloud.request(input='test')
    def test_credentials_wake_once_per_key_and_are_not_written_to_worker_status(self):
        identity=self.job();self.key.return_value='fixture-key-one';self.run.return_value={'id':identity,'status':'waiting_credentials'}
        self.worker.step();self.assertTrue(self.run.call_args.kwargs['credentials']);self.worker.step();self.assertFalse(self.run.call_args.kwargs['credentials'])
        self.key.return_value='fixture-key-two';self.worker.step();self.assertTrue(self.run.call_args.kwargs['credentials'])
        status=(Path(self.temp.name)/'worker-status.json').read_text();self.assertNotIn('fixture-key',status);self.assertNotIn('A requested goal',status)
    def test_credential_wake_is_retained_while_another_owner_holds_desktop(self):
        jobs=Jobs(self.temp.name)
        try:
            held=jobs.submit('Held',autonomous=True);lease=jobs.claim(held)
            waiting=jobs.submit('Waiting',autonomous=True)
            with jobs.db:jobs.db.execute("UPDATE jobs SET status='waiting_credentials' WHERE id=?",(waiting,))
            self.key.return_value='fixture-key';self.worker.step();self.run.assert_not_called()
            jobs.settle(lease,{'outcome':'blocked'});self.run.return_value={'id':waiting,'status':'completed'}
            self.worker.step();self.assertTrue(self.run.call_args.kwargs['credentials'])
        finally:jobs.close()
    def test_background_study_is_opt_in_and_rate_spacing_does_not_change_daily_limit(self):
        self.key.return_value='fixture-key';self.worker.step();self.study.assert_not_called()
        catalog=Catalog(self.temp.name)
        try:catalog.set_setting('resident_study',True);catalog.set_setting('daily_limit',0)
        finally:catalog.close()
        self.worker.step();self.worker.step();self.study.assert_called_once();self.assertEqual(self.study.call_args.kwargs['limit'],0)
        self.now+=60;self.worker.step();self.assertEqual(self.study.call_count,2)
    def test_installation_changes_trigger_inspection_before_next_goal(self):
        self.worker.changed=Mock();self.worker.changed.poll.return_value=False
        self.worker.step();self.worker.changed.poll.return_value=True;self.worker.step()
        self.assertEqual(self.scan.call_count,2);self.assertEqual(self.worker.changed.scanned.call_count,2)
    def test_stop_fences_an_existing_owner_and_does_not_erase_goal(self):
        jobs=Jobs(self.temp.name)
        try:
            identity=jobs.submit('Goal',autonomous=True);lease=jobs.claim(identity);self.worker.stop()
            with self.assertRaises(LeaseLost):lease.begin_effect({'kind':'type'})
            self.assertEqual(jobs.get(identity)['status'],'paused')
        finally:jobs.close()
    def test_real_runtime_execution_guard_defers_before_any_effect(self):
        identity=self.job()
        result=run_next(self.temp.name,Mock(),Mock(),lambda _:None,identity=identity,autonomous_only=True,
            execution_guard=Mock(side_effect=RuntimeError('Interactive desktop unavailable')))
        self.assertEqual(result['status'],'retry_wait')
        jobs=Jobs(self.temp.name)
        try:self.assertEqual(jobs.db.execute('SELECT count(*) FROM effects').fetchone()[0],0)
        finally:jobs.close()
    def test_checkpoint_guard_prevents_native_or_gui_effect_after_desktop_locks(self):
        jobs=Jobs(self.temp.name)
        try:
            identity=jobs.submit('Goal');lease=jobs.claim(identity);lease.guard=Mock(side_effect=RuntimeError('Interactive desktop unavailable'))
            with self.assertRaises(RuntimeError):lease.begin_effect({'kind':'create_artifact'})
            self.assertEqual(jobs.db.execute('SELECT count(*) FROM effects').fetchone()[0],0)
        finally:jobs.close()
    def test_background_reader_uses_existing_parallel_campaign(self):
        catalog=Catalog(self.temp.name)
        try:
            catalog.set_setting('research_workers',4)
            with patch('app_agent.campaign.study_campaign') as campaign:background_study(catalog,Mock(),lambda _:None,cancel=threading.Event(),limit=0)
            self.assertEqual(campaign.call_args.kwargs['research_workers'],4);self.assertEqual(campaign.call_args.kwargs['daily_limit'],0)
        finally:catalog.close()
    def test_supervisor_completes_real_durable_cached_two_app_goal_without_provider_access(self):
        from app_agent.task_director import TaskDirector
        from test_catalog import app,snapshot
        from test_task_director import Desktop,Cloud
        catalog=Catalog(self.temp.name);editor={**app(identity='start:editor'),'name':'Editor','aliases':['Editor']}
        catalog.sync(snapshot([app(),editor]));task='Calculate 23 plus 19 and put the result in Editor.'
        desktops={app()['id']:Desktop(True),editor['id']:Desktop()}
        resolve=lambda selected,cancel:desktops[selected['id']]
        with patch('app_agent.task_director.ensure_blueprint',side_effect=RuntimeError('No manual')):
            initial=TaskDirector(catalog,Cloud(),lambda *args:True,lambda _:None,self.temp.name,resolve=resolve).run(task)
        self.assertEqual(initial['outcome'],'steps_verified');catalog.close()
        jobs=Jobs(self.temp.name)
        try:identity=jobs.submit(task,autonomous=True)
        finally:jobs.close()
        desktops={app()['id']:Desktop(True),editor['id']:Desktop()}
        self.worker.run=lambda *args,**kwargs:run_next(*args,**kwargs,resolve=resolve)
        with patch('app_agent.resident.CloudResearcher',side_effect=RuntimeError('Provider must not be used')) as provider:
            result=self.worker.step();provider.assert_not_called()
        self.assertEqual(result['status'],'completed');self.assertEqual(result['id'],identity)
        self.assertEqual(desktops[editor['id']].value,'42');self.assertEqual(len(result['verified']),2)


class ProcessLockTests(unittest.TestCase):
    def test_native_mutex_rejects_same_process_recursion_and_recovers_abandoned_owner(self):
        kernel=Mock();kernel.CreateMutexW.return_value=100;kernel.WaitForSingleObject.return_value=0x80
        with tempfile.TemporaryDirectory() as directory,patch('app_agent.session_lock.os',types.SimpleNamespace(name='nt')),patch.object(ctypes,'WinDLL',return_value=kernel,create=True):
            lock=SessionLock(directory);other=SessionLock(directory)
            try:
                self.assertTrue(lock.acquire());self.assertFalse(other.acquire())
                kernel.CreateMutexW.assert_called_once();other.close()
                self.assertFalse(SessionLock(directory).acquire())
            finally:lock.close()
            self.assertTrue(other.acquire());other.close()
            self.assertEqual(kernel.ReleaseMutex.call_count,2);self.assertEqual(kernel.CloseHandle.call_count,2)

    def test_native_mutex_busy_and_failed_wait_release_handles_and_local_reservations(self):
        kernel=Mock();kernel.CreateMutexW.return_value=100;kernel.WaitForSingleObject.side_effect=[258,0xFFFFFFFF,0]
        with tempfile.TemporaryDirectory() as directory,patch('app_agent.session_lock.os',types.SimpleNamespace(name='nt')),patch.object(ctypes,'WinDLL',return_value=kernel,create=True):
            self.assertFalse(SessionLock(directory).acquire())
            with self.assertRaises(OSError):SessionLock(directory).acquire()
            with SessionLock(directory):pass
            self.assertEqual(kernel.CloseHandle.call_count,3);kernel.ReleaseMutex.assert_called_once()

    def test_ui_presence_and_duplicate_worker_are_separate_locks(self):
        with tempfile.TemporaryDirectory() as directory:
            with SessionLock(directory,'ui'):
                self.assertTrue(ui_open(directory))
                with SessionLock(directory):
                    other=SessionLock(directory)
                    try:self.assertFalse(other.acquire())
                    finally:other.close()
            self.assertFalse(ui_open(directory))
    @unittest.skipUnless(os.name=='posix','Native POSIX process locking used for cloud acceptance')
    def test_real_process_termination_releases_lock_without_stale_pid_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            code="import sys,time; from app_agent.session_lock import SessionLock; lock=SessionLock(sys.argv[1]); assert lock.acquire(); print('owned',flush=True); time.sleep(30)"
            process=subprocess.Popen([sys.executable,'-c',code,directory],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(),'owned');lock=SessionLock(directory)
                self.assertFalse(lock.acquire());process.terminate();process.wait(timeout=5);self.assertTrue(lock.acquire());lock.close()
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                process.stdout.close()


class CredentialAndStartupTests(unittest.TestCase):
    def test_encrypted_credential_round_trip_is_user_bound_atomic_and_not_plaintext(self):
        fake=types.SimpleNamespace(CryptProtectData=Mock(return_value=b'opaque-encrypted-data'),CryptUnprotectData=Mock(return_value=('label',b'fixture-key')))
        with tempfile.TemporaryDirectory() as directory,patch('app_agent.local_credentials.sys.platform','win32'),patch.dict('sys.modules',{'win32crypt':fake}):
            save_key(directory,'fixture-key');path=Path(directory)/'provider-key.dpapi'
            self.assertNotIn(b'fixture-key',path.read_bytes());self.assertEqual(load_key(directory),'fixture-key')
            self.assertEqual(fake.CryptProtectData.call_args.args[-1],1)
            self.assertEqual(list(Path(directory).glob('.provider-*')),[])
            forget_key(directory);self.assertIsNone(load_key(directory))
    def test_invalid_key_and_link_do_not_call_native_encryption(self):
        fake=types.SimpleNamespace(CryptProtectData=Mock())
        with tempfile.TemporaryDirectory() as directory,patch('app_agent.local_credentials.sys.platform','win32'),patch.dict('sys.modules',{'win32crypt':fake}):
            with self.assertRaises(RuntimeError):save_key(directory,'Error:\nnot a key')
            fake.CryptProtectData.assert_not_called()
            (Path(directory)/'provider-key.dpapi').symlink_to(Path(directory)/'elsewhere')
            with self.assertRaises(ValueError):load_key(directory)
    def test_environment_key_takes_precedence_without_reading_encrypted_file(self):
        with patch.dict(os.environ,{'AGENT_API_KEY':'fixture-key'}),patch('app_agent.local_credentials.load_key') as load:
            self.assertEqual(configured_key('unused'),'fixture-key');load.assert_not_called()
    def test_startup_quotes_paths_and_never_contains_a_provider_key(self):
        with tempfile.TemporaryDirectory(prefix='agent paths ') as directory:
            python=Path(directory)/'python.exe';python.write_bytes(b'fixture');pythonw=python.with_name('pythonw.exe');pythonw.write_bytes(b'fixture')
            value=command(Path(directory)/'data folder',python)
            self.assertIn('pythonw.exe"',value);self.assertIn('"'+str(Path(directory)/'data folder')+'"',value)
            self.assertIn('-m app_agent.cli',value);self.assertNotIn('API_KEY',value)
    def test_login_setting_only_changes_the_owned_current_user_run_value(self):
        registry=MagicMock();registry.HKEY_CURRENT_USER=1;registry.KEY_SET_VALUE=2;registry.REG_SZ=1
        registry.QueryValueEx.return_value=('worker command',1)
        with patch('app_agent.startup.sys.platform','win32'),patch.dict('sys.modules',{'winreg':registry}),patch('app_agent.startup.command',return_value='worker command'):
            set_startup('unused',True);self.assertTrue(startup_enabled());set_startup('unused',False)
        self.assertEqual(registry.CreateKeyEx.call_args.args[0],registry.HKEY_CURRENT_USER)
        self.assertEqual(registry.SetValueEx.call_args.args[1],'PersonalAppAgent');self.assertEqual(registry.DeleteValue.call_args.args[1],'PersonalAppAgent')


class DesktopAndCliTests(unittest.TestCase):
    def test_native_desktop_check_accepts_default_and_rejects_lock_screen(self):
        user=Mock();user.OpenInputDesktop.return_value=100
        def info(handle,index,name,size,needed):name.value='Default';return 1
        user.GetUserObjectInformationW.side_effect=info
        with patch('app_agent.resident.sys.platform','win32'),patch.object(ctypes,'WinDLL',return_value=user,create=True):
            self.assertTrue(desktop_available());user.CloseDesktop.assert_called_once_with(100)
            user.GetUserObjectInformationW.side_effect=lambda handle,index,name,size,needed:0
            self.assertFalse(desktop_available());user.OpenInputDesktop.return_value=0;self.assertFalse(desktop_available())
    def test_non_windows_worker_and_desktop_do_not_claim_native_acceptance(self):
        with patch('app_agent.resident.sys.platform','linux'):
            self.assertFalse(desktop_available())
            with self.assertRaises(RuntimeError):run_resident('unused')
    def test_cli_schedule_creates_persistent_explicit_permissions_and_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            output=io.StringIO()
            with patch.object(sys,'argv',['app-agent','--data-dir',directory,'schedule','Goal','--at','2026-10-08T00:00:00Z','--every-minutes','60','--autonomous']),patch('sys.stdout',output):main()
            identity=json.loads(output.getvalue())['id'];schedules=__import__('app_agent.schedules',fromlist=['Schedules']).Schedules(directory)
            try:
                self.assertEqual(schedules.get(identity)['interval'],3600);self.assertTrue(schedules.get(identity)['options']['autonomous'])
            finally:schedules.close()


if __name__=='__main__':unittest.main()
