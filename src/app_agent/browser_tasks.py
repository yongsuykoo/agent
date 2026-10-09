"""Browser goals share task permission, guarded replay and durable action journals."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import uuid
from .browser import Browser
from .native_tasks import _save
from .runner import result_matches


def run_browser(director,task,request,browser_factory=None,session_store=None):
    browser_factory=browser_factory or Browser
    checkpoint=director.checkpoint;browser=None
    result={'task':task,'outcome':'blocked','steps':[],'verified_results':[],
            'time':datetime.now(timezone.utc).isoformat(),
            'scope':'Exact rendered DOM output observed in one isolated browser tab; external service delivery and universal app mastery are not certified.'}
    plan={'tool':'browser','request':request,'steps':[{'task':task,'expected_result':request['expected_result']}]}
    def guard():
        if director.cancel.is_set():raise RuntimeError('Browser task cancelled.')
        if checkpoint:checkpoint.touch()
    try:
        guard()
        if checkpoint:
            saved=checkpoint.jobs.get(checkpoint.id)
            if saved['plan'] and saved['plan']!=plan and (saved['verified'] or checkpoint.pending_actions()):
                raise RuntimeError('Browser scope changed after an effect; no automatic replay.')
            if saved['verified']:
                record=checkpoint.records()[-1];proof=record['proof']
                from .file_tools import safe_path
                path=safe_path(proof['path'])
                if path.parent!=safe_path((director.directory/'browser-evidence').absolute()) or path.stat().st_size>4*1024*1024:
                    raise RuntimeError('Saved browser observation has an invalid scope or size.')
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=proof['sha256']:raise RuntimeError('Saved browser observation changed; no automatic re-click.')
                observation=json.loads(raw)
                if not result_matches(observation,request['expected_result'],result_control_id='page:output'):
                    raise RuntimeError('Saved browser observation does not match the submitted result.')
                result.update(outcome='steps_verified',steps=[record],verified_results=saved['verified'],
                              scope='Previously observed browser result retained without reopening the page or repeating actions; current external service state is not revalidated.')
                return _save(director,result)
        session=None
        if request.get('session'):
            from .browser_sessions import BrowserSessions
            session=(session_store or BrowserSessions(director.directory)).get(request['session'],request['url'])
        observation={'window':'Owned browser session' if session else 'New isolated browser session','controls':[{'id':0,'name':request['url'],'type':'URL'}]}
        if not director.approve({'kind':'open_browser','target':0,'text':request['url'],
                'reason':('Reuse agent-owned session '+request['session'] if session else 'Open a fresh profile')+'; operate only this requested browser task and verify exact rendered output.'},observation):
            result['outcome']='cancelled' if director.cancel.is_set() else 'blocked'
            return _save(director,result)
        guard()
        if checkpoint:checkpoint.save_plan(plan)
        browser=browser_factory(guard,session=session) if session else browser_factory(guard)
        browser.start(request['url'])
        desktop=checkpoint.desktop(browser) if checkpoint else browser
        # The exact full user goal and installed browser revision identify a recipe.
        version={key:browser.info.get(key) for key in ('product','revision','protocolVersion')}
        from .browser_scripts import DOM_TOOLS_VERSION
        version['dom_tools']=DOM_TOOLS_VERSION
        if session:version['session']={key:session.metadata[key] for key in ('id','revision','origin')}
        key='browser-workflow:'+hashlib.sha256(task.encode()).hexdigest()
        cached=director.catalog.setting(key,{})
        previous=[cached['record']] if cached.get('version')==version and cached.get('record',{}).get('recipe') else []
        blueprint={'name':'Isolated browser DOM','capabilities':['Read rendered controls including open shadow roots and same-origin frames','Replace text-field value or a bounded editable rich-text document with literal plain text','Click buttons, tabs, menu items, radio buttons and custom options','Set native checkbox or advertised ARIA checkbox/switch/toggle-button state','Select one enabled dropdown option using text equal to its exact advertised value'],
                   'limitations':['Use only advertised control actions. No password entry, file uploads, downloads, arbitrary JavaScript, imported personal browser profiles or cookie export. A named session uses only its previously configured agent-owned profile and site origin.',
                                  'Completion requires exact case-sensitive rendered output, not editor content, an input/select value or a control label. Only one tab, bounded open shadow roots and same-origin frames are observed; closed roots and cross-origin frames are unavailable. Dropdowns with ambiguous values, multiple selection, excessive options or oversized option labels cannot be selected. Rich-text type replaces the whole editable text using a browser editing operation; it does not preserve formatting. Readonly editors, embedded widgets/media, oversized documents, mixed or unspecified toggle states cannot be edited automatically. ARIA controls use actual application click handlers; declaring a role alone does not prove an effect.']}
        record=director.runner(desktop,director.cloud,director.approve,director.emit,director.directory,director.cancel).run(
            task,blueprint,max_steps=16,previous_workflows=previous,required_result_text=request['expected_result'],result_control_id='page:output')
        result['steps'].append({'tool':'browser','version':version,'record':record})
        if record['outcome']!='result_observed':
            result['outcome']=record['outcome'];return _save(director,result)
        proof=desktop.observe();guard()
        if not result_matches(proof,request['expected_result'],result_control_id='page:output'):
            raise RuntimeError('Browser output changed before independent checkpoint verification.')
        from .file_tools import safe_path
        directory=safe_path((director.directory/'browser-evidence').absolute());directory.mkdir(parents=True,exist_ok=True)
        path=directory/(uuid.uuid4().hex+'.json');raw=json.dumps(proof,ensure_ascii=False,sort_keys=True).encode()
        with path.open('xb') as stream:stream.write(raw)
        evidence={'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'url':proof['url'],'expected_result':request['expected_result']}
        step={'tool':'browser','record':record,'proof':evidence}
        if checkpoint:checkpoint.verified(request['expected_result'],step)
        if record.get('replay_recipe'):
            director.catalog.set_setting(key,{'version':version,'record':{**record,'recipe':record['replay_recipe']}})
        result.update(outcome='steps_verified',steps=[step],verified_results=[request['expected_result']])
        director.emit('Verified exact browser output; recorded evidence and guarded workflow.')
    except Exception as error:
        result.update(outcome='cancelled' if director.cancel.is_set() else 'verification_failed',error=str(error)[:1500])
        director.emit('Browser task stopped: '+str(error)[:500])
    finally:
        if browser:
            try:browser.close()
            except Exception as error:
                result['cleanup_warning']=str(error)[:300]
                director.emit('Browser cleanup needs attention: '+str(error)[:300])
    return _save(director,result)
