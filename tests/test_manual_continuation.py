import json
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from app_agent.catalog import Catalog
from app_agent.campaign import study_campaign
from app_agent.document_fixtures import manual_pdf
from app_agent.learning import ensure_blueprint,merge_blueprints
from app_agent.local_inspection import inspect_installation
from app_agent.machine import machine_report,research_context
from app_agent.manual_study import claim,continue_manual,release
from app_agent.pdf_documents import extract_pdf,progress_key
from app_agent.research import CloudResearcher,validate_extraction


class SectionCloud(CloudResearcher):
    def __init__(self,callback=None,empty=False):
        super().__init__(key='fixture-key');self.calls=[];self.callback=callback;self.empty=empty
    def request(self,**payload):
        evidence=json.loads(payload['input']);self.calls.append(evidence)
        if self.callback:self.callback()
        page=evidence['documents'][0]['pages'][0]['page']
        result={'capabilities':[],'limitations':[]}
        if not self.empty:
            result['capabilities']=[{'name':'Create text','steps':['Type Hello'], 'expected_result':'Hello',
                'source_ids':[0],'source_pages':[{'source_id':0,'page':page}]}]
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}


class ManualContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        self.install=self.root/'install';self.install.mkdir();self.path=self.install/'manual.pdf'
        self.path.write_bytes(manual_pdf(['Type Hello.']*70))
        self.app={'id':'fixture:editor','name':'Owned Editor','version':'1','source':'fixture','location':str(self.install)}
        self.catalog=Catalog(self.root/'data');self.sync();self.cloud=SectionCloud()
    def sync(self,version='1'):
        evidence=inspect_installation(self.app,deadline_seconds=3)
        self.catalog.sync({'apps':[{**self.app,'version':version}],'local_evidence':{self.app['id']:evidence}})
        self.current=self.catalog.get(self.app['id']);self.manual=evidence['manuals'][0]
    def study(self):
        ensure_blueprint(self.catalog,self.current,self.cloud,lambda _:None)
        self.current=self.catalog.get(self.app['id'])
        return self.catalog.setting(progress_key(self.current,self.manual))
    def tearDown(self):self.catalog.close();self.temporary.cleanup()

    def test_full_manual_continues_after_restart_and_preserves_every_cited_chunk(self):
        self.assertEqual(self.study()['cursor'],{'page':33,'offset':0})
        self.catalog.close();self.catalog=Catalog(self.root/'data')
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'manual_progress')
        result=continue_manual(self.catalog,self.cloud,lambda _:None)
        self.assertEqual(result['status'],'manual_complete');self.assertEqual(result['reviewed_chunks'],3)
        calls=len(self.cloud.calls)
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'no_pending_manual')
        self.assertEqual(len(self.cloud.calls),calls)
        blueprint=self.catalog.get(self.app['id'])['blueprint']
        self.assertEqual([source['read_cursor']['page'] for source in blueprint['sources']],[1,33,65])
        self.assertEqual([p['page'] for p in blueprint['capabilities'][0]['source_pages']],[1,33,65])
        self.assertEqual(blueprint['capabilities'][0]['status'],'documented_unverified')
        progress=machine_report(self.catalog)['apps'][0]['pdf_manual_progress'][0]
        self.assertTrue(progress['reading_complete']);self.assertEqual(progress['reviewed_chunks'],3)

    def test_long_single_page_resumes_at_character_offset_without_losing_text(self):
        expected='START '+('A'*50000)+' END';raw=manual_pdf([expected]);cursor=None;parts=[];ranges=[]
        while True:
            doc=extract_pdf(raw,cursor);parts.append(doc['text'].split('\n',1)[1]);ranges.append(doc['pages'][0])
            cursor=doc['next_cursor']
            if cursor is None:break
        self.assertEqual(''.join(parts),expected)
        self.assertEqual([p['offset'] for p in ranges],[0,ranges[0]['end_offset'],ranges[1]['end_offset']])
        self.assertEqual(ranges[-1]['end_offset'],len(expected))
        doc['url']='fixture:manual';response={'capabilities':[{'name':'Read','steps':['Read text'],'expected_result':'END',
            'source_ids':[0],'source_pages':[{'source_id':0,'page':1}]}],'limitations':[]}
        citation=validate_extraction(response,[doc])['capabilities'][0]['source_pages'][0]
        self.assertEqual(citation['offset'],ranges[-1]['offset'])

    def test_sections_with_no_new_operation_advance_without_inventing_capabilities(self):
        self.study();cloud=SectionCloud(empty=True)
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None)['status'],'manual_progress')
        current=self.catalog.get(self.app['id'])['blueprint']
        self.assertEqual([cap['name'] for cap in current['capabilities']],['Create text'])
        self.assertEqual(len(current['sources']),2)

    def test_empty_scanned_section_advances_with_gap_and_without_provider_usage(self):
        self.path.write_bytes(manual_pdf(['Type Hello.']*32+['']*32+['Type Hello.']))
        self.sync();self.study();calls=len(self.cloud.calls)
        result=continue_manual(self.catalog,self.cloud,lambda _:None)
        self.assertEqual(result['status'],'manual_progress');self.assertEqual(len(self.cloud.calls),calls)
        state=self.catalog.setting(progress_key(self.current,self.manual))
        self.assertEqual(state['no_text_pages'],list(range(33,65)))
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'manual_complete')

    def test_cancellation_keeps_exact_checkpoint_and_same_next_evidence(self):
        self.study();stop=threading.Event();cloud=SectionCloud(callback=stop.set)
        before=self.catalog.get(self.app['id'])['blueprint']
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None,cancel=stop)['status'],'cancelled')
        self.assertEqual(self.catalog.get(self.app['id'])['blueprint'],before)
        self.assertEqual(self.catalog.setting(progress_key(self.current,self.manual))['cursor'],{'page':33,'offset':0})
        cloud.callback=None;stop.clear();continue_manual(self.catalog,cloud,lambda _:None,cancel=stop)
        self.assertEqual(cloud.calls[0]['documents'],cloud.calls[1]['documents'])

    def test_cancellation_inside_commit_rolls_back_blueprint_and_cursor_together(self):
        self.study();before=self.catalog.get(self.app['id'])['blueprint'];stop=threading.Event()
        original=merge_blueprints
        def merge(*args):
            result=original(*args);stop.set();return result
        with patch('app_agent.manual_study.merge_blueprints',side_effect=merge):
            result=continue_manual(self.catalog,self.cloud,lambda _:None,cancel=stop)
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(self.catalog.get(self.app['id'])['blueprint'],before)
        self.assertEqual(self.catalog.setting(progress_key(self.current,self.manual))['cursor'],{'page':33,'offset':0})

    def test_provider_failure_backs_off_without_advancing_or_repeating(self):
        self.study();cloud=SectionCloud(callback=lambda:(_ for _ in ()).throw(RuntimeError('HTTP 429')))
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None)['status'],'cloud_blocked')
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None)['status'],'no_pending_manual')
        state=self.catalog.setting(progress_key(self.current,self.manual))
        self.assertEqual(state['cursor'],{'page':33,'offset':0});self.assertGreater(state['retry_at'],time.time())
        self.assertEqual(len(cloud.calls),1)

    def test_version_update_during_model_call_rejects_old_generation(self):
        self.study();old=self.current.copy()
        cloud=SectionCloud(callback=lambda:self.sync(version='2'))
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None)['status'],'app_changed')
        self.assertIsNone(self.catalog.get(self.app['id'])['blueprint'])
        self.assertEqual(self.catalog.setting(progress_key(old,self.manual))['cursor'],{'page':33,'offset':0})

    def test_manual_bytes_changed_during_model_call_are_rejected_before_commit(self):
        self.study();before=self.catalog.get(self.app['id'])['blueprint']
        cloud=SectionCloud(callback=lambda:self.path.write_bytes(manual_pdf(['Changed.']*70)))
        self.assertEqual(continue_manual(self.catalog,cloud,lambda _:None)['status'],'manual_deferred')
        self.assertEqual(self.catalog.get(self.app['id'])['blueprint'],before)
        self.assertEqual(self.catalog.setting(progress_key(self.current,self.manual))['cursor'],{'page':33,'offset':0})

    def test_atomic_leases_across_database_connections_and_dead_owner_recovery(self):
        self.study();directory=self.root/'data';app=self.current;manual=self.manual
        def reserve(_):
            catalog=Catalog(directory)
            try:return claim(catalog,app,manual)
            finally:catalog.close()
        with ThreadPoolExecutor(max_workers=4) as pool:tokens=list(pool.map(reserve,range(8)))
        self.assertEqual(sum(token is not None for token in tokens),1)
        with patch('app_agent.manual_study.process_alive',return_value=False):token=claim(self.catalog,app,manual)
        self.assertIsNotNone(token);release(self.catalog,progress_key(app,manual),token)

    def test_actual_process_exit_releases_manual_ownership_without_waiting_for_timeout(self):
        self.study();import app_agent
        script="import sys,os;sys.path.insert(0,sys.argv[1]);from app_agent.catalog import Catalog;from app_agent.manual_study import claim;c=Catalog(sys.argv[2]);a=c.get('fixture:editor');m=c.local_evidence(a['id'],a['generation'])['manuals'][0];assert claim(c,a,m);os._exit(0)"
        subprocess.run([sys.executable,'-I','-c',script,str(Path(app_agent.__file__).parent.parent),str(self.catalog.data_dir)],check=True,timeout=15)
        token=claim(self.catalog,self.current,self.manual)
        self.assertIsNotNone(token);release(self.catalog,progress_key(self.current,self.manual),token)

    def test_saved_blueprint_cannot_skip_unreviewed_or_forged_pdf_range(self):
        self.study();before=self.catalog.setting(progress_key(self.current,self.manual))
        _,docs=research_context(self.catalog,self.current);source={k:v for k,v in docs[0].items() if k!='text'}
        source['text_sha256']='0'*64
        self.catalog.save_blueprint(self.current['id'],1,{'capabilities':[{'name':'Create text'}],'sources':[source]})
        self.assertEqual(self.catalog.setting(progress_key(self.current,self.manual)),before)

    def test_background_campaign_resumes_manual_before_initial_queue_is_empty(self):
        self.study();other={'id':'fixture:other','name':'Other App','version':'1','source':'fixture'}
        self.catalog.sync({'apps':[self.app,other]})
        report=study_campaign(self.catalog,self.cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
        self.assertEqual(report['research'][0]['status'],'manual_progress')
        self.assertEqual(self.catalog.get(other['id'])['status'],'queued')

    def test_budget_limit_preserves_cached_unreviewed_section(self):
        self.study();from datetime import datetime
        self.catalog.set_setting('research_budget',{'day':datetime.now().astimezone().date().isoformat(),'used':1})
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None,daily_limit=1)['status'],'daily_limit')
        self.assertEqual(self.catalog.setting(progress_key(self.current,self.manual))['cursor'],{'page':33,'offset':0})

    def test_invalid_cursor_is_rejected_before_parser_launch(self):
        with patch('app_agent.pdf_documents.subprocess.run') as launch:
            for cursor in ({},{'page':0,'offset':0},{'page':1,'offset':-1},{'page':True,'offset':0}):
                with self.assertRaises(ValueError):extract_pdf(manual_pdf(),cursor)
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
