"""Provider-free acceptance of owned PDF manuals and the local study pipeline."""
import hashlib
from pathlib import Path
import threading
import uuid
from .catalog import Catalog
from .document_fixtures import manual_pdf
from .local_inspection import inspect_installation
from .machine import research_context
from .pdf_documents import extract_pdf
from .research import validate_extraction
from .self_test import run_checks


def operation(page=1):
    return {'capabilities':[{'name':'Create text','steps':['Type Hello into a blank document'],
        'expected_result':'Hello is displayed','source_ids':[0],'source_pages':[{'source_id':0,'page':page}]}], 'limitations':[]}


def rejected(raw):
    try:extract_pdf(raw)
    except (ValueError,RuntimeError):return {'unreadable_manual_rejected':True}
    raise RuntimeError('Unusable PDF was accepted as readable evidence.')


def document_smoke(directory,emit=print,cancel=None):
    cancel=cancel or threading.Event()
    root=Path(directory).absolute()/('document-tests-'+uuid.uuid4().hex);root.mkdir(parents=True,exist_ok=False)
    def compressed():
        document=extract_pdf(manual_pdf())
        if 'Type Hello' not in document['text'] or document['page_count']!=2 or document['truncated']:
            raise RuntimeError('Compressed multi-page PDF text or coverage differs.')
        if document['pages'][0]['sha256']!=hashlib.sha256('Create a blank document. Type Hello. Verify Hello.'.encode()).hexdigest():
            raise RuntimeError('PDF page evidence hash differs.')
        return {'pages_read':2,'page_hashes_verified':True,'reader_revision':document['reader_revision'],'process_limits':document['process_limits']}
    def unicode_text():
        expected='Type 你好 世界 — café into the editor.'
        if expected not in extract_pdf(manual_pdf([expected],unicode=True))['text']:
            raise RuntimeError('Unicode font mapping was not decoded exactly.')
        return {'unicode_font_mapping_verified':True}
    def coverage():
        doc=extract_pdf(manual_pdf(['Create a blank document.']*40));doc['url']='fixture:manual'
        result=validate_extraction(operation(),[doc])
        if doc['pages_read']!=32 or not doc['truncated'] or not any('32 of 40' in gap for gap in result['limitations']):
            raise RuntimeError('Partial PDF reading failed to retain its coverage gap.')
        return {'total_pages':40,'inspected_pages':32,'coverage_gap_retained':True}
    def local_study():
        folder=root/'owned-installation';folder.mkdir();path=folder/'manual.pdf';path.write_bytes(manual_pdf())
        app={'id':'fixture:editor','name':'Owned Editor','version':'1','source':'fixture','location':str(folder)}
        catalog=Catalog(root/'agent-data')
        try:
            evidence=inspect_installation(app,deadline_seconds=3)
            if any('text' in manual for manual in evidence['manuals']):raise RuntimeError('PDF was parsed during inventory instead of deferred study.')
            catalog.sync({'apps':[app],'local_evidence':{app['id']:evidence}});current=catalog.get(app['id'])
            context,documents=research_context(catalog,current)
            blueprint=validate_extraction(operation(),documents)
            catalog.save_blueprint(current['id'],current['generation'],blueprint)
            if catalog.coverage(current['id'],1)[0]['status']!='documented_unverified':raise RuntimeError('Reading incorrectly claimed execution verification.')
            _,cached=research_context(catalog,current)
            if documents!=cached:raise RuntimeError('Unchanged PDF page evidence was not reused.')
            path.write_bytes(manual_pdf(['Changed manual: use a different editor.']))
            gap,stale=research_context(catalog,current)
            if stale or not gap['installation'].get('manual_gaps'):raise RuntimeError('Changed installation bytes reused old PDF text.')
            catalog.sync({'apps':[{**app,'version':'2'}],'local_evidence':{app['id']:inspect_installation(app,deadline_seconds=3)}})
            current=catalog.get(app['id']);_,fresh=research_context(catalog,current)
            if current['generation']!=2 or current['blueprint'] is not None or 'Changed manual' not in fresh[0]['text']:
                raise RuntimeError('Updated app failed to invalidate old learned evidence.')
            return {'discovery_deferred':True,'local_page_evidence':True,'unchanged_cache_reused':True,
                'stale_bytes_rejected':True,'update_relearned':True,'reading_status':'documented_unverified','provider_calls':0}
        finally:catalog.close()
    def citations():
        doc=extract_pdf(manual_pdf());doc['url']='fixture:manual'
        valid=validate_extraction(operation(),[doc])
        if valid['capabilities'][0]['source_pages'][0]['page_sha256']!=doc['pages'][0]['sha256']:
            raise RuntimeError('Saved PDF citation differs from inspected page bytes.')
        try:validate_extraction(operation(page=99),[doc])
        except ValueError:return {'unread_page_rejected':True,'page_hash_citation_verified':True}
        raise RuntimeError('Uninspected PDF page accepted as evidence.')
    checks=[('Compressed PDF pages and hashes',compressed),('Unicode PDF font mappings',unicode_text),
        ('Partial reading retains coverage gaps',coverage),('Malformed and scanned-only manuals do not establish evidence',lambda:(rejected(b'%PDF-1.4\nbroken'),rejected(manual_pdf([''])))),
        ('Encrypted manuals require no passwords and are rejected',lambda:rejected(manual_pdf(encrypted=True))),
        ('Compressed oversized page is rejected',lambda:rejected(manual_pdf(['A'*8_100_000]))),
        ('Installed PDF study, caching and update adaptation',local_study),('Uninspected PDF pages cannot be cited',citations)]
    emit('Document tests use owned PDF fixtures only; no provider key, network or desktop interaction.')
    return run_checks(checks,root/'report.json',cancel,emit,
        scope='Bounded owned PDF/manual learning checks. Documented operations remain execution-unverified; no all-app certification.')
