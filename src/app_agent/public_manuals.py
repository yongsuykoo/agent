"""Owned-thread persistence of checked public PDF snapshots; no PDF execution."""
import hashlib
import json
import os
import threading
import time
import uuid
from .jobs import process_alive
from .pdf_documents import MAX_PDF_BYTES,extract_pdf,manual_identity,progress_key,cache_key,put_state


class PublicCapture:
    """Network workers collect bounded bytes; only the catalog owner commits."""
    def __init__(self,app):
        self.app=app;self.documents=[];self.lock=threading.Lock()

    def __call__(self,raw,metadata):
        from .research import public_https
        public_https(metadata['url']);public_https(metadata['requested_url'])
        if not isinstance(raw,bytes) or not raw.startswith(b'%PDF-') or len(raw)>MAX_PDF_BYTES:
            raise ValueError('Public PDF must have its header and fit the 5 MB limit.')
        stamp=time.time()
        manual={**metadata,'sha256':hashlib.sha256(raw).hexdigest(),'format':'pdf','origin':'public',
            'path':metadata['requested_url'],'observed_at':stamp,'refresh_at':stamp+86400,'cached_bytes':len(raw)}
        with self.lock:
            if len(self.documents)>=5:raise ValueError('At most five public PDFs can be captured per research batch.')
            self.documents.append((manual,raw))
        return {**metadata,'format':'pdf','sha256':manual['sha256'],'deferred_pdf':True}

    def register(self,catalog,cancel=None,refresh_owner=None):
        if cancel is not None and cancel.is_set():return 0
        with self.lock:documents=list(self.documents)
        if not documents:return 0
        catalog.db.execute('BEGIN IMMEDIATE')
        try:
            app=self.app
            row=catalog.db.execute('SELECT blueprint FROM apps WHERE id=? AND generation=? AND present=1',(app['id'],app['generation'])).fetchone()
            if row is None:catalog.db.rollback();return 0
            count=0
            for manual,raw in documents:
                prior=catalog.db.execute('SELECT body FROM public_manuals WHERE app_id=? AND generation=? AND requested_url=?',
                    (app['id'],app['generation'],manual['requested_url'])).fetchone()
                previous=json.loads(prior[0]) if prior else {}
                lease=previous.get('refresh_lease',{})
                if refresh_owner is not None and (lease.get('owner')!=refresh_owner or lease.get('until',0)<=time.time()):continue
                if previous.get('observed_at',0)>manual['observed_at']:continue
                catalog.db.execute('INSERT INTO public_manuals VALUES (?,?,?,?,?) ON CONFLICT(app_id,generation,requested_url) DO UPDATE SET body=excluded.body,raw=excluded.raw',
                    (app['id'],app['generation'],manual['requested_url'],json.dumps(manual),raw))
                count+=1
            if count and not row[0]:
                from .pdf_documents import all_manuals
                pending=any(not catalog.setting(progress_key(app,m),{}).get('complete') for m in all_manuals(catalog,app,catalog.local_evidence(app['id'],app['generation']) or {}) if m.get('format')=='pdf')
                catalog.db.execute('UPDATE apps SET status=? WHERE id=? AND generation=? AND present=1',('manual_reading' if pending else 'queued',app['id'],app['generation']))
            if cancel is not None and cancel.is_set():catalog.db.rollback();return 0
            if count:catalog.dirty_knowledge()
            catalog.db.commit();return count
        except BaseException:catalog.db.rollback();raise


def manuals(catalog,app):
    return [json.loads(row[0]) for row in catalog.db.execute('SELECT body FROM public_manuals WHERE app_id=? AND generation=? ORDER BY requested_url',(app['id'],app['generation']))]


