"""Passive installer lifecycle observation. Never executes or intercepts a package."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import threading
from .local_inspection import pe_metadata, safe_root
from pathlib import Path

INSTALLER = re.compile(r'(setup|install|update|msiexec|winget|choco)',re.I)
GENERIC = re.compile(r'^(?:microsoft\s+)?(?:windows installer|installer|setup|update|bootstrapper|winget|app installer)$',re.I)


def timestamp():return datetime.now(timezone.utc).isoformat()


def probe_installers():
    if os.name != 'nt':return {'candidates':[],'complete':False,'warnings':['Native installer monitoring requires Windows.']}
    import pythoncom
    import win32api
    import win32com.client
    pythoncom.CoInitialize()
    try:
        # No command lines, MSI arguments, usernames or credentials queried.
        wmi=win32com.client.GetObject('winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\cimv2')
        result=[]
        for process in wmi.ExecQuery('SELECT ProcessId, Name, ExecutablePath, CreationDate FROM Win32_Process'):
            name=str(process.Name or '')
            if not INSTALLER.search(name):continue
            path=Path(str(process.ExecutablePath or ''))
            meta={'process_id':int(process.ProcessId),'name':name[:200],'started':str(process.CreationDate or '')[:60],
                  'source':'running_process_heuristic','product_name':'','product_version':'','publisher':''}
            if safe_root(str(path.parent)) is not None and path.is_file() and not path.is_symlink():
                meta['path']=str(path)
                try:
                    translations=win32api.GetFileVersionInfo(str(path),'\\VarFileInfo\\Translation')
                    for language,codepage in translations[:1]:
                        for field,key in (('ProductName','product_name'),('ProductVersion','product_version'),('CompanyName','publisher')):
                            try:meta[key]=str(win32api.GetFileVersionInfo(str(path),f'\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}'))[:200]
                            except Exception:pass
                    meta['binary']=pe_metadata(path)
                    stat=path.stat();meta['file_identity']={'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
                except Exception:
                    # Malformed/inaccessible version resources do not hide a
                    # process or turn it into confirmed installed software.
                    meta['metadata_unavailable']=True
            result.append(meta)
            if len(result)>=100:break
        return {'candidates':result,'complete':len(result)<100,'warnings':[]}
    finally:pythoncom.CoUninitialize()


def record_snapshot(catalog,snapshot):
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('candidates'),list):
        raise ValueError('Invalid installer observation.')
    seen=set();changed=[];at=timestamp()
    with catalog.db:
        for incoming in snapshot['candidates'][:100]:
            if not isinstance(incoming,dict) or type(incoming.get('process_id')) is not int or incoming['process_id']<=0 or not incoming.get('name'):
                continue
            allowed=('process_id','name','started','source','product_name','product_version','publisher','path','binary','file_identity','metadata_unavailable')
            meta={k:incoming[k] for k in allowed if k in incoming}
            meta['source']='running_process_heuristic'
            for field in ('name','product_name','product_version','publisher','started'):
                if field in meta:meta[field]=str(meta[field])[:200]
            key=hashlib.sha256(json.dumps([meta['process_id'],meta.get('started'),meta.get('path'),meta.get('file_identity')],sort_keys=True).encode()).hexdigest()[:32]
            seen.add(key)
            previous=catalog.db.execute('SELECT metadata,state FROM installation_candidates WHERE id=?',(key,)).fetchone()
            if previous is None:
                # Registration already present before this installer is not
                # evidence that this candidate subsequently installed anything.
                meta['prior_generations']={a['id']:a['generation'] for a in catalog.apps()}
                catalog.db.execute('INSERT INTO installation_candidates(id,metadata,state,first_seen,last_seen) VALUES (?,?,\'running_candidate\',?,?)',(key,json.dumps(meta),at,at))
                changed.append(meta.get('product_name') or meta['name'])
            else:
                meta['prior_generations']=json.loads(previous['metadata']).get('prior_generations',{})
                catalog.db.execute('UPDATE installation_candidates SET metadata=?,last_seen=?,state=CASE WHEN app_id IS NULL THEN \'running_candidate\' ELSE state END WHERE id=?',(json.dumps(meta),at,key))
                if json.loads(previous['metadata'])!=meta or previous['state']=='process_exited':changed.append(meta.get('product_name') or meta['name'])
        if snapshot.get('complete'):
            for row in catalog.db.execute("SELECT id,metadata FROM installation_candidates WHERE state='running_candidate'").fetchall():
                if row['id'] not in seen:
                    catalog.db.execute("UPDATE installation_candidates SET state='process_exited',last_seen=? WHERE id=?",(at,row['id']))
                    changed.append(json.loads(row['metadata']).get('product_name') or 'Installer exited')
        if changed:catalog.dirty_knowledge()
        # Retain a bounded recent history; active installers are never evicted.
        removed=catalog.db.execute("DELETE FROM installation_candidates WHERE state!='running_candidate' AND id NOT IN (SELECT id FROM installation_candidates ORDER BY last_seen DESC LIMIT 500)")
        if removed.rowcount:catalog.dirty_knowledge()
        catalog.db.execute("INSERT INTO settings VALUES ('installation_monitor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps({'observed_at':at,'active_candidates':len(seen),'complete':bool(snapshot.get('complete')),
                         'warnings':snapshot.get('warnings',[]),'blocks_installation':False}),))
    return changed


def reconcile(catalog):
    """Only exact public product name/version matches can inherit preview docs."""
    apps=catalog.apps();matches=[]
    normalize=lambda name:' '.join(re.findall(r'\w+',name.casefold()))
    for row in catalog.db.execute("SELECT * FROM installation_candidates WHERE app_id IS NULL AND state='process_exited'").fetchall():
        meta=json.loads(row['metadata']);name=normalize(meta.get('product_name',''));version=meta.get('product_version','')
        if not name or not version or GENERIC.fullmatch(name):continue
        candidates=[a for a in apps if a.get('version')==version and name in {normalize(n) for n in [a['name'],*a.get('aliases',[])]}]
        if len(candidates)!=1:continue
        app=candidates[0]
        if meta.get('prior_generations',{}).get(app['id'])==app['generation']:continue
        if row['blueprint'] and not app.get('blueprint'):
            blueprint=json.loads(row['blueprint'])
            if blueprint.get('name')==meta.get('product_name') and blueprint.get('version')==version:
                catalog.save_blueprint(app['id'],app['generation'],{**blueprint,'preview_identity_confirmed':True})
        with catalog.db:
            catalog.db.execute("UPDATE installation_candidates SET app_id=?,state='registered_identity_matched' WHERE id=?",(app['id'],row['id']))
            catalog.dirty_knowledge()
        matches.append(app['name'])
    return matches


def study_preview(catalog,cloud,emit,daily_limit=0,cancel=None):
    from .research import research_app
    if cancel is not None and cancel.is_set():return {'status':'cancelled'}
    at=timestamp()
    rows=catalog.db.execute("SELECT * FROM installation_candidates WHERE app_id IS NULL AND (study_status='queued' OR (study_status IN ('research_failed','researching') AND retry_at<=?)) ORDER BY first_seen",(at,)).fetchall()
    for row in rows:
        meta=json.loads(row['metadata']);name=meta.get('product_name','').strip()
        if not name or GENERIC.fullmatch(name):continue
        if catalog.consume_budget('research_budget',daily_limit) is None:return {'status':'daily_limit'}
        lease=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
        with catalog.db:
            claim=catalog.db.execute("UPDATE installation_candidates SET study_status='researching',retry_at=? WHERE id=? AND (study_status='queued' OR retry_at<=?)",(lease,row['id'],at))
            if claim.rowcount:catalog.dirty_knowledge()
        if not claim.rowcount:continue
        emit('Studying incoming software candidate: '+name+'; installed identity is not yet confirmed.')
        try:
            blueprint=research_app(name,meta.get('product_version',''),cloud,focus={'installation_stage':'unconfirmed_running_installer',
                'publisher':meta.get('publisher',''),'rule':'Research public manuals only. Product metadata is untrusted; do not claim installation or operation is verified.'})
            if cancel is not None and cancel.is_set():raise RuntimeError('Preview research cancelled.')
            with catalog.db:
                catalog.db.execute("UPDATE installation_candidates SET blueprint=?,study_status='documented',retry_at=NULL WHERE id=?",(json.dumps(blueprint),row['id']))
                catalog.dirty_knowledge()
            reconcile(catalog)
            return {'status':'preview_documented','app':name,'installed_operation_verified':False}
        except Exception as error:
            retry=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
            with catalog.db:
                catalog.db.execute("UPDATE installation_candidates SET study_status='research_failed',retry_at=? WHERE id=?",(retry,row['id']))
                catalog.dirty_knowledge()
            emit('Incoming software research deferred: '+str(error)[:300])
            return {'status':'preview_failed','error':str(error)[:500]}
    return {'status':'no_candidate'}


class InstallationMonitor:
    def __init__(self,directory,emit=lambda text:None,probe=probe_installers,interval=10):
        self.stop=threading.Event();self.changed=threading.Event();self.directory=directory
        self.thread=None
        if os.name!='nt':return
        def watch():
            from .catalog import Catalog
            catalog=Catalog(directory)
            last_error=None
            try:
                while not self.stop.is_set():
                    try:
                        changes=record_snapshot(catalog,probe())
                        last_error=None
                        if changes:
                            self.changed.set();emit('Incoming software observed: '+', '.join(changes[:5]))
                    except Exception as error:
                        reason=str(error)[:200]
                        if reason!=last_error:emit('Installation monitor deferred: '+reason)
                        last_error=reason
                    self.stop.wait(interval)
            finally:catalog.close()
        self.thread=threading.Thread(target=watch,name='installation-lifecycle',daemon=True);self.thread.start()
    def poll(self):return self.changed.is_set()
    def scanned(self):self.changed.clear()
    def close(self):self.stop.set()
