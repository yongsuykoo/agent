import json
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from email.message import Message
from pathlib import Path
from unittest.mock import Mock,patch
from app_agent.catalog import Catalog
from app_agent.campaign import study_campaign
from app_agent.document_fixtures import manual_pdf
from app_agent.manual_study import continue_manual
from app_agent.pdf_documents import progress_key
from app_agent.public_manuals import PublicCapture,manuals,read_pdf,refresh_next
from app_agent.research import CloudResearcher,fetch_document,research_app

URL='https://example.com/user-manual.pdf'


class OnlineCloud(CloudResearcher):
    def __init__(self):super().__init__(key='fixture-key');self.searches=0;self.extractions=0;self.callback=None
    def request(self,**payload):
        if 'tools' in payload:
            self.searches+=1
            return {'output':[{'content':[{'annotations':[{'type':'url_citation','url':URL}]}]}]}
        self.extractions+=1;document=json.loads(payload['input'])['documents'][0]
        if self.callback:self.callback()
        result={'capabilities':[],'limitations':[]}
        if 'Type Hello' in document['text']:
            result['capabilities']=[{'name':'Create text','steps':['Type Hello'],'expected_result':'Hello',
                'source_ids':[0],'source_pages':[{'source_id':0,'page':document['pages'][0]['page']}]}]
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}


@contextmanager
def transport(raw,final=URL,callback=None,content_type='application/pdf'):
    headers=Message();headers['Content-Type']=content_type
    response=Mock(headers=headers,url=final)
    def read(limit):
        if callback:callback()
        return raw[:limit]
    response.read.side_effect=read
    response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    with patch('app_agent.research.getproxies',return_value={'https':'http://fixture.proxy'}),patch('app_agent.research.proxy_bypass',return_value=False),patch('app_agent.research.build_opener') as builder:
        builder.return_value.open.return_value=response
        yield builder


class PublicManualTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.catalog=Catalog(self.root/'data')
        self.app={'id':'fixture:online-editor','name':'Owned Online Editor','version':'1','source':'fixture'}
        self.catalog.sync({'apps':[self.app]});self.current=self.catalog.get(self.app['id']);self.cloud=OnlineCloud()
    def tearDown(self):self.catalog.close();self.temp.cleanup()
    def capture(self,raw,callback=None):
        capture=PublicCapture(self.current)
        with transport(raw,callback=callback):fetch_document(URL,pdf_capture=capture)
        capture.register(self.catalog);return manuals(self.catalog,self.current)[0]
    def due(self):
        row=manuals(self.catalog,self.current)[0];row['refresh_at']=0
        with self.catalog.db:self.catalog.db.execute('UPDATE public_manuals SET body=?',(json.dumps(row),))
        return row

    def test_discovery_defers_parsing_and_operation_claims_then_reads_beyond_front_matter(self):
        raw=manual_pdf(['Copyright.']*32+['']*32+['Type Hello.']*6)
        with transport(raw),patch('app_agent.pdf_documents.extract_pdf',side_effect=AssertionError('Download must not parse')):
            first=study_campaign(self.catalog,self.cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
        self.assertEqual(first['research'][0]['status'],'manual_sources_discovered')
        self.assertEqual(self.cloud.extractions,0);self.assertIsNone(self.catalog.get(self.app['id'])['blueprint'])
        continue_manual(self.catalog,self.cloud,lambda _:None)
        self.catalog.close();self.catalog=Catalog(self.root/'data')
        count=self.cloud.extractions;continue_manual(self.catalog,self.cloud,lambda _:None)
        self.assertEqual(self.cloud.extractions,count)
        last=continue_manual(self.catalog,self.cloud,lambda _:None)
        self.assertTrue(last['blueprint_ready']);self.assertTrue(last['reading_complete'])
        blueprint=self.catalog.get(self.app['id'])['blueprint']
        self.assertEqual([s['read_cursor']['page'] for s in blueprint['sources']],[1,33,65])
        self.assertEqual(blueprint['capabilities'][0]['source_pages'][0]['page'],65)
        self.assertTrue(all(s['snapshot_reading'] for s in blueprint['sources']))

    def test_mixed_html_and_pdf_extraction_uses_only_readable_html_then_keeps_pdf_pending(self):
        capture=PublicCapture(self.current)
        def fetch(url):
            if url==URL:return capture(manual_pdf(),{'url':URL,'requested_url':URL,'retrieved_at':'fixture'})
            return {'url':url,'text':'Type Hello','sha256':'fixture'}
        cloud=Mock();cloud.extract.return_value={'capabilities':[{'name':'Create text'}],'limitations':[]}
        result=research_app('Editor','1',cloud,urls=[URL,'https://example.com/help'],fetcher=fetch,public_capture=capture)
        self.assertEqual(len(cloud.extract.call_args.args[2]),1)
        self.assertEqual(capture.register(self.catalog),1)
        self.catalog.save_blueprint(self.current['id'],1,result)
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'manual_complete')

    def test_snapshot_refresh_unchanged_keeps_cursor_and_changed_bytes_restart_reading(self):
        raw=manual_pdf(['Type Hello.']*40);manual=self.capture(raw)
        continue_manual(self.catalog,self.cloud,lambda _:None);oldkey=progress_key(self.current,manual)
        self.due()
        with transport(raw):self.assertEqual(refresh_next(self.catalog,lambda _:None)['status'],'public_manual_unchanged')
        self.assertEqual(self.catalog.setting(oldkey)['cursor'],{'page':33,'offset':0})
        self.due()
        with transport(manual_pdf(['New Type Hello.'])):self.assertEqual(refresh_next(self.catalog,lambda _:None)['status'],'public_manual_changed')
        replacement=manuals(self.catalog,self.current)[0]
        self.assertNotEqual(progress_key(self.current,replacement),oldkey)
        self.assertEqual(read_pdf(self.catalog,self.current,replacement)['read_cursor'],{'page':1,'offset':0})
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'manual_complete')

    def test_changed_snapshot_during_provider_request_rejects_old_findings(self):
        manual=self.capture(manual_pdf(['Type Hello.']*40));oldkey=progress_key(self.current,manual)
        self.cloud.callback=lambda:self.capture(manual_pdf(['Changed Type Hello.']))
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None)['status'],'manual_deferred')
        self.assertIsNone(self.catalog.get(self.app['id'])['blueprint'])
        self.assertNotIn('cursor',self.catalog.setting(oldkey))

    def test_cancelled_public_model_merge_preserves_registered_snapshot_and_checkpoint(self):
        manual=self.capture(manual_pdf(['Type Hello.']));stop=threading.Event();self.cloud.callback=stop.set
        self.assertEqual(continue_manual(self.catalog,self.cloud,lambda _:None,cancel=stop)['status'],'cancelled')
        self.assertIsNone(self.catalog.get(self.app['id'])['blueprint'])
        self.assertNotIn('cursor',self.catalog.setting(progress_key(self.current,manual)))
        self.assertEqual(len(manuals(self.catalog,self.current)),1)

    def test_app_update_during_discovery_cannot_register_old_bytes(self):
        from app_agent.learning import ensure_blueprint
        def update():
            connection=Catalog(self.root/'data')
            try:connection.sync({'apps':[{**self.app,'version':'2'}]})
            finally:connection.close()
        with transport(manual_pdf(),callback=update),self.assertRaisesRegex(RuntimeError,'App changed'):
            ensure_blueprint(self.catalog,self.current,self.cloud,lambda _:None)
        self.assertEqual(self.catalog.db.execute('SELECT COUNT(*) FROM public_manuals').fetchone()[0],0)

    def test_corrupted_snapshot_is_rejected_even_when_a_parsed_section_is_cached(self):
        manual=self.capture(manual_pdf(['Type Hello.']));read_pdf(self.catalog,self.current,manual)
        with self.catalog.db:self.catalog.db.execute('UPDATE public_manuals SET raw=?',(b'%PDF-corrupted',))
        with self.assertRaisesRegex(ValueError,'changed'):read_pdf(self.catalog,self.current,manual)

    def test_refresh_failure_retains_snapshot_and_backs_off_without_another_request(self):
        manual=self.capture(manual_pdf(['Type Hello.']));self.due()
        with patch('app_agent.research.fetch_document',side_effect=RuntimeError('Publisher unavailable')) as fetch:
            self.assertEqual(refresh_next(self.catalog,lambda _:None)['status'],'public_refresh_deferred')
            self.assertEqual(refresh_next(self.catalog,lambda _:None)['status'],'no_public_refresh')
        self.assertEqual(fetch.call_count,1);self.assertEqual(read_pdf(self.catalog,self.current,manual)['read_cursor'],{'page':1,'offset':0})

    def test_newer_capture_wins_and_expired_refresh_owner_cannot_replace_it(self):
        older=PublicCapture(self.current);newer=PublicCapture(self.current)
        with transport(manual_pdf(['Old Type Hello.'])):fetch_document(URL,pdf_capture=older)
        with transport(manual_pdf(['New Type Hello.'])):fetch_document(URL,pdf_capture=newer)
        newer.register(self.catalog);self.assertEqual(older.register(self.catalog),0)
        manual=manuals(self.catalog,self.current)[0]
        self.assertIn('New Type Hello',read_pdf(self.catalog,self.current,manual)['text'])
        self.assertEqual(older.register(self.catalog,refresh_owner='obsolete'),0)

    def test_refresh_duplicate_owner_and_cancellation_cannot_commit_download(self):
        self.capture(manual_pdf(['Type Hello.']));self.due();stop=threading.Event();nested=[]
        def during_read():
            second=Catalog(self.root/'data')
            try:nested.append(refresh_next(second,lambda _:None)['status'])
            finally:second.close()
            stop.set()
        with transport(manual_pdf(['Changed Type Hello.']),callback=during_read):
            self.assertEqual(refresh_next(self.catalog,lambda _:None,cancel=stop)['status'],'cancelled')
        self.assertEqual(nested,['no_public_refresh'])
        self.assertIn('Type Hello.',read_pdf(self.catalog,self.current,manuals(self.catalog,self.current)[0])['text'])
        self.assertNotIn('refresh_lease',manuals(self.catalog,self.current)[0])

    def test_invalid_public_destinations_and_oversized_pdf_cannot_enter_catalog(self):
        capture=PublicCapture(self.current)
        for url in ('http://example.com/manual.pdf','https://127.0.0.1/manual.pdf','https://user:secret@example.com/manual.pdf'):
            with self.assertRaises(ValueError):capture(manual_pdf(),{'url':url,'requested_url':URL,'retrieved_at':'fixture'})
        with transport(b'%PDF-'+b'A'*5_000_000),self.assertRaises(ValueError):fetch_document(URL,pdf_capture=capture)
        self.assertEqual(capture.register(self.catalog),0)

    def test_update_and_removal_prune_cached_raw_documents_but_keep_old_reading_evidence(self):
        manual=self.capture(manual_pdf(['Type Hello.']));continue_manual(self.catalog,self.cloud,lambda _:None)
        key=progress_key(self.current,manual)
        self.catalog.sync({'apps':[{**self.app,'version':'2'}]})
        self.assertEqual(self.catalog.db.execute('SELECT COUNT(*) FROM public_manuals').fetchone()[0],0)
        self.assertTrue(self.catalog.setting(key)['complete'])
        self.current=self.catalog.get(self.app['id']);self.capture(manual_pdf())
        self.catalog.sync({'apps':[],'complete_sources':['fixture']})
        self.assertEqual(self.catalog.db.execute('SELECT COUNT(*) FROM public_manuals').fetchone()[0],0)

    def test_unchanged_refresh_of_exhausted_non_operational_manual_does_not_strand_research(self):
        raw=manual_pdf(['Copyright only.']);self.capture(raw);continue_manual(self.catalog,self.cloud,lambda _:None)
        self.assertEqual(self.catalog.next_research()['id'],self.current['id'])
        self.due()
        with transport(raw):refresh_next(self.catalog,lambda _:None)
        self.assertEqual(self.catalog.next_research()['id'],self.current['id'])
        self.assertIsNone(self.catalog.get(self.current['id'])['blueprint'])

    def test_campaign_refresh_and_section_reading_both_progress_with_pending_manuals(self):
        raw=manual_pdf(['Type Hello.']*40);self.capture(raw);self.due()
        with transport(raw):report=study_campaign(self.catalog,self.cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
        self.assertEqual([result['status'] for result in report['research']],['public_manual_unchanged','manual_progress'])
        self.assertEqual(self.cloud.extractions,1)

    def test_model_failure_keeps_captured_pdf_for_later_section_study(self):
        def fetch(url,pdf_capture=None):
            if url==URL:
                return pdf_capture(manual_pdf(),{'url':URL,'requested_url':URL,'retrieved_at':'fixture'})
            return {'url':url,'text':'Document text','sha256':'fixture'}
        cloud=Mock();cloud.find_sources.return_value=[URL,'https://example.com/help'];cloud.extract.side_effect=RuntimeError('HTTP 429')
        with patch('app_agent.research.fetch_document',side_effect=fetch),patch('app_agent.research.getproxies',return_value={'https':'http://fixture.proxy'}),patch('app_agent.research.proxy_bypass',return_value=False):
            report=study_campaign(self.catalog,cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
        self.assertEqual(report['status'],'cloud_blocked')
        self.assertEqual(len(manuals(self.catalog,self.current)),1)
        self.assertIsNone(self.catalog.get(self.current['id'])['blueprint'])
        self.assertTrue(continue_manual(self.catalog,self.cloud,lambda _:None)['blueprint_ready'])

    def test_redirected_aliases_retain_each_acknowledged_snapshot_identity(self):
        raw=manual_pdf(['Type Hello.']);capture=PublicCapture(self.current)
        with transport(raw):
            fetch_document(URL,pdf_capture=capture)
            fetch_document('https://example.com/download-manual',pdf_capture=capture)
        self.assertEqual(capture.register(self.catalog),2)
        continue_manual(self.catalog,self.cloud,lambda _:None);continue_manual(self.catalog,self.cloud,lambda _:None)
        sources=self.catalog.get(self.current['id'])['blueprint']['sources']
        self.assertEqual(len(sources),2)
        self.assertEqual(len({source['manual_identity'] for source in sources}),2)
        self.assertEqual({source['url'] for source in sources},{URL})


if __name__=='__main__':unittest.main()
