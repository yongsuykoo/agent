"""Resume installed PDF study without a demonstration or a daily pause."""
import json
import os
import time
import uuid
from datetime import datetime,timezone
from .jobs import process_alive
from .learning import merge_blueprints
from .pdf_documents import installed_pdf,progress_key,put_state,acknowledge_sources,READER_REVISION


def available(state,stamp):
    lease=state.get('lease',{})
    return not state.get('complete') and state.get('retry_at',0)<=stamp and not (
        lease.get('until',0)>stamp and process_alive(lease.get('pid')))


def draft_key(app):
    return f"pdf-bootstrap:{app['id']}:{app['generation']}"


def reading_blueprint(catalog,app):
    return app.get('blueprint') or catalog.setting(draft_key(app),{
        'name':app['name'],'version':app.get('version',''),
        'capabilities':[],'sources':[],'limitations':[]})


def pending_manuals(catalog):
    stamp=time.time();priority=set(catalog.setting('priority_apps',[]));pending=[]
    for app in catalog.apps():
        # Initial research owns this generation until its lease completes.
        if not app.get('blueprint') and app['status']=='researching':continue
        evidence=catalog.local_evidence(app['id'],app['generation']) or {}
        for manual in evidence.get('manuals',[]):
            if manual.get('format')!='pdf':continue
            state=catalog.setting(progress_key(app,manual),{})
            if available(state,stamp):pending.append((app,manual,evidence,state))
    pending.sort(key=lambda item:(item[0]['id'] not in priority,item[3].get('reviewed_chunks',0),item[0]['name'].casefold(),item[1]['path']))
    return pending


def claim(catalog,app,manual):
    key=progress_key(app,manual);stamp=time.time();token=uuid.uuid4().hex
    catalog.db.execute('BEGIN IMMEDIATE')
    try:
        row=catalog.db.execute('SELECT blueprint,status FROM apps WHERE id=? AND generation=? AND present=1',(app['id'],app['generation'])).fetchone()
        state=catalog.setting(key,{})
        if not row or (not row[0] and row[1]=='researching') or not available(state,stamp):catalog.db.rollback();return None
        put_state(catalog,key,{**state,'lease':{'owner':token,'pid':os.getpid(),'until':stamp+900}})
        if not row[0]:
            catalog.db.execute("UPDATE apps SET status='manual_reading' WHERE id=? AND generation=? AND present=1",(app['id'],app['generation']))
        catalog.db.commit();return token
    except BaseException:catalog.db.rollback();raise


def release(catalog,key,token,error=None,app=None):
    catalog.db.execute('BEGIN IMMEDIATE')
    try:
        state=catalog.setting(key,{})
        if state.get('lease',{}).get('owner')==token:
            state.pop('lease',None)
            if error is not None:state.update(retry_at=time.time()+900,error=str(error)[:500])
            put_state(catalog,key,state)
            if error is not None and app is not None:
                # Unreadable manuals must not strand an app: normal research
                # can now look for other installed/public documentation.
                manuals=(catalog.local_evidence(app['id'],app['generation']) or {}).get('manuals',[])
                owners=[catalog.setting(progress_key(app,item),{}).get('lease',{}) for item in manuals if item.get('format')=='pdf']
                if not any(owner.get('until',0)>time.time() and process_alive(owner.get('pid')) for owner in owners):
                    catalog.db.execute("UPDATE apps SET status='queued' WHERE id=? AND generation=? AND present=1 AND blueprint IS NULL AND status='manual_reading'",(app['id'],app['generation']))
        catalog.db.commit()
    except BaseException:catalog.db.rollback();raise


