"""Bounded isolated PDF extraction, pinned packaged parser and local provenance."""
import hashlib
from importlib import resources
import json
import os
import stat
import subprocess
import sys
import threading

MAX_PDF_BYTES=5_000_000
PARSER_SHA256='f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad'
READER_REVISION='pdf-reader-2/pypdf-6.20.0'
SLOTS=threading.BoundedSemaphore(2)


def valid_cursor(cursor):
    return isinstance(cursor,dict) and set(cursor)=={'page','offset'} and type(cursor['page']) is int and 1<=cursor['page']<=1024 and type(cursor['offset']) is int and 0<=cursor['offset']<=8_000_000


def extract_pdf(raw,cursor=None,allow_empty=False):
    cursor={'page':1,'offset':0} if cursor is None else cursor
    if not valid_cursor(cursor) or type(allow_empty) is not bool:raise ValueError('Invalid PDF reading cursor.')
    if not isinstance(raw,bytes) or not raw.startswith(b'%PDF-') or len(raw)>MAX_PDF_BYTES:
        raise ValueError('PDF must have its PDF header and fit the 5 MB manual limit.')
    # Do not pass provider keys or desktop/controller configuration to the parser.
    names=('SYSTEMROOT','SystemRoot','WINDIR','PATH','TEMP','TMP','LANG','LC_ALL','LD_LIBRARY_PATH','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR')
    environment={k:os.environ[k] for k in names if k in os.environ}
    package=resources.files('app_agent');wheel=package.joinpath('vendor/pypdf.whl')
    if hashlib.sha256(wheel.read_bytes()).hexdigest()!=PARSER_SHA256:
        raise RuntimeError('Packaged PDF parser checksum mismatch; no manual parsed.')
    script=package.joinpath('_pdf_worker.py').read_text(encoding='utf-8')
    with SLOTS,resources.as_file(wheel) as path:
        try:
            result=subprocess.run([sys.executable,'-I','-c',script,str(path),str(cursor['page']),str(cursor['offset']),'1' if allow_empty else '0'],input=raw,stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,timeout=8,env=environment)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('PDF manual parsing exceeded its eight-second deadline; reader terminated.') from error
    if len(result.stdout)>200_000:raise RuntimeError('PDF parser output exceeded its limit.')
    try:packet=json.loads(result.stdout)
    except (ValueError,UnicodeError) as error:raise RuntimeError('PDF parser exited without bounded readable evidence.') from error
    if not isinstance(packet,dict):raise RuntimeError('PDF parser returned invalid evidence.')
    if result.returncode or 'error' in packet:raise ValueError(packet.get('error','PDF parser exceeded a process resource limit.'))
    document=packet.get('result')
    if not isinstance(document,dict) or not isinstance(document.get('text'),str) or len(document['text'])>24000 or not document.get('pages'):
        raise RuntimeError('PDF parser returned invalid evidence.')
    upcoming=document.get('next_cursor')
    if document.get('read_cursor')!=cursor or (upcoming is not None and (not valid_cursor(upcoming) or (upcoming['page'],upcoming['offset'])<=(cursor['page'],cursor['offset']))):
        raise RuntimeError('PDF parser returned invalid progress.')
    return {**document,'reader_revision':READER_REVISION,'text_sha256':hashlib.sha256(document['text'].encode()).hexdigest()}


def manual_identity(app,manual):
    fields=[app['id'],app['generation'],manual['sha256'],manual['path'],manual.get('root'),READER_REVISION]
    return hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest()


def progress_key(app,manual):return 'pdf-study:'+manual_identity(app,manual)


def cache_key(identity,cursor):return 'pdf-manual:'+identity+':'+str(cursor['page'])+'/'+str(cursor['offset'])


def put_state(catalog,key,value):
    # Used inside the caller's transaction; never commit half a study checkpoint.
    catalog.db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))


