"""Bounded isolated PDF extraction, pinned packaged parser and local provenance."""
import hashlib
from importlib import resources
import json
import os
import subprocess
import sys
import threading

MAX_PDF_BYTES=5_000_000
PARSER_SHA256='f003fc2014814d264fe7dd3f9d435c158e23e1a85a2233f87a0a2d6d21c914ad'
READER_REVISION='pdf-reader-1/pypdf-6.20.0'
SLOTS=threading.BoundedSemaphore(2)


def extract_pdf(raw):
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
            result=subprocess.run([sys.executable,'-I','-c',script,str(path)],input=raw,stdout=subprocess.PIPE,
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
    return {**document,'reader_revision':READER_REVISION}


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
    if before.st_size>MAX_PDF_BYTES:raise ValueError('Installed PDF exceeds 5 MB.')
    with os.fdopen(open_read(path),'rb') as stream:
        opened=os.fstat(stream.fileno())
        if not opened_matches_path(before,opened):raise ValueError('Installed PDF identity changed while reading.')
        raw=stream.read(MAX_PDF_BYTES+1)
        if identity(opened)!=identity(os.fstat(stream.fileno())):raise ValueError('Installed PDF changed while reading.')
    if identity(before)!=identity(path.stat()) or hashlib.sha256(raw).hexdigest()!=manual['sha256']:
        raise ValueError('Installed PDF changed since discovery; rescan before using it.')
    key='pdf-manual:'+hashlib.sha256((app['id']+str(app['generation'])+manual['sha256']+READER_REVISION).encode()).hexdigest()
    cached=catalog.setting(key,None)
    result=cached or extract_pdf(raw)
    if cached is None:catalog.set_setting(key,result)
    return {'url':'installation-manual:'+manual['sha256']+'/'+manual['path'],'sha256':manual['sha256'],
            'retrieved_at':evidence.get('observed_at',''),**result}
