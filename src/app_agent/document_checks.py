"""Provider-free acceptance of owned PDF manuals and the local study pipeline."""
import hashlib
import json
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
    def seed(name,pages,initial=True):
        from .learning import ensure_blueprint
        from .research import CloudResearcher
        folder=root/name;folder.mkdir();(folder/'manual.pdf').write_bytes(manual_pdf(pages))
        app={'id':'fixture:'+name,'name':'Owned '+name,'version':'1','source':'fixture','location':str(folder)}
        catalog=Catalog(root/(name+'-agent-data'));catalog.sync({'apps':[app],'local_evidence':{app['id']:inspect_installation(app,deadline_seconds=3)}})
        class FixtureCloud(CloudResearcher):
            def __init__(self):super().__init__(key='fixture-key');self.calls=0;self.callback=None
            def request(self,**payload):
                self.calls+=1;data=json.loads(payload['input'])
                if self.callback:self.callback()
                doc=data['documents'][0]
                result=operation(doc['pages'][0]['page']) if 'Type Hello' in doc['text'] else {'capabilities':[],'limitations':[]}
                return {'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}
        cloud=FixtureCloud()
        if initial:ensure_blueprint(catalog,catalog.get(app['id']),cloud,lambda _:None)
        return catalog,catalog.get(app['id']),cloud
    def continuation():
        from .manual_study import continue_manual
        catalog,app,cloud=seed('restart-continuation',['Type Hello.']*70)
        directory=catalog.data_dir;catalog.close();catalog=Catalog(directory)
        try:
            first=continue_manual(catalog,cloud,lambda _:None);last=continue_manual(catalog,cloud,lambda _:None)
            blueprint=catalog.get(app['id'])['blueprint'];pages=[page['page'] for page in blueprint['capabilities'][0]['source_pages']]
            calls=cloud.calls;repeated=continue_manual(catalog,cloud,lambda _:None)
            if first['status']!='manual_progress' or last['status']!='manual_complete' or pages!=[1,33,65] or cloud.calls!=calls or repeated['status']!='no_pending_manual':
                raise RuntimeError('Full manual continuation, provenance or restart recovery differs.')
            return {'reading_complete':True,'reviewed_chunks':3,'citation_pages':pages,'restart_resumed':True,'repeated_provider_calls':0,'simulated_provider_responses':True}
        finally:catalog.close()
    def long_page():
        expected='START '+('A'*50000)+' END';raw=manual_pdf([expected]);cursor=None;parts=[];ranges=[]
        while True:
            doc=extract_pdf(raw,cursor);parts.append(doc['text'].split('\n',1)[1]);ranges.append(doc['pages'][0]);cursor=doc['next_cursor']
            if cursor is None:break
        if ''.join(parts)!=expected or any(a['end_offset']!=b['offset'] for a,b in zip(ranges,ranges[1:])):
            raise RuntimeError('Long-page continuation lost or repeated text.')
        return {'characters_reconstructed':len(expected),'chunks':len(parts),'character_ranges_contiguous':True}
    def empty_section():
        from .manual_study import continue_manual
        from .pdf_documents import progress_key
        catalog,app,cloud=seed('empty-section',['Type Hello.']*32+['']*32+['Type Hello.'])
        try:
            before=cloud.calls;continue_manual(catalog,cloud,lambda _:None)
            if cloud.calls!=before:raise RuntimeError('Empty section consumed provider calls.')
            evidence=catalog.local_evidence(app['id'],app['generation']);state=catalog.setting(progress_key(app,evidence['manuals'][0]))
            if state['no_text_pages']!=list(range(33,65)):raise RuntimeError('Unextractable page gap was lost.')
            if continue_manual(catalog,cloud,lambda _:None)['status']!='manual_complete':raise RuntimeError('Reading failed to continue beyond empty pages.')
            return {'empty_section_provider_calls':0,'unextractable_pages_recorded':32,'later_text_reviewed':True}
        finally:catalog.close()
    def fences():
        from .manual_study import continue_manual,claim,release
        from .pdf_documents import progress_key
        from concurrent.futures import ThreadPoolExecutor
        catalog,app,cloud=seed('checkpoint-fences',['Type Hello.']*40)
        try:
            manual=catalog.local_evidence(app['id'],1)['manuals'][0];key=progress_key(app,manual);before=catalog.get(app['id'])['blueprint']
            stop=threading.Event();cloud.callback=stop.set
            if continue_manual(catalog,cloud,lambda _:None,cancel=stop)['status']!='cancelled' or catalog.get(app['id'])['blueprint']!=before or catalog.setting(key)['cursor']!={'page':33,'offset':0}:
                raise RuntimeError('Cancellation committed an unreviewed section.')
            cloud.callback=None;directory=catalog.data_dir
            def reserve(_):
                connection=Catalog(directory)
                try:return claim(connection,app,manual)
                finally:connection.close()
            with ThreadPoolExecutor(max_workers=4) as pool:tokens=list(pool.map(reserve,range(8)))
            winners=[token for token in tokens if token]
            if len(winners)!=1:raise RuntimeError('Multiple workers acquired one manual section.')
            release(catalog,key,winners[0])
            import app_agent,subprocess,sys
            script="import sys,os;sys.path.insert(0,sys.argv[1]);from app_agent.catalog import Catalog;from app_agent.manual_study import claim;c=Catalog(sys.argv[2]);a=c.get('fixture:checkpoint-fences');m=c.local_evidence(a['id'],a['generation'])['manuals'][0];assert claim(c,a,m);os._exit(0)"
            subprocess.run([sys.executable,'-I','-c',script,str(Path(app_agent.__file__).parent.parent),str(directory)],check=True,timeout=15)
            recovered=claim(catalog,app,manual)
            if recovered is None:raise RuntimeError('An exited worker blocked manual recovery until timeout.')
            release(catalog,key,recovered)
            def update():catalog.sync({'apps':[{**app,'version':'2'}]})
            cloud.callback=update
            if continue_manual(catalog,cloud,lambda _:None)['status']!='app_changed' or catalog.get(app['id'])['blueprint'] is not None:
                raise RuntimeError('Version update accepted stale manual findings.')
            return {'cancelled_checkpoint_unchanged':True,'concurrent_lease_winners':1,'dead_process_recovered':True,'updated_generation_rejected':True}
        finally:catalog.close()
    def bootstrap():
        from .manual_study import continue_manual,draft_key
        catalog,app,cloud=seed('new-app-front-matter',['Copyright and contents.']*32+['']*32+['Type Hello.']*6,initial=False)
        try:
            first=continue_manual(catalog,cloud,lambda _:None)
            if first['blueprint_ready'] or catalog.learning_overview()['apps_documented'] or catalog.next_research() is not None:
                raise RuntimeError('Front matter falsely established an app blueprint or duplicated initial study.')
            directory=catalog.data_dir;catalog.close();catalog=Catalog(directory)
            if len(catalog.setting(draft_key(app))['sources'])!=1:raise RuntimeError('Draft evidence failed to survive restart.')
            calls=cloud.calls;middle=continue_manual(catalog,cloud,lambda _:None)
            if middle['blueprint_ready'] or cloud.calls!=calls:raise RuntimeError('Blank opening section established operations or charged a provider call.')
            last=continue_manual(catalog,cloud,lambda _:None);blueprint=catalog.get(app['id'])['blueprint']
            if not last['blueprint_ready'] or not last['reading_complete'] or [s['read_cursor']['page'] for s in blueprint['sources']]!=[1,33,65] or blueprint['capabilities'][0]['source_pages'][0]['page']!=65 or catalog.coverage(app['id'],1)[0]['observed_runs']:
                raise RuntimeError('New-app study failed to find later instructions with retained provenance.')
            return {'new_app_studied_without_blueprint':True,'front_matter_draft_resumed':True,'blank_opening_provider_calls':0,
                'first_operation_cited_page':65,'reading_complete':True,'execution_verified':False,'simulated_provider_responses':True}
        finally:catalog.close()
    def no_operation():
        from .manual_study import continue_manual,draft_key
        catalog,app,cloud=seed('no-operating-instructions',['Copyright only.']*40,initial=False)
        try:
            continue_manual(catalog,cloud,lambda _:None);last=continue_manual(catalog,cloud,lambda _:None)
            if not last['reading_complete'] or last['blueprint_ready'] or catalog.get(app['id'])['blueprint'] is not None or catalog.next_research()['id']!=app['id'] or not catalog.setting(draft_key(app))['limitations']:
                raise RuntimeError('An exhausted non-operational manual claimed understanding or prevented alternative research.')
            calls=cloud.calls
            if continue_manual(catalog,cloud,lambda _:None)['status']!='no_pending_manual' or cloud.calls!=calls:
                raise RuntimeError('Exhausted manual was read repeatedly.')
            return {'exhausted_manual_without_false_blueprint':True,'alternative_research_queued':True,'draft_gaps_retained':True,'repeated_provider_calls':0}
        finally:catalog.close()
    checks=[('Compressed PDF pages and hashes',compressed),('Unicode PDF font mappings',unicode_text),
        ('Partial reading retains coverage gaps',coverage),('Malformed and scanned-only manuals do not establish evidence',lambda:(rejected(b'%PDF-1.4\nbroken'),rejected(manual_pdf([''])))),
        ('Encrypted manuals require no passwords and are rejected',lambda:rejected(manual_pdf(encrypted=True))),
        ('Compressed oversized page is rejected',lambda:rejected(manual_pdf(['A'*8_100_000]))),
        ('Installed PDF study, caching and update adaptation',local_study),('Uninspected PDF pages cannot be cited',citations),
        ('Full installed manual resumes after restart',continuation),('Long PDF page retains every character range',long_page),
        ('Empty sections retain gaps and continue without model calls',empty_section),('Cancelled concurrent and updated manual checkpoints are fenced',fences),
        ('New app studies beyond front matter before its first blueprint',bootstrap),('Exhausted manual queues alternative research without inventing operations',no_operation)]
    emit('Document tests use owned PDF fixtures only; no provider key, network or desktop interaction.')
    return run_checks(checks,root/'report.json',cancel,emit,
        scope='Bounded owned PDF/manual learning checks. Documented operations remain execution-unverified; no all-app certification.')