def commit(catalog,app,manual,token,source,additional,cancel=None):
    """Merge the latest blueprint and cursor in one fenced SQLite transaction."""
    key=progress_key(app,manual)
    catalog.db.execute('BEGIN IMMEDIATE')
    try:
        row=catalog.db.execute('SELECT blueprint FROM apps WHERE id=? AND generation=? AND present=1',(app['id'],app['generation'])).fetchone()
        state=catalog.setting(key,{})
        if (cancel is not None and cancel.is_set()) or not row or state.get('lease',{}).get('owner')!=token or state.get('lease',{}).get('until',0)<=time.time() or state.get('complete') or state.get('cursor',{'page':1,'offset':0})!=source['read_cursor']:
            catalog.db.rollback();return None
        if acknowledge_sources(catalog,app,[source])!=1:catalog.db.rollback();return None
        previous=json.loads(row[0]) if row[0] else reading_blueprint(catalog,{**app,'blueprint':None})
        combined,added=merge_blueprints(previous,additional)
        ready=bool(combined['capabilities'])
        if ready:
            catalog.db.execute("UPDATE apps SET blueprint=?,status='documented',error=NULL,attempts=0,retry_at=NULL WHERE id=? AND generation=? AND present=1",(json.dumps(combined),app['id'],app['generation']))
            catalog.db.execute('DELETE FROM settings WHERE key=?',(draft_key(app),))
        else:
            put_state(catalog,draft_key(app),combined)
            manuals=(catalog.local_evidence(app['id'],app['generation']) or {}).get('manuals',[])
            more=any(not catalog.setting(progress_key(app,item),{}).get('complete') for item in manuals if item.get('format')=='pdf')
            catalog.db.execute('UPDATE apps SET status=?,error=NULL,retry_at=NULL WHERE id=? AND generation=? AND present=1',
                ('manual_reading' if more else 'queued',app['id'],app['generation']))
        state=catalog.setting(key,{});state.pop('lease',None);state.pop('error',None);state.pop('retry_at',None)
        put_state(catalog,key,state);catalog.dirty_knowledge()
        if cancel is not None and cancel.is_set():catalog.db.rollback();return None
        catalog.db.commit()
        return {'new_capabilities':added,'blueprint_ready':ready,'reading_complete':state['complete'],'reviewed_chunks':state['reviewed_chunks']}
    except BaseException:catalog.db.rollback();raise


def continue_manual(catalog,cloud,emit,daily_limit=0,cancel=None):
    cancelled=lambda:cancel is not None and cancel.is_set()
    if cancelled():return {'status':'cancelled'}
    candidates=pending_manuals(catalog)
    if not candidates:return {'status':'no_pending_manual'}
    app,manual,evidence,_=candidates[0];key=progress_key(app,manual);token=claim(catalog,app,manual)
    if token is None:return {'status':'manual_busy'}
    failure=None
    try:
        document=installed_pdf(catalog,app,evidence,manual)
        if cancelled():return {'status':'cancelled'}
        emit(f"Continuing {app['name']} manual at page {document['read_cursor']['page']}, character {document['read_cursor']['offset']}.")
        if document['text']:
            if catalog.consume_budget('research_budget',daily_limit) is None:return {'status':'daily_limit'}
            old=reading_blueprint(catalog,catalog.get(app['id']))
            extracted=cloud.extract(app['name'],app.get('version',''),[document],
                known_capabilities=[cap['name'] for cap in old['capabilities']],allow_empty=True)
            if not extracted['capabilities']:
                extracted['limitations'].append('This inspected section establishes no new operating procedure. Reading alone does not establish app understanding.')
        else:
            extracted={'capabilities':[],'limitations':['Inspected PDF pages have no extractable text; they may be blank or scanned. No operation is inferred.']}
        if cancelled():return {'status':'cancelled'}
        try:current=catalog.get(app['id'])
        except KeyError:return {'status':'app_changed'}
        if current['generation']!=app['generation']:return {'status':'app_changed'}
        # A manual can change while a provider request is in flight.
        checked=installed_pdf(catalog,app,evidence,manual)
        if checked['read_cursor']!=document['read_cursor']:return {'status':'manual_checkpoint_changed'}
        source={key:value for key,value in document.items() if key!='text'}
        additional={'name':app['name'],'version':app.get('version',''),'sources':[source],**extracted,
            'evidence_origin':'installed_manuals','updated_at':datetime.now(timezone.utc).isoformat()}
        if cancelled():return {'status':'cancelled'}
        result=commit(catalog,app,manual,token,source,additional,cancel)
        if result is None:return {'status':'cancelled' if cancelled() else 'manual_checkpoint_changed'}
        return {'status':'manual_complete' if result['reading_complete'] else 'manual_progress','app':app['name'],**result}
    except Exception as error:
        failure=error
        from .campaign import cloud_blocked
        emit(f"Manual study deferred for {app['name']}: {error}")
        return {'status':'cloud_blocked' if cloud_blocked(error) else 'manual_deferred','app':app['name'],'error':str(error)}
    finally:release(catalog,key,token,failure,app)


def manual_report(catalog,app,evidence):
    result=[]
    for manual in evidence.get('manuals',[]):
        if manual.get('format')!='pdf':continue
        state=catalog.setting(progress_key(app,manual),{})
        result.append({'manual':manual['path'],'reader_revision':READER_REVISION,
            'blueprint_ready':bool(app.get('blueprint')),
            'reading_complete':bool(state.get('complete')),'next_cursor':state.get('cursor',{'page':1,'offset':0}),
            'reviewed_chunks':state.get('reviewed_chunks',0),'characters_reviewed':state.get('characters_reviewed',0),
            'page_count':state.get('page_count'),'no_text_pages':state.get('no_text_pages',[]),
            'deferred':state.get('retry_at',0)>time.time()})
    return result
