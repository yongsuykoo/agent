"""Real catalog/queue persistence, deterministic desktop and provider adapters."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from app_agent.catalog import Catalog
from app_agent.jobs import Jobs
from app_agent.resident import Supervisor,background_study


class BackgroundLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.now=100
        self.run=Mock();self.study=Mock();self.scan=Mock();self.key=Mock(return_value='fixture-key')
        self.available=Mock(return_value=False)
        self.worker=self.make_worker()
        with self.catalog() as catalog:catalog.set_setting('resident_study',True)

    def catalog(self):
        from contextlib import closing
        return closing(Catalog(self.root))

    def make_worker(self):
        return Supervisor(self.root,lambda _:None,available=self.available,idle=lambda:0,
            clock=lambda:self.now,scanner=self.scan,key_reader=self.key,run=self.run,
            study=self.study,presence=lambda _:False)

    def tearDown(self):self.temp.cleanup()

    def test_locked_discovery_queues_new_app_then_studies_without_desktop(self):
        self.scan.side_effect=lambda catalog,**kw:catalog.sync({'apps':[{'id':'fixture:new','name':'New App','version':'1'}]})
        def study(catalog,*args,**kw):self.assertEqual(catalog.apps()[0]['name'],'New App')
        self.study.side_effect=study;self.worker.step()
        self.run.assert_not_called()
        with self.catalog() as catalog:
            self.assertEqual(catalog.setting('worker_learning')['apps_detected'],1)
            self.assertEqual(catalog.setting('worker_learning')['apps_documented'],0)

    def test_busy_user_does_not_block_readonly_work_or_allow_desktop_actions(self):
        self.available.return_value=True;self.worker.step()
        self.scan.assert_called_once();self.study.assert_called_once();self.run.assert_not_called()

    def test_scan_failure_does_not_starve_study_or_hot_loop_change_event(self):
        self.scan.side_effect=OSError('fixture failure');self.worker.changed=Mock()
        self.worker.changed.poll.return_value=True
        self.worker.step();self.worker.step()
        self.scan.assert_called_once();self.study.assert_called_once()
        self.now+=60;self.worker.step()
        self.assertEqual(self.scan.call_count,2);self.assertEqual(self.study.call_count,2)

    def test_failed_study_backs_off_then_recovers_without_manual_resume(self):
        self.study.side_effect=[RuntimeError('fixture failure'),None]
        self.worker.step();self.worker.step();self.study.assert_called_once()
        self.now+=60;self.worker.step();self.assertEqual(self.study.call_count,2)
        with self.catalog() as catalog:self.assertIsNotNone(catalog.setting('worker_learning'))

    def test_cross_connection_pause_is_seen_inside_readonly_study(self):
        def study(*args,**kwargs):
            jobs=Jobs(self.root)
            try:jobs.pause()
            finally:jobs.close()
            self.assertTrue(kwargs['cancel'].is_set())
        self.study.side_effect=study;self.worker.step()
        with self.catalog() as catalog:self.assertIsNone(catalog.setting('worker_learning'))
        self.assertEqual(json.loads((self.root/'worker-status.json').read_text())['state'],'queue_paused')
        self.worker.step();self.study.assert_called_once()

    def test_missing_credentials_are_visible_and_new_key_resumes_study(self):
        self.key.return_value=None;self.worker.step();self.study.assert_not_called()
        self.assertEqual(json.loads((self.root/'worker-status.json').read_text())['state'],'waiting_credentials')
        self.key.return_value='fixture-key';self.worker.step();self.study.assert_called_once()
        self.assertNotIn('fixture-key',(self.root/'worker-status.json').read_text())

    def test_unchanged_state_updates_heartbeat_without_repeated_messages(self):
        emitted=[];self.worker.emit=emitted.append
        with patch('app_agent.resident.time.time',return_value=500):self.worker.status('idle')
        self.now+=31
        with patch('app_agent.resident.time.time',return_value=531):self.worker.status('idle')
        self.assertEqual(len(emitted),1)
        self.assertEqual(json.loads((self.root/'worker-status.json').read_text())['updated'],531)

    def test_real_manual_learning_resumes_after_worker_restart_with_locked_desktop(self):
        from app_agent.document_fixtures import manual_pdf
        from app_agent.local_inspection import inspect_installation
        from test_manual_continuation import SectionCloud
        install=self.root/'install';install.mkdir();(install/'manual.pdf').write_bytes(manual_pdf(['Type Hello.']*70))
        app={'id':'fixture:editor','name':'Owned Editor','version':'1','source':'fixture','location':str(install)}
        def scan(catalog,**kw):catalog.sync({'apps':[app],'local_evidence':{app['id']:inspect_installation(app,deadline_seconds=3)}})
        self.scan.side_effect=scan;cloud=SectionCloud()
        self.study.side_effect=lambda catalog,_cloud,emit,**kw:background_study(catalog,cloud,emit,**kw)
        self.worker.step();self.worker=self.make_worker();self.worker.step();self.now+=60;self.worker.step()
        with self.catalog() as catalog:
            blueprint=catalog.get(app['id'])['blueprint']
            self.assertEqual([s['read_cursor']['page'] for s in blueprint['sources']],[1,33,65])
            self.assertEqual(catalog.setting('worker_learning')['apps_documented'],1)
            self.assertEqual(catalog.setting('worker_learning')['capabilities_tested_once'],0)
        self.assertEqual(len(cloud.calls),3);self.run.assert_not_called()