def read_pdf(catalog,app,manual):
    row=catalog.db.execute('SELECT body,raw FROM public_manuals WHERE app_id=? AND generation=? AND requested_url=?',
        (app['id'],app['generation'],manual['requested_url'])).fetchone()
    if row is None:raise ValueError('Public PDF snapshot is no longer registered for this app generation.')
    current=json.loads(row[0]);raw=row[1]
    if manual_identity(app,current)!=manual_identity(app,manual) or len(raw)>MAX_PDF_BYTES or hashlib.sha256(raw).hexdigest()!=manual['sha256']:
        raise ValueError('Public PDF snapshot changed; stale findings cannot be committed.')
    identity=manual_identity(app,manual);state=catalog.setting(progress_key(app,manual),{})
    cursor=state.get('cursor') or {'page':1,'offset':0};key=cache_key(identity,cursor)
    from .pdf_documents import valid_cursor
    if not valid_cursor(cursor):raise ValueError('Saved public PDF cursor is invalid.')
    cached=catalog.setting(key,None);result=cached or extract_pdf(raw,cursor,allow_empty=True)
    if cached is None:catalog.set_setting(key,result)
    return {key:manual[key] for key in ('url','requested_url','sha256','retrieved_at','origin')} | {
        'manual_identity':identity,'snapshot_reading':True,**result}


def refresh_available(manual,stamp):
    lease=manual.get('refresh_lease',{})
    return max(manual.get('refresh_at',0),manual.get('retry_at',0))<=stamp and not (
        lease.get('until',0)>stamp and process_alive(lease.get('pid')))


def refresh_next(catalog,emit,cancel=None):
    if cancel is not None and cancel.is_set():return {'status':'cancelled'}
    candidates=[(app,m) for app in catalog.apps() for m in manuals(catalog,app) if refresh_available(m,time.time())]
    if not candidates:return {'status':'no_public_refresh'}
    app,manual=min(candidates,key=lambda item:item[1]['refresh_at']);token=uuid.uuid4().hex
    catalog.db.execute('BEGIN IMMEDIATE')
    try:
        rows=manuals(catalog,app);current=next((m for m in rows if m['requested_url']==manual['requested_url']),None)
        present=catalog.db.execute('SELECT 1 FROM apps WHERE id=? AND generation=? AND present=1',(app['id'],app['generation'])).fetchone()
        if not present or not current or not refresh_available(current,time.time()):catalog.db.rollback();return {'status':'public_refresh_busy'}
        current['refresh_lease']={'owner':token,'pid':os.getpid(),'until':time.time()+60}
        catalog.db.execute('UPDATE public_manuals SET body=? WHERE app_id=? AND generation=? AND requested_url=?',
            (json.dumps(current),app['id'],app['generation'],manual['requested_url']))
        catalog.db.commit()
    except BaseException:catalog.db.rollback();raise
    error=None
    try:
        from .research import fetch_document,DOCUMENT_SLOTS
        capture=PublicCapture(app)
        with DOCUMENT_SLOTS:fetch_document(manual['requested_url'],pdf_capture=capture)
        if not capture.documents:raise ValueError('Public PDF refresh returned a different document type.')
        if cancel is not None and cancel.is_set():return {'status':'cancelled'}
        if not capture.register(catalog,cancel,refresh_owner=token):
            if cancel is not None and cancel.is_set():return {'status':'cancelled'}
            error='Public PDF refresh ownership or app generation changed before commit.'
            return {'status':'public_refresh_changed'}
        changed=capture.documents[0][0]['sha256']!=manual['sha256'] or capture.documents[0][0]['url']!=manual['url']
        emit(f"Public PDF source {'changed; reading restarted' if changed else 'unchanged; reading retained'} for {app['name']}.")
        return {'status':'public_manual_changed' if changed else 'public_manual_unchanged','app':app['name']}
    except Exception as failure:
        error=str(failure);emit(f"Public PDF refresh deferred for {app['name']}: {error}")
        return {'status':'public_refresh_deferred','app':app['name'],'error':error}
    finally:
        catalog.db.execute('BEGIN IMMEDIATE')
        try:
            current=next((m for m in manuals(catalog,app) if m['requested_url']==manual['requested_url']),None)
            if current and current.get('refresh_lease',{}).get('owner')==token:
                current.pop('refresh_lease',None)
                if error is not None:current.update(retry_at=time.time()+900,error=error[:500])
                catalog.db.execute('UPDATE public_manuals SET body=? WHERE app_id=? AND generation=? AND requested_url=?',
                    (json.dumps(current),app['id'],app['generation'],manual['requested_url']))
            catalog.db.commit()
        except BaseException:catalog.db.rollback();raise


def exhausted_urls(catalog,app):
    return list(dict.fromkeys(url for m in manuals(catalog,app) if catalog.setting(progress_key(app,m),{}).get('complete') for url in (m['requested_url'],m['url'])))
