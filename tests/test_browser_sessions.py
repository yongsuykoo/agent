"""Owned-profile identity, origin binding, process ownership and recovery."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from app_agent.browser import Browser,browser_request
from app_agent.browser_sessions import BrowserSessions,login_session,origin,session_name
from app_agent.browser_tasks import run_browser
from app_agent.catalog import Catalog
from app_agent.cli import main
from app_agent.jobs import Jobs
from app_agent.task_director import TaskDirector
from app_agent.browser_checks import FixturePlanner
from test_browser import Adapter,TASK

NAMED=TASK.replace('Open "https://example.com/form" in a browser and','Use browser session "work" at "https://example.com/form" to')


class SessionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=BrowserSessions(self.root,check_url=lambda url:None)
        self.meta=self.store.create('Work','https://example.com/sign-in')
    def tearDown(self):self.temp.cleanup()
    def test_names_are_bounded_and_never_interpreted_as_paths(self):
        for value in ('../work','work/other','','x'*33,'a b',None):
            with self.subTest(value=value),self.assertRaises(ValueError):session_name(value)
        self.assertEqual(session_name('Work'),'work')
        self.assertTrue(self.store.folder('CON').name.startswith('session-'))
        self.assertEqual(self.store.folder('Work'),self.store.folder('work'))
    def test_origin_matches_default_port_case_and_international_names(self):
        self.assertEqual(origin('https://EXAMPLE.com:443/other?a=b'),'https://example.com')
        self.assertEqual(origin('https://bücher.example/path'),'https://xn--bcher-kva.example')
        self.assertEqual(origin('http://[::1]:8765/path'),'http://[::1]:8765')
        for value in ('file:///tmp/a','https://user:pass@example.com','https://example.com:bad'):
            with self.assertRaises(ValueError):origin(value)
    def test_create_is_idempotent_but_cannot_rebind_existing_account(self):
        self.assertEqual(self.meta,self.store.create('WORK','https://example.com:443/other'))
        with self.assertRaisesRegex(ValueError,'another site'):self.store.create('work','https://other.example.com')
        for url in ('https://other.example.com','http://example.com','https://example.com:8443'):
            with self.assertRaisesRegex(ValueError,'origin'):self.store.get('work',url)
    def test_registry_lists_only_metadata_without_network_or_cookie_reads(self):
        profile=self.store.get('work').profile;(profile/'Cookies').write_bytes(b'private-cookie-fixture')
        self.store.check_url=Mock(side_effect=RuntimeError('offline'))
        value=self.store.list()
        self.assertEqual(value,[{k:self.meta[k] for k in ('name','origin','created_at')}])
        self.store.check_url.assert_not_called();self.store.get('work').validate()
        with self.assertRaisesRegex(RuntimeError,'offline'):self.store.get('work','https://example.com')
    def test_marker_and_strict_metadata_stop_account_substitution(self):
        path=self.store.folder('work')/'session.json'
        for extra in ({'cookie':'secret'},{'name':'other'},{'id':'bad'},{'origin':'https://example.com/path'}):
            path.write_text(json.dumps({**self.meta,**extra}))
            with self.assertRaises(ValueError):self.store.get('work')
        path.write_text(json.dumps(self.meta))
        (self.store.get('work').profile/'app-agent-profile-id').write_text('0'*32)
        with self.assertRaisesRegex(ValueError,'identity'):self.store.get('work')
    def test_oversized_or_partial_registry_never_adopts_a_profile(self):
        path=self.store.folder('work')/'session.json';path.write_text(' '*4097)
        with self.assertRaisesRegex(ValueError,'size'):self.store.get('work')
        path.unlink()
        with self.assertRaisesRegex(RuntimeError,'not configured'):self.store.create('work','https://example.com')
    def test_rotation_invalidates_existing_handles_and_workflow_generation(self):
        old=self.store.get('work');self.store.rotate('work');new=self.store.get('work')
        self.assertEqual(old.profile,new.profile);self.assertEqual(old.metadata['id'],new.metadata['id'])
        self.assertNotEqual(old.metadata['revision'],new.metadata['revision'])
        with self.assertRaisesRegex(RuntimeError,'changed'):old.validate()
    def test_busy_profile_refuses_open_delete_and_rotation_then_releases(self):
        first=self.store.get('work');first.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError,'already in use'):self.store.get('work').acquire()
            with self.assertRaisesRegex(RuntimeError,'already in use'):self.store.remove('work')
            with self.assertRaisesRegex(RuntimeError,'already in use'):self.store.rotate('work')
            browser=Browser(session=self.store.get('work'),check_url=lambda url:None)
            with patch('app_agent.browser.executable',return_value='owned-browser'),patch('app_agent.browser.subprocess.Popen') as start:
                with self.assertRaisesRegex(RuntimeError,'already in use'):browser.start('https://example.com')
                start.assert_not_called()
        finally:first.close()
        second=self.store.get('work');second.acquire();second.close()
    def test_cross_process_lock_releases_after_process_exit(self):
        code='from app_agent.browser_sessions import BrowserSessions; import os,sys; s=BrowserSessions(sys.argv[1],check_url=lambda u:None).get("work"); s.acquire(); print("owned",flush=True); sys.stdin.readline(); os._exit(0)'
        process=subprocess.Popen([sys.executable,'-c',code,str(self.root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'owned')
            with self.assertRaisesRegex(RuntimeError,'already in use'):self.store.get('work').acquire()
            process.stdin.write('exit\n');process.stdin.flush();self.assertEqual(process.wait(timeout=5),0)
            session=self.store.get('work');session.acquire();session.close()
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdin.close();process.stdout.close()
    def test_remove_deletes_only_selected_owned_profile_and_recreation_changes_id(self):
        other=self.store.create('other','https://other.example.com');outside=self.root/'existing-browser';outside.mkdir();(outside/'Cookies').write_text('untouched')
        self.store.remove('work');self.assertEqual(self.store.get('other').metadata,other)
        self.assertEqual((outside/'Cookies').read_text(),'untouched')
        self.assertNotEqual(self.store.create('work','https://example.com')['id'],self.meta['id'])
    @unittest.skipIf(os.name=='nt','POSIX symlink fixture; native reparse checks run separately')
    def test_registry_symlink_cannot_import_an_existing_browser(self):
        original=self.store.folder('work');moved=self.root/'outside';original.rename(moved);original.symlink_to(moved,target_is_directory=True)
        with self.assertRaises(ValueError):self.store.get('work')
    def test_named_grammar_keeps_goal_and_exact_output(self):
        request=browser_request(NAMED);self.assertEqual(request['session'],'work');self.assertEqual(request['expected_result'],'Saved: Hello 世界')
        self.assertNotIn('session',browser_request(TASK))
        with self.assertRaises(ValueError):browser_request(NAMED.replace('"work"','"../work"'))
    def test_cli_listing_and_explicit_forget_never_output_cookie_data(self):
        output=io.StringIO()
        with patch('sys.argv',['agent','--data-dir',str(self.root),'browser-sessions']),patch('sys.stdout',output):main()
        self.assertEqual(json.loads(output.getvalue())[0]['name'],'work');self.assertNotIn(self.meta['id'],output.getvalue())
        with patch('sys.argv',['agent','--data-dir',str(self.root),'forget-browser-session','work']),patch('sys.stdout',io.StringIO()):main()
        self.assertEqual(self.store.list(),[])
    def test_manual_login_rotates_generation_without_claiming_authentication(self):
        browser=Mock();browser.process.poll.side_effect=[None,0];output=[]
        before=self.meta['revision']
        with patch('app_agent.browser_sessions.BrowserSessions',return_value=self.store),patch('app_agent.browser.Browser',return_value=browser) as factory:
            value=login_session(self.root,'work','https://example.com/sign-in',output.append)
        self.assertEqual(value['authentication'],'not_assumed');self.assertTrue(factory.call_args.kwargs['manual_login'])
        browser.observe.assert_not_called();browser.close.assert_called_once()
        self.assertNotEqual(self.store.get('work').metadata['revision'],before)
    def test_cancelled_signin_closes_browser_without_claim_or_generation_change(self):
        event=threading.Event();browser=Mock();browser.start.side_effect=lambda url:event.set()
        with patch('app_agent.browser_sessions.BrowserSessions',return_value=self.store),patch('app_agent.browser.Browser',return_value=browser):
            with self.assertRaisesRegex(RuntimeError,'stopped'):login_session(self.root,'work','https://example.com',lambda text:None,event)
        browser.close.assert_called_once();self.assertEqual(self.store.get('work').metadata,self.meta)
    def test_busy_queue_waits_without_retry_budget_or_unverified_replay(self):
        jobs=Jobs(self.root,clock=lambda:1000)
        try:
            identity=jobs.submit(NAMED,autonomous=True);checkpoint=jobs.claim(identity)
            jobs.db.execute('UPDATE jobs SET attempts=9 WHERE id=?',(identity,));jobs.db.commit()
            value=jobs.settle(checkpoint,{'outcome':'error','error':'Browser session is already in use; wait for its browser to close.'})
            self.assertEqual((value['status'],value['due']),('retry_wait',1030))
            second=jobs.submit(NAMED,autonomous=True);checkpoint=jobs.claim(second);checkpoint.begin_effect({'kind':'click','target':4})
            self.assertEqual(jobs.settle(checkpoint,{'outcome':'error','error':'Browser session is already in use'})['status'],'needs_review')
        finally:jobs.close()


class TaskSessionTests(unittest.TestCase):
    setUp=SessionsTests.setUp
    tearDown=SessionsTests.tearDown
    # Independent task integration tests below use a simulated DOM; the smoke
    # suite separately verifies actual retained Chromium authentication.
    def test_task_replay_binds_profile_revision_and_account_origin(self):
        catalog=Catalog(self.root);cloud=FixturePlanner()
        class AccountAdapter(Adapter):
            def __init__(self,guard,session):super().__init__(guard);self.session=session
            def start(self,url):self.session.check_url(url);self.session.acquire();return super().start(url)
            def close(self):self.session.close();super().close()
        director=TaskDirector(catalog,cloud,lambda *args:True,lambda text:None,self.root,threading.Event())
        def run():return run_browser(director,NAMED,browser_request(NAMED),browser_factory=AccountAdapter,session_store=self.store)
        try:
            self.assertEqual(run()['outcome'],'steps_verified');calls=cloud.calls
            self.assertEqual(run()['outcome'],'steps_verified');self.assertEqual(cloud.calls,calls)
            self.store.rotate('work');self.assertEqual(run()['outcome'],'steps_verified');self.assertGreater(cloud.calls,calls)
            wrong=NAMED.replace('https://example.com/form','https://other.example.com/form')
            factory=Mock();result=run_browser(director,wrong,browser_request(wrong),browser_factory=factory,session_store=self.store)
            self.assertEqual(result['outcome'],'verification_failed');factory.assert_not_called()
        finally:catalog.close()
    def test_verified_history_survives_profile_deletion_without_reopening_site(self):
        catalog=Catalog(self.root);jobs=Jobs(self.root);checkpoint=jobs.claim(jobs.submit(NAMED,autonomous=True))
        director=TaskDirector(catalog,FixturePlanner(),lambda *args:True,lambda text:None,self.root,threading.Event(),checkpoint=checkpoint)
        class AccountAdapter(Adapter):
            def __init__(self,guard,session):super().__init__(guard)
        try:
            result=run_browser(director,NAMED,browser_request(NAMED),browser_factory=AccountAdapter,session_store=self.store)
            self.assertEqual(result['outcome'],'steps_verified');self.store.remove('work')
            factory=Mock();result=run_browser(director,NAMED,browser_request(NAMED),browser_factory=factory,session_store=self.store)
            self.assertEqual(result['outcome'],'steps_verified');factory.assert_not_called();self.assertIn('Previously observed',result['scope'])
        finally:jobs.close();catalog.close()


if __name__=='__main__':unittest.main()
