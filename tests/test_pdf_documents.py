import hashlib
import json
from email.message import Message
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock,patch
from app_agent.catalog import Catalog
from app_agent.document_checks import operation
from app_agent.document_fixtures import manual_pdf
from app_agent.local_inspection import inspect_installation
from app_agent.machine import research_context
from app_agent.pdf_documents import extract_pdf,installed_pdf,MAX_PDF_BYTES
from app_agent.research import CloudResearcher,fetch_document,validate_extraction


class PdfDocumentsTests(unittest.TestCase):
    def test_compressed_pages_have_exact_text_and_page_hashes(self):
        doc=extract_pdf(manual_pdf(['Type Hello.','Press plus.']))
        self.assertEqual(doc['text'],'[PDF page 1]\nType Hello.\n\n[PDF page 2]\nPress plus.')
        self.assertEqual(doc['pages'][1]['sha256'],hashlib.sha256(b'Press plus.').hexdigest())
        self.assertEqual((doc['page_count'],doc['pages_read'],doc['truncated']),(2,2,False))
        self.assertEqual(doc['process_limits'],{'memory_bytes':256*1024*1024,'cpu_seconds':6})

    def test_unicode_font_mapping_is_decoded(self):
        self.assertIn('你好 café — 世界',extract_pdf(manual_pdf(['你好 café — 世界'],unicode=True))['text'])

    def test_reading_large_manual_records_uninspected_pages(self):
        doc=extract_pdf(manual_pdf(['Type Hello.']*40));doc['url']='fixture:manual'
        self.assertEqual((doc['pages_read'],doc['page_count'],doc['truncated']),(32,40,True))
        self.assertTrue(any('32 of 40' in x for x in validate_extraction(operation(),[doc])['limitations']))
        with self.assertRaisesRegex(ValueError,'unread'):
            validate_extraction(operation(33),[doc])

    def test_long_page_text_is_explicitly_truncated(self):
        doc=extract_pdf(manual_pdf(['Type Hello. '*3000],compressed=False))
        self.assertLessEqual(len(doc['text']),24000)
        self.assertTrue(doc['truncated']);self.assertTrue(doc['pages'][0]['truncated'])

    def test_malformed_encrypted_scanned_and_decompression_bomb_fail_without_evidence(self):
        for raw in (b'%PDF-1.4\nbroken',manual_pdf(encrypted=True),manual_pdf(['']),manual_pdf(['X'*8_100_000])):
            with self.subTest(size=len(raw)),self.assertRaises((ValueError,RuntimeError)):extract_pdf(raw)

    def test_oversized_or_non_pdf_never_launches_parser(self):
        with patch('app_agent.pdf_documents.subprocess.run') as run:
            for raw in (b'plain text',b'%PDF-'+b'a'*MAX_PDF_BYTES):
                with self.assertRaises(ValueError):extract_pdf(raw)
            run.assert_not_called()

    def test_parser_times_out_and_excludes_keys_from_child_environment(self):
        with patch.dict('os.environ',{'AGENT_API_KEY':'private-provider','OPENAI_API_KEY':'private-openai','CONTROLLER_SECRET':'private-controller'}),patch('app_agent.pdf_documents.subprocess.run',side_effect=subprocess.TimeoutExpired('reader',8)) as run:
            with self.assertRaisesRegex(RuntimeError,'terminated'):extract_pdf(manual_pdf())
        call=run.call_args
        self.assertEqual(call.args[0][1:3],['-I','-c'])
        self.assertEqual(call.kwargs['timeout'],8)
        self.assertNotIn('private-',json.dumps(call.kwargs['env']))

    def test_parser_invalid_output_cannot_become_evidence(self):
        with patch('app_agent.pdf_documents.subprocess.run',return_value=Mock(returncode=0,stdout=b'{"result":{"text":"fake"}}')):
            with self.assertRaisesRegex(RuntimeError,'invalid evidence'):extract_pdf(manual_pdf())

    def test_nested_worker_archive_can_load_pinned_parser_resource(self):
        import app_agent
        package=Path(app_agent.__file__).parent
        with tempfile.TemporaryDirectory() as folder:
            wheel=Path(folder)/'app_agent_fixture.whl'
            with zipfile.ZipFile(wheel,'w',zipfile.ZIP_DEFLATED) as archive:
                for name in ('__init__.py','pdf_documents.py','_pdf_worker.py','vendor/pypdf.whl'):
                    archive.write(package/name,'app_agent/'+name)
            script="import sys,json;sys.path.insert(0,sys.argv[1]);import app_agent;assert app_agent.__file__.startswith(sys.argv[1]);from app_agent.pdf_documents import extract_pdf;print(json.dumps(extract_pdf(sys.stdin.buffer.read())))"
            result=subprocess.run([sys.executable,'-I','-c',script,str(wheel)],input=manual_pdf(),capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            self.assertEqual(json.loads(result.stdout)['pages_read'],2)

    def test_modified_parser_is_rejected_before_launch(self):
        with patch('app_agent.pdf_documents.PARSER_SHA256','0'*64),patch('app_agent.pdf_documents.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):extract_pdf(manual_pdf())
            run.assert_not_called()

    def test_public_pdf_retrieval_keeps_byte_hash_and_final_url(self):
        raw=manual_pdf();headers=Message();headers['Content-Type']='application/pdf'
        response=Mock(headers=headers,url='https://example.com/manual.pdf');response.read.return_value=raw
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('app_agent.research.public_https'),patch('app_agent.research.build_opener') as opener:
            opener.return_value.open.return_value=response;doc=fetch_document('https://example.com/start')
        self.assertEqual(doc['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(doc['requested_url'],'https://example.com/start')
        self.assertEqual(doc['format'],'pdf');response.read.assert_called_once_with(MAX_PDF_BYTES+1)

    def test_pdf_citation_requires_inspected_nonempty_page_and_cited_source(self):
        doc=extract_pdf(manual_pdf(['Type Hello.','']));doc['url']='fixture:manual'
        for references in ([],[{'source_id':0,'page':2}],[{'source_id':0,'page':99}],[{'source_id':1,'page':1}],[{'source_id':0,'page':True}]):
            value=operation();value['capabilities'][0]['source_pages']=references
            with self.subTest(references=references),self.assertRaises(ValueError):validate_extraction(value,[doc])
        valid=validate_extraction(operation(),[doc])['capabilities'][0]
        self.assertEqual(valid['status'],'documented_unverified')
        self.assertEqual(valid['source_pages'][0]['page_sha256'],doc['pages'][0]['sha256'])

    def test_page_citation_repair_preserves_exact_pdf_evidence(self):
        doc=extract_pdf(manual_pdf());doc['url']='fixture:manual'
        invalid=operation(99)
        def response(value):return {'output':[{'content':[{'type':'output_text','text':json.dumps(value)}]}]}
        cloud=CloudResearcher(key='fixture-key')
        with patch.object(cloud,'request',side_effect=[response(invalid),response(operation())]) as request:
            result=cloud.extract('Editor','1',[doc])
        first,second=[json.loads(call.kwargs['input']) for call in request.call_args_list]
        self.assertEqual(first['documents'],second['documents'])
        self.assertIn('unread',second['validation_feedback'])
        self.assertEqual(result['capabilities'][0]['source_pages'][0]['page'],1)

    def test_installed_pdf_deferred_cache_survives_restart_and_rejects_stale_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);install=root/'install';install.mkdir();path=install/'manual.pdf';path.write_bytes(manual_pdf())
            app={'id':'fixture:editor','name':'Editor','source':'fixture','version':'1','location':str(install)}
            with patch('app_agent.pdf_documents.extract_pdf',side_effect=AssertionError('Inventory must not parse PDF')):
                evidence=inspect_installation(app,deadline_seconds=3)
            self.assertNotIn('text',evidence['manuals'][0])
            catalog=Catalog(root/'data')
            try:
                catalog.sync({'apps':[app],'local_evidence':{app['id']:evidence}});current=catalog.get(app['id'])
                _,documents=research_context(catalog,current);catalog.close();catalog=Catalog(root/'data')
                with patch('app_agent.pdf_documents.extract_pdf',side_effect=AssertionError('Cache must not reparse')):
                    _,cached=research_context(catalog,current)
                self.assertEqual(documents,cached)
                path.write_bytes(manual_pdf(['Changed.']))
                context,documents=research_context(catalog,current)
                self.assertEqual(documents,[]);self.assertIn('rescan',context['installation']['manual_gaps'][0])
            finally:catalog.close()

    def test_undiscovered_or_outside_manual_rejected_before_read(self):
        catalog=Mock();app={'id':'editor','generation':1}
        for manual in ({'path':'../manual.pdf','root':'/other'},{'path':'manual.pdf','root':'/other'}):
            with self.assertRaisesRegex(ValueError,'discovered'):
                installed_pdf(catalog,app,{'roots':[],'files':[]},manual)


if __name__=='__main__':unittest.main()
