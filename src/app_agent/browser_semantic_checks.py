"""Owned real-browser checks for rich editors and semantic application controls."""
import json
from pathlib import Path
from .browser import browser_request
from .browser_tasks import run_browser
from .catalog import Catalog
from .jobs import Jobs
from .job_runtime import run_next
from .runner import result_matches
from .task_director import TaskDirector

TEXT='Hello 世界\nSecond line'
SAVED_TEXT=TEXT.replace('\n',' | ')+' / on / review'
EXPECTED='Saved: '+SAVED_TEXT
FORM='''<div contenteditable="true" role="textbox" aria-label="Draft"><p>Old <b>formatted</b> draft</p></div>
<div role="switch" tabindex="0" aria-label="Confirmed" aria-checked="false">Confirm</div>
<div role="tablist"><div role="tab" tabindex="0" aria-label="Write" aria-selected="true">Write</div><div role="tab" tabindex="0" aria-label="Review" aria-selected="false">Review</div></div>
<div role="button" tabindex="0" aria-label="Pinned" aria-pressed="false">Pin</div>
<span id="choice-label">First choice</span><div role="radio" tabindex="0" aria-labelledby="choice-label" aria-checked="false">First</div>
<div role="menuitem" tabindex="0" aria-label="Preview">Preview</div>
<div role="option" tabindex="0" aria-label="Custom option" aria-selected="false">Option</div>
<div contenteditable="true" aria-readonly="true" aria-label="Locked draft">Locked</div>
<div contenteditable="true" aria-label="Embedded widget"><span contenteditable="false">Protected widget</span></div>
<div contenteditable="true" aria-label="Image document"><img alt="Image" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div>
<div role="textbox" aria-label="Declared only">Cannot edit me</div>
<div role="switch" aria-label="Unknown switch">Unknown</div><div role="checkbox" aria-label="Mixed checkbox" aria-checked="mixed">Mixed</div>
<div aria-disabled="true"><div role="tab" aria-label="Disabled tab" aria-selected="false">Disabled</div></div>
<button id="apply">Apply</button><output id="result" style="display:block"></output>'''
PAGE='''<!doctype html><meta charset="utf-8"><title>Semantic editor fixture</title><div id="host"></div><script>
const form=document.querySelector('#host').attachShadow({mode:'open'});form.innerHTML='''+json.dumps(FORM)+''';
window.effects={switches:0,pins:0,tabs:0,inputs:0,radios:0,menus:0,options:0};
const named=name=>name==='First choice'?form.querySelector('[aria-labelledby=choice-label]'):form.querySelector('[aria-label="'+name+'"]');
named('Draft').addEventListener('input',()=>{window.effects.inputs++;});
named('Confirmed').onclick=()=>{window.effects.switches++;const el=named('Confirmed');el.setAttribute('aria-checked',el.getAttribute('aria-checked')==='true'?'false':'true');};
named('Pinned').onclick=()=>{window.effects.pins++;const el=named('Pinned');el.setAttribute('aria-pressed',el.getAttribute('aria-pressed')==='true'?'false':'true');};
for(const name of ['Write','Review'])named(name).onclick=()=>{window.effects.tabs++;for(const n of ['Write','Review'])named(n).setAttribute('aria-selected',String(n===name));};
named('First choice').onclick=()=>{window.effects.radios++;named('First choice').setAttribute('aria-checked','true');};
named('Preview').onclick=()=>{window.effects.menus++;};
named('Custom option').onclick=()=>{window.effects.options++;named('Custom option').setAttribute('aria-selected','true');};
form.querySelector('#apply').onclick=async()=>{
 const r=await fetch('/commit',{method:'POST',body:JSON.stringify({text:named('Draft').innerText.replaceAll('\\n',' | ')+' / '+(named('Confirmed').getAttribute('aria-checked')==='true'?'on':'off')+' / '+(named('Review').getAttribute('aria-selected')==='true'?'review':'write')})});
 form.querySelector('#result').textContent=(await r.json()).result;
};</script>'''


