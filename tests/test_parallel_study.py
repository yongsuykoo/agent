import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch, Mock
from app_agent.catalog import Catalog
from app_agent.campaign import study_campaign
from app_agent.learning import ResearchBusy, ensure_blueprint
from test_catalog import app, snapshot


class ParallelStudyTests(unittest.TestCase):
    def test_manual_pages_are_fetched_concurrently_and_keep_citation_order(self):
        from app_agent.research import research_app
        sources=['https://example.com/'+str(i) for i in range(3)]
        barrier=threading.Barrier(3);threads=set();lock=threading.Lock()
        def fetch(url):
            with lock:threads.add(threading.get_ident())
            barrier.wait(3)
            return {'url':url,'text':'Manual '+url,'sha256':'stub'}
        cloud=Mock();cloud.extract.return_value={'capabilities':[{'name':'Operate'}],'limitations':[]}
        result=research_app('App','1',cloud,urls=sources,fetcher=fetch)
        self.assertEqual(len(threads),3)
        self.assertEqual([doc['url'] for doc in cloud.extract.call_args.args[2]],sources)
        self.assertEqual([doc['url'] for doc in result['sources']],sources)

    def test_uncapped_planning_and_practice_counters_continue_after_existing_usage(self):
        from app_agent.campaign import consume_planning_budget
        from app_agent.app_practice import consume_practice_budget
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory)
            for key, consume in [('planning_budget',consume_planning_budget),('practice_budget',consume_practice_budget)]:
                catalog.set_setting(key,{'day':datetime.now().astimezone().date().isoformat(),'used':100})
                self.assertTrue(consume(catalog,0));self.assertEqual(catalog.setting(key)['used'],101)
            catalog.close()

    def test_real_parallel_reading_has_no_daily_cap_and_does_not_repeat_documented_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory)
            catalog.sync(snapshot([{**app(identity=str(i)), 'name':'App '+str(i)} for i in range(6)]))
            catalog.set_setting('research_budget', {'day':datetime.now().astimezone().date().isoformat(),'used':100})
            barrier=threading.Barrier(3);threads=set();lock=threading.Lock()
            def read(*args, **kwargs):
                with lock:threads.add(threading.get_ident())
                barrier.wait(3)
                return {'capabilities':[{'name':'Operate'}]}
            with patch('app_agent.learning.research_app',side_effect=read) as research:
                report=study_campaign(catalog,object(),lambda text:None,daily_limit=0,max_apps=6,max_plans=0,research_workers=3)
                repeated=study_campaign(catalog,object(),lambda text:None,daily_limit=0,max_apps=6,max_plans=0,research_workers=3)
            self.assertEqual(len(threads),3);self.assertNotIn(threading.get_ident(),threads)
            self.assertEqual(research.call_count,6);self.assertEqual(report['overview']['apps_documented'],6)
            self.assertEqual(catalog.setting('research_budget')['used'],106)
            self.assertEqual(repeated['status'],'documentation_wait');catalog.close()

    def test_finite_budget_is_atomic_across_concurrent_database_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            Catalog(directory).close()
            def reserve(_):
                catalog=Catalog(directory)
                try:return catalog.consume_budget('research_budget',2) is not None
                finally:catalog.close()
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(reserve,range(12)))
            self.assertEqual(sum(results),2)

    def test_research_lease_avoids_duplicate_requests_and_expired_lease_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([app()]))
            self.assertTrue(catalog.claim_research(app()['id'],1))
            with patch('app_agent.learning.research_app') as research:
                with self.assertRaises(ResearchBusy):ensure_blueprint(catalog,catalog.get(app()['id']),object(),lambda text:None)
            research.assert_not_called()
            with catalog.db:catalog.db.execute("UPDATE apps SET retry_at='2000-01-01T00:00:00+00:00'")
            self.assertEqual(catalog.next_research()['id'],app()['id']);catalog.close()

    def test_parallel_rate_failure_finishes_current_wave_then_backs_off_without_new_work(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([{**app(identity=str(i)),'name':str(i)} for i in range(8)]))
            with patch('app_agent.learning.research_app',side_effect=RuntimeError('HTTP 429')) as research:
                report=study_campaign(catalog,object(),lambda text:None,daily_limit=0,max_apps=8,max_plans=0,research_workers=3)
                retry=study_campaign(catalog,object(),lambda text:None,daily_limit=0,max_apps=8,max_plans=0,research_workers=3)
            self.assertEqual(report['status'],'cloud_blocked');self.assertEqual(research.call_count,3)
            self.assertEqual(retry['status'],'waiting_for_cloud_retry');catalog.close()

    def test_cancelled_parallel_results_are_not_saved_and_updated_app_discards_old_documents(self):
        for cancelled in (True,False):
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as directory:
                catalog=Catalog(directory);catalog.sync(snapshot([app()]));stop=threading.Event()
                def read(*args, **kwargs):
                    if cancelled:stop.set()
                    else:
                        concurrent=Catalog(directory)
                        try:concurrent.sync(snapshot([app(version='2')]))
                        finally:concurrent.close()
                    return {'capabilities':[]}
                with patch('app_agent.learning.research_app',side_effect=read):
                    study_campaign(catalog,object(),lambda text:None,daily_limit=0,max_apps=1,max_plans=0,cancel=stop)
                self.assertIsNone(catalog.get(app()['id'])['blueprint']);catalog.close()
