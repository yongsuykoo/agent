"""Native Office goals with versioned recipes and durable file verification."""
from datetime import datetime, timezone
from pathlib import Path
import uuid
from .office import Office
from .office_plan import plan_office, validate_workbook, validate_document
from .office_artifacts import verify_workbook, verify_document
from .native_tasks import _save


def run_office(director,task,route,adapter=Office):
    app,family=route['app'],route['family']
    validate=validate_workbook if family=='excel' else validate_document
    verify=verify_workbook if family=='excel' else verify_document
    checkpoint=getattr(director,'checkpoint',None)
    result={'task':task,'outcome':'blocked','steps':[],'verified_results':[],
            'time':datetime.now(timezone.utc).isoformat(),
            'scope':'New Office file content verified against a bounded plan; arbitrary app mastery and full semantic goal correctness are not certified.'}
    native=None;started=False
    try:
        def current():
            latest=director.catalog.get(app['id'])
            if director.cancel.is_set() or not latest or not latest.get('present',True) or latest['generation']!=app['generation']:
                raise RuntimeError('Task cancelled or Office installation changed.')
            if checkpoint:checkpoint.touch()
        current()
        if checkpoint:
            saved=checkpoint.jobs.get(checkpoint.id)
            durable={'steps':[{'app_id':app['id'],'task':task,'expected_result':'Verified '+family+' artifact'}],
                     'os_build':director.catalog.setting('machine_model',{}).get('os',{}).get('build'),
                     'generations':{app['id']:app['generation']},'tool':'office:'+family}
            if saved['plan'] and saved['plan']!=durable:raise RuntimeError('Saved Office plan changed; stale plan not replayed.')
            if saved['verified']:
                record=checkpoint.records()[-1]
                proof=verify(record['path'],record['plan'])
                if proof['files']!=saved['verified'][0]:raise RuntimeError('Saved verified Office file changed; automatic recreation stopped.')
                result.update(outcome='artifacts_verified',steps=[record],verified_results=proof['files'])
                return _save(director,result)
        desktop=director.resolve(app,director.cancel);observed=desktop.observe()
        identity=tuple(observed.get(k) for k in ('window_handle','process_id'))
        try:native=adapter(app,observed,family)
        except Exception as error:
            # No COM write has happened. The generic workflow may still support this app.
            director.emit('Native Office interface unavailable; using desktop workflow: '+str(error)[:300])
            return None
        native_identity={k:native.info[k] for k in ('name','version','path')}
        cached=director.catalog.artifact_recipe(app['id'],app['generation'],task)
        plan=None
        if cached and cached.get('tool')=='office:'+family and cached.get('native_identity')==native_identity:
            try:plan=validate(cached['plan'],task)
            except (ValueError,KeyError,TypeError):pass
        if plan is None:
            try:plan=plan_office(task,family,director.cloud,director.cancel)
            except ValueError as error:
                if checkpoint and saved['plan']:raise
                director.emit('Office goal exceeds the native data tool; using desktop workflow: '+str(error)[:300])
                return None
        else:director.emit('Reusing a verified Office recipe; saved bytes will be checked again.')
        if checkpoint:checkpoint.save_plan(durable)
        current()
        action={'kind':'create_artifact','target':0,'text':'Create a new '+family+' file in a fresh App Agent output folder.',
                'reason':'Use the documented Office interface and independently verify saved content.'}
        if not director.approve(action,observed):
            result['outcome']='cancelled' if director.cancel.is_set() else 'blocked'
            return _save(director,result)
        def guard():
            current()
        guard()
        if identity!=tuple(desktop.observe().get(k) for k in ('window_handle','process_id')):
            raise RuntimeError('Selected Office window/process changed before creation.')
        directory=Path(director.directory)/'outputs'/('office-'+uuid.uuid4().hex)
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [directory,*directory.parents]):
            raise ValueError('Output folder cannot traverse a link or junction.')
        directory.mkdir(parents=True,exist_ok=False)
        path=directory/('workbook.xlsx' if family=='excel' else 'document.docx')
        record={'task':task,'tool':'office:'+family,'plan':plan,'path':str(path),'native_identity':native_identity}
        result['steps'].append(record)
        effect=checkpoint.begin_effect({'kind':'create_artifact','path':str(path),'app_id':app['id']}) if checkpoint else None
        started=True
        director.emit('Creating '+family+' artifact; checking saved data and calculations next.')
        native.render(plan,path,guard)
        if checkpoint:checkpoint.applied(effect)
        current()
        record['verification']=verify(path,plan)
        current();record['outcome']='artifact_verified'
        if not director.catalog.save_artifact_workflow(app['id'],app['generation'],record):raise RuntimeError('Office installation changed before recipe persistence.')
        if checkpoint:checkpoint.verified(record['verification']['files'],record)
        result.update(outcome='artifacts_verified',verified_results=record['verification']['files'])
        director.emit('Verified Office file: '+str(path))
    except Exception as error:
        result['error']=str(error)[:1500]
        result['outcome']='cancelled' if director.cancel.is_set() else 'verification_failed' if started else 'blocked'
        if result['steps']:result['steps'][-1].update(outcome='verification_failed',error=result['error'])
        director.emit('Office task stopped: '+str(error)[:500])
    finally:
        if native is not None:
            try:native.close()
            except Exception as error:result['cleanup_warning']=str(error)[:500]
    return _save(director,result)