class Planner:
    def request(self,**payload):
        observation=json.loads(payload['input'])['observation'];controls=observation['controls']
        if result_matches(observation,EXPECTED,result_control_id='page:output'):
            action={'kind':'finish','expected_text':EXPECTED,'reason':'Verify the independently rendered saved result.'}
        else:
            named={c['name']:c for c in controls}
            if named['Draft']['value']!=TEXT:target=named['Draft'];action={'kind':'type','text':TEXT}
            elif named['Confirmed']['state']['toggle']!='on':target=named['Confirmed'];action={'kind':'toggle','state':'on'}
            elif named['Review']['state']['selected']!='true':target=named['Review'];action={'kind':'click'}
            else:target=named['Apply'];action={'kind':'click'}
            action.update(target=target['id'],automation_id=target['automation_id'],target_name=target['name'],reason='Operate the owned semantic-control fixture.')
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(action)}]}]}


def checks(root,fixture,factory,cancel,emit):
    goal=f'Open "{fixture.url}semantic" in a browser and replace Draft, confirm and choose Review, then click Apply and verify exactly: "{EXPECTED}"'
    request=browser_request(goal)
    if not request:raise RuntimeError('Semantic fixture goal did not use the public browser grammar.')
    def guard():
        if cancel.is_set():raise RuntimeError('Semantic checks cancelled.')
    def opened():return factory(guard).start(fixture.url+'semantic')
    def controls(browser):return {c['name']:c for c in browser.observe()['controls']}
    def roundtrip():
        data=root/'semantic-task';catalog=Catalog(data);before=len(fixture.commits)
        try:
            result=run_browser(TaskDirector(catalog,Planner(),lambda *a:True,emit,data,cancel),goal,request,factory)
            if result['outcome']!='steps_verified' or fixture.commits[before:]!=[SAVED_TEXT]:raise RuntimeError('Rich-text/tab/switch HTTP task did not verify: '+str(result.get('error',result['outcome'])))
            proof=json.loads(Path(result['steps'][0]['proof']['path']).read_text(encoding='utf-8'))
            if not result_matches(proof,EXPECTED,result_control_id='page:output'):raise RuntimeError('Rich-text saved evidence failed exact verification.')
            return {'actual_submissions':1,'actions':result['steps'][0]['record']['actions_executed'],'unicode_multiline_input_and_exact_saved_output':True}
        finally:catalog.close()
    def literal_and_clear():
        browser=opened()
        try:
            text='<img src=x onerror=alert(1)> & 世界\nLiteral text';target=controls(browser)['Draft']
            browser.act({'kind':'type','target':target['id'],'text':text})
            current=controls(browser)['Draft']
            if current['value']!=text or browser.evaluate("document.querySelector('#host').shadowRoot.querySelector('[aria-label=Draft]').querySelectorAll('img').length")!=0:raise RuntimeError('Rich-text typing interpreted markup or lost literal text.')
            if browser.transport.call('Runtime.evaluate',{'expression':'window.effects.inputs','returnByValue':True})['result']['value']!=1:raise RuntimeError('Rich editor did not notify the application exactly once.')
            if result_matches(browser.observe(),text,result_control_id='page:output'):raise RuntimeError('Unsaved editable content certified a task result.')
            browser.act({'kind':'type','target':current['id'],'text':''})
            if controls(browser)['Draft']['value']!='':raise RuntimeError('Empty replacement failed to clear the rich editor.')
            return {'literal_markup_preserved':True,'application_input_event':True,'exact_empty_replacement':True,'unsaved_editor_not_proof':True}
        finally:browser.close()
    def protections():
        browser=opened()
        try:
            before=len(fixture.commits);original=browser.observe();named={c['name']:c for c in original['controls']}
            for name,kind in [('Locked draft','type'),('Embedded widget','type'),('Image document','type'),('Declared only','type'),('Unknown switch','toggle'),('Mixed checkbox','toggle'),('Disabled tab','click')]:
                if named[name]['actions']:raise RuntimeError('Unavailable semantic control advertised: '+name)
                try:browser.act({'kind':kind,'target':named[name]['id'],'text':'Do not edit','state':'on'})
                except ValueError:pass
                else:raise RuntimeError('Unavailable semantic control operated: '+name)
            browser.evaluate("const form=document.querySelector('#host').shadowRoot;const el=document.createElement('div');el.contentEditable='true';el.setAttribute('aria-label','Large draft');el.textContent='x'.repeat(2001);form.append(el)")
            if controls(browser)['Large draft']['actions']:raise RuntimeError('Oversized editor advertised destructive whole-document replacement.')
            if len(fixture.commits)!=before or browser.transport.call('Runtime.evaluate',{'expression':'window.effects.inputs','returnByValue':True})['result']['value']:raise RuntimeError('Protected controls produced effects.')
            return {'readonly_widget_media_and_oversized_editors_unavailable':True,'unknown_mixed_disabled_controls_unavailable':True}
        finally:browser.close()
    def idempotent():
        browser=opened()
        try:
            for name in ['Confirmed','Pinned']:
                for state in ['on','on','off','off']:
                    target=controls(browser)[name];browser.act({'kind':'toggle','target':target['id'],'state':state})
                    if controls(browser)[name]['state']['toggle']!=state:raise RuntimeError('Semantic toggle did not reach the requested state.')
            for name in ['First choice','Preview','Custom option']:
                target=controls(browser)[name];browser.act({'kind':'click','target':target['id']})
            effects=browser.transport.call('Runtime.evaluate',{'expression':'window.effects','returnByValue':True})['result']['value']
            if [effects[n] for n in ['switches','pins','radios','menus','options']]!=[2,2,1,1,1]:raise RuntimeError('Semantic actions did not use the application handlers idempotently.')
            return {'idempotent_switch_and_toggle_button':True,'radio_menu_and_option_handlers_executed':True}
        finally:browser.close()
    def stale():
        browser=opened();prefix="document.querySelector('#host').shadowRoot.querySelector"
        try:
            for name,mutation,action in [
                ('Confirmed',prefix+"('[aria-label=Confirmed]').setAttribute('aria-checked','true')",{'kind':'toggle','state':'on'}),
                ('Review',prefix+"('[aria-label=Review]').setAttribute('aria-selected','true')",{'kind':'click'}),
                ('Draft',prefix+"('[aria-label=Draft]').innerHTML='<p>Old <i>formatted</i> draft</p>'",{'kind':'type','text':'Do not replace'}),
                ('Draft',prefix+"('[aria-label=Draft]').onfocus=()=>{document.querySelector('#host').shadowRoot.querySelector('[aria-label=Draft]').setAttribute('aria-readonly','true')}",{'kind':'type','text':'Do not replace'})]:
                target=controls(browser)[name];browser.evaluate(mutation)
                try:browser.act({**action,'target':target['id']})
                except RuntimeError:pass
                else:raise RuntimeError('Stale semantic action accepted: '+name)
            effects=browser.transport.call('Runtime.evaluate',{'expression':'window.effects','returnByValue':True})['result']['value']
            if effects['inputs'] or effects['switches'] or effects['tabs']:raise RuntimeError('Changed semantic controls produced an agent effect.')
            return {'changed_toggle_tab_and_markup_rejected':True,'focus_time_editability_change_rejected':True}
        finally:browser.close()
    def replay():
        data=root/'semantic-replay';before=len(fixture.commits)
        class Director(TaskDirector):
            def run(self,task,use_vision=False):return run_browser(self,task,request,factory)
        class NoProvider:
            def request(self,**payload):raise RuntimeError('Verified rich-text workflow contacted the provider.')
        for planner in [Planner(),NoProvider()]:
            jobs=Jobs(data)
            try:identity=jobs.submit(goal,autonomous=True)
            finally:jobs.close()
            result=run_next(data,planner,lambda *a:True,emit,cancel,director=Director)
            if result['id']!=identity or result['status']!='completed':raise RuntimeError('Queued semantic workflow failed: '+str(result['detail']))
        if fixture.commits[before:]!=[SAVED_TEXT]*2 or result['result']['steps'][0]['record']['execution_mode']!='local_replay':raise RuntimeError('Rich-text workflow did not replay exactly without provider calls.')
        return {'actual_submissions':2,'replay_provider_calls':0,'rich_markup_and_aria_guards_rechecked':True}
    return [('Rich-text switch and tab workflow verifies actual HTTP output',roundtrip),
            ('Rich editor preserves literal Unicode text and clear operations',literal_and_clear),
            ('Readonly complex and oversized editors and ambiguous states are protected',protections),
            ('Semantic toggles are idempotent and use application handlers',idempotent),
            ('Changed semantic state markup and focus reject stale actions',stale),
            ('Queued rich-text workflow replays without provider calls',replay)]