def acknowledge_sources(catalog,app,sources):
    """Advance only locally cached, exact current-generation PDF evidence.

    The caller owns a transaction containing the blueprint write. Merely opening
    a manual, a failed provider response or a stale source cannot move the cursor.
    """
    evidence=catalog.local_evidence(app['id'],app['generation']) or {};advanced=0
    for manual in evidence.get('manuals',[]):
        if manual.get('format')!='pdf':continue
        identity=manual_identity(app,manual);key=progress_key(app,manual)
        for source in sources:
            if not isinstance(source,dict) or source.get('manual_identity')!=identity or source.get('sha256')!=manual['sha256']:continue
            if source.get('url')!='installation-manual:'+manual['sha256']+'/'+manual['path']:continue
            state=catalog.setting(key,{})
            cursor=state.get('cursor',{'page':1,'offset':0})
            if state.get('complete') or source.get('read_cursor')!=cursor:continue
            cached=catalog.setting(cache_key(identity,cursor),None)
            fields=('read_cursor','next_cursor','pages','page_count','pages_read','reader_revision','text_sha256')
            if not cached or any(source.get(field)!=cached.get(field) for field in fields):continue
            gaps=sorted(set(state.get('no_text_pages',[])+[p['page'] for p in cached['pages'] if not p['characters']]))
            put_state(catalog,key,{**state,'cursor':cached['next_cursor'],'complete':cached['next_cursor'] is None,
                'reviewed_chunks':state.get('reviewed_chunks',0)+1,'characters_reviewed':state.get('characters_reviewed',0)+sum(p['characters'] for p in cached['pages']),
                'page_count':cached['page_count'],'no_text_pages':gaps})
            advanced+=1
    return advanced


def installed_pdf(catalog,app,evidence,manual):
    """Recheck exact discovered installation bytes before cached or new reading."""
    from pathlib import Path
    from .file_tools import safe_path,open_read,identity,opened_matches_path
    item=next((row for row in evidence.get('files',[]) if row.get('kind')=='manual' and row['path']==manual['path'] and row['root']==manual.get('root')),None)
    if not item or item['root'] not in evidence.get('roots',[]):raise ValueError('PDF is not a discovered installation manual.')
    root=safe_path(item['root']);relative=Path(item['path'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('PDF manual path left its installation scope.')
    path=safe_path(root/relative)
    if not path.is_relative_to(root):raise ValueError('PDF manual path left its installation scope.')
    before=path.stat()
    if not stat.S_ISREG(before.st_mode):raise ValueError('Installed PDF must be a regular file.')
    if before.st_size>MAX_PDF_BYTES:raise ValueError('Installed PDF exceeds 5 MB.')
    with os.fdopen(open_read(path),'rb') as stream:
        opened=os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not opened_matches_path(before,opened):raise ValueError('Installed PDF identity changed while reading.')
        raw=stream.read(MAX_PDF_BYTES+1)
        if identity(opened)!=identity(os.fstat(stream.fileno())):raise ValueError('Installed PDF changed while reading.')
    if identity(before)!=identity(path.stat()) or hashlib.sha256(raw).hexdigest()!=manual['sha256']:
        raise ValueError('Installed PDF changed since discovery; rescan before using it.')
    identity_key=manual_identity(app,manual);state=catalog.setting(progress_key(app,manual),{})
    cursor=state.get('cursor') or {'page':1,'offset':0}
    if not valid_cursor(cursor):raise ValueError('Saved PDF reading progress is invalid.')
    key=cache_key(identity_key,cursor)
    cached=catalog.setting(key,None)
    result=cached or extract_pdf(raw,cursor,allow_empty=True)
    if cached is None:catalog.set_setting(key,result)
    return {'url':'installation-manual:'+manual['sha256']+'/'+manual['path'],'sha256':manual['sha256'],
            'retrieved_at':evidence.get('observed_at',''),'manual_identity':identity_key,**result}
