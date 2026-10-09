"""Owned HTTP-stream fixtures for online PDF acquisition and durable study."""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import build_opener,ProxyHandler,Request
from .catalog import Catalog
from .campaign import study_campaign
from .document_fixtures import manual_pdf
from .manual_study import continue_manual
from .pdf_documents import progress_key
from .public_manuals import manuals,refresh_next
from .research import CloudResearcher

URL='https://publisher.fixture.example/user-manual.pdf'


@contextmanager
def publisher(raw):
    state={'raw':raw,'requests':0,'credential_header_seen':False}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests']+=1
            state['credential_header_seen'] |= self.headers.get('Authorization') is not None
            body=state['raw'];self.send_response(200);self.send_header('Content-Type','application/pdf')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    wire=build_opener(ProxyHandler({}))
    class Response:
        url=URL
        def __init__(self,response):self.response=response;self.headers=response.headers
        def read(self,size):return self.response.read(size)
        def __enter__(self):return self
        def __exit__(self,*args):self.response.close()
    class Adapter:
        def open(self,request,timeout):
            if request.full_url!=URL:raise ValueError('Fixture transport permits its owned manual only.')
            return Response(wire.open(Request(f'http://127.0.0.1:{server.server_port}/manual.pdf',headers=dict(request.header_items())),timeout=timeout))
    try:
        # Only fixture transport is substituted; product HTTPS and destination
        # checks still execute. This is not public TLS/network certification.
        with patch('app_agent.research.getproxies',return_value={'https':'http://fixture.proxy'}),patch('app_agent.research.proxy_bypass',return_value=False),patch('app_agent.research.build_opener',return_value=Adapter()):
            yield state
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


class FixtureCloud(CloudResearcher):
    def __init__(self):super().__init__(key='fixture-key');self.extractions=0;self.callback=None
    def request(self,**payload):
        if 'tools' in payload:return {'output':[{'content':[{'annotations':[{'type':'url_citation','url':URL}]}]}]}
        self.extractions+=1;doc=json.loads(payload['input'])['documents'][0]
        if self.callback:self.callback()
        result={'capabilities':[],'limitations':[]}
        if 'Type Hello' in doc['text']:
            result['capabilities']=[{'name':'Create text','steps':['Type Hello'],'expected_result':'Hello',
                'source_ids':[0],'source_pages':[{'source_id':0,'page':doc['pages'][0]['page']}]}]
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}


def checks(root):
    def seed(name):
        catalog=Catalog(root/name);app={'id':'fixture:'+name,'name':'Owned '+name,'version':'1','source':'fixture'}
        catalog.sync({'apps':[app]});return catalog,catalog.get(app['id']),FixtureCloud()
    def online_restart():
        catalog,app,cloud=seed('online-pdf-restart')
        try:
            with publisher(manual_pdf(['Copyright.']*32+['']*32+['Type Hello.']*6)) as network:
                discovery=study_campaign(catalog,cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
                if discovery['research'][0]['status']!='manual_sources_discovered' or cloud.extractions or catalog.get(app['id'])['blueprint'] is not None:
                    raise RuntimeError('Online PDF discovery claimed an operation before section study.')
                continue_manual(catalog,cloud,lambda _:None)
                directory=catalog.data_dir;catalog.close();catalog=Catalog(directory)
                calls=cloud.extractions;continue_manual(catalog,cloud,lambda _:None)
                if cloud.extractions!=calls:raise RuntimeError('Blank public PDF section consumed a provider request.')
                last=continue_manual(catalog,cloud,lambda _:None);blueprint=catalog.get(app['id'])['blueprint']
                if not last['reading_complete'] or [s['read_cursor']['page'] for s in blueprint['sources']]!=[1,33,65] or blueprint['capabilities'][0]['source_pages'][0]['page']!=65 or network['requests']!=1 or network['credential_header_seen']:
                    raise RuntimeError('Online manual restart, source provenance, network reuse or credential exclusion differs.')
                return {'online_pdf_restart_resumed':True,'owned_http_streams':network['requests'],'public_blank_section_provider_calls':0,
                    'online_first_operation_cited_page':65,'snapshot_reading_complete':True,'credential_header_seen':False,
                    'simulated_public_https_transport':True,'simulated_provider_responses':True}
        finally:catalog.close()
    def online_refresh():
        catalog,app,cloud=seed('online-pdf-refresh');raw=manual_pdf(['Type Hello.']*40)
        try:
            with publisher(raw) as network:
                study_campaign(catalog,cloud,lambda _:None,daily_limit=0,max_apps=1,max_plans=0)
                original=manuals(catalog,app)[0];key=progress_key(app,original)
                continue_manual(catalog,cloud,lambda _:None)
                def due():
                    body=manuals(catalog,app)[0];body['refresh_at']=0
                    with catalog.db:catalog.db.execute('UPDATE public_manuals SET body=?',(json.dumps(body),))
                due()
                if refresh_next(catalog,lambda _:None)['status']!='public_manual_unchanged' or catalog.setting(key)['cursor']!={'page':33,'offset':0}:
                    raise RuntimeError('Unchanged public source reset reading progress.')
                due();network['raw']=manual_pdf(['Changed Type Hello.'])
                if refresh_next(catalog,lambda _:None)['status']!='public_manual_changed':raise RuntimeError('Changed publisher bytes were not detected.')
                replacement=manuals(catalog,app)[0]
                if progress_key(app,replacement)==key or continue_manual(catalog,cloud,lambda _:None)['status']!='manual_complete':
                    raise RuntimeError('Changed public source failed to restart reading.')
                before=catalog.get(app['id'])['blueprint'];due();network['raw']=manual_pdf(['Another Type Hello.'])
                stop=threading.Event();stop.set()
                if refresh_next(catalog,lambda _:None,cancel=stop)['status']!='cancelled' or catalog.get(app['id'])['blueprint']!=before:
                    raise RuntimeError('Cancelled refresh changed documented evidence.')
                if network['requests']!=3 or network['credential_header_seen']:raise RuntimeError('Refresh stream count or credential exclusion differs.')
                return {'public_refresh_unchanged_cursor_retained':True,'public_changed_snapshot_relearned':True,
                    'public_refresh_cancelled_evidence_preserved':True,'owned_http_streams':3,'credential_header_seen':False,
                    'simulated_public_https_transport':True,'simulated_provider_responses':True}
        finally:catalog.close()
    return [('Online PDF discovery resumes past front matter after restart',online_restart),
        ('Online PDF refresh retains unchanged cursors and relearns changed snapshots',online_refresh)]
