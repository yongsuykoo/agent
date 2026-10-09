"""Real Chromium execution checks using our own web fixture and local planner."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit
from .browser import Browser,browser_request
from .browser_tasks import run_browser
from .catalog import Catalog
from .jobs import Jobs
from .job_runtime import run_next
from .runner import result_matches
from .self_test import run_checks
from .task_director import TaskDirector

PAGE='''<!doctype html><meta charset="utf-8"><title>Disposable browser check</title>
<label>Message<input id="message"></label><label>Confirmed<input id="confirm" type="checkbox"></label>
<input aria-label="Password" type="password" value="never-include-this-value">
<input aria-label="Read only" readonly value="unchanged"><input aria-label="Upload" type="file">
<input aria-label="Hidden" style="display:none"><button id="apply">Apply</button>
<div style="opacity:0"><output>Invisible result must not verify</output></div>
<output id="result" style="display:block"></output>
<a href="/next">Continue</a>
<script>document.querySelector('#apply').onclick=async()=>{
 if(!document.querySelector('#confirm').checked)return;
 const r=await fetch('/commit',{method:'POST',body:JSON.stringify({text:document.querySelector('#message').value})});
 document.querySelector('#result').textContent=(await r.json()).result;
};</script>'''

NESTED_FORM='''<label>Message<input id="message"></label><label>Confirmed<input id="confirm" type="checkbox"></label>
<select id="delivery" aria-label="Delivery"><option value="standard">Standard</option><option value="express">Express 世界</option><option value="disabled" disabled>Unavailable</option><optgroup label="Blocked group" disabled><option value="blocked">Blocked</option></optgroup></select>
<select aria-label="Ambiguous"><option value="same">One</option><option value="same">Two</option></select>
<select aria-label="Multiple" multiple><option value="a">A</option></select>
<select aria-label="Too many">'''+''.join('<option value="'+str(i)+'">Option '+str(i)+'</option>' for i in range(81))+'''</select>
<input type="password" aria-label="Nested password" value="nested-password-must-stay-private">
<button id="apply">Apply</button><output id="result" style="display:block"></output>'''

NESTED_PAGE='''<!doctype html><meta charset="utf-8"><title>Nested interface check</title>
<div id="host"></div><div id="hidden" style="opacity:0"></div><div id="inert" inert></div><div id="closed"></div>
<iframe sandbox src="/foreign" title="Unavailable isolated frame"></iframe>
<script>
document.querySelector('#host').attachShadow({mode:'open'}).innerHTML='<iframe id="embedded" src="/frame-form" style="width:900px;height:450px" title="Embedded form"></iframe>';
document.querySelector('#hidden').attachShadow({mode:'open'}).innerHTML='<input aria-label="Hidden nested field"><output>Hidden nested proof</output>';
document.querySelector('#inert').attachShadow({mode:'open'}).innerHTML='<button>Inert component button</button>';
document.querySelector('#closed').attachShadow({mode:'closed'}).innerHTML='<input aria-label="Closed component field">';
</script>'''

FRAME_PAGE='''<!doctype html><meta charset="utf-8"><title>Embedded form</title><div id="component"></div><script>
const form=document.querySelector('#component').attachShadow({mode:'open'});
form.innerHTML='''+json.dumps(NESTED_FORM)+''';
form.querySelector('#apply').onclick=async()=>{
 if(!form.querySelector('#confirm').checked)return;
 const r=await fetch('/commit',{method:'POST',body:JSON.stringify({text:form.querySelector('#message').value+' / '+form.querySelector('#delivery').value})});
 form.querySelector('#result').textContent=(await r.json()).result;
};</script>'''


class Fixture:
    def __init__(self):
        self.commits=[];self.auth_submissions=[];self.auth_requests=0;self.token=uuid.uuid4().hex;owner=self
        class Handler(BaseHTTPRequestHandler):
            def signed_in(self):return ('fixture_session='+owner.token) in self.headers.get('Cookie','').split('; ')
            def do_GET(self):
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://127.0.0.1:1/private');self.end_headers();return
                body='<h1>Navigation complete</h1>' if self.path=='/next' else PAGE
                if self.path=='/nested':body=NESTED_PAGE
                elif self.path in ('/frame-form','/frame-changed'):
                    time.sleep(.15)  # Exercise real embedded-navigation readiness.
                    body=FRAME_PAGE
                elif self.path=='/foreign':body='<input aria-label="Foreign field"><output>Foreign proof</output>'
                if self.path=='/account':
                    if self.signed_in():owner.auth_requests+=1;body=PAGE+'<p>Account: fixture member</p>'
                    else:body='<h1>Sign in required</h1>'
                self.send_response(200)
                if self.path=='/sign-in':self.send_header('Set-Cookie','fixture_session='+owner.token+'; Path=/; Max-Age=3600; HttpOnly; SameSite=Lax')
                self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body.encode())
            def do_POST(self):
                count=int(self.headers.get('Content-Length','0'))
                if self.path!='/commit' or not 0<=count<=4096:self.send_error(400);return
                value=json.loads(self.rfile.read(count))['text'];owner.commits.append(value)
                if self.signed_in():owner.auth_submissions.append(value)
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'result':'Saved: '+value}).encode())
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/'
    def check_url(self,url):
        value=urlsplit(url)
        if value.scheme!='http' or value.hostname!='127.0.0.1' or value.port!=self.server.server_port or value.username or value.password:
            raise ValueError('Browser smoke may reach only its own disposable fixture.')
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


class FixturePlanner:
    """Reviewed deterministic fixture actions; never represents a model test."""
    def __init__(self,text='Hello 世界',premature=False):self.text=text;self.calls=0;self.premature=premature
    def request(self,**payload):
        self.calls+=1;obs=json.loads(payload['input'])['observation'];controls=obs['controls'];expected='Saved: '+self.text
        if self.premature or result_matches(obs,expected,result_control_id='page:output'):
            action={'kind':'finish','expected_text':expected,'reason':'Verify rendered output.'}
        else:
            editor=next(c for c in controls if c['name']=='Message');checkbox=next(c for c in controls if c['name']=='Confirmed')
            if editor['value']!=self.text:target=editor;action={'kind':'type','text':self.text}
            elif checkbox['state']['toggle']!='on':target=checkbox;action={'kind':'toggle','state':'on'}
            else:target=next(c for c in controls if c['name']=='Apply');action={'kind':'click'}
            action.update(target=target['id'],automation_id=target['automation_id'],target_name=target['name'],reason='Operate disposable fixture.')
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(action)}]}]}


class NestedPlanner(FixturePlanner):
    def request(self,**payload):
        self.calls+=1;obs=json.loads(payload['input'])['observation'];expected='Saved: '+self.text+' / express'
        if result_matches(obs,expected,result_control_id='page:output'):
            action={'kind':'finish','expected_text':expected,'reason':'Verify the actual nested rendered output.'}
        else:
            controls=obs['controls'];editor=next(c for c in controls if c['name']=='Message')
            dropdown=next(c for c in controls if c['name']=='Delivery');checkbox=next(c for c in controls if c['name']=='Confirmed')
            if editor['value']!=self.text:target=editor;action={'kind':'type','text':self.text}
            elif dropdown['value']!='express':target=dropdown;action={'kind':'select','text':'express'}
            elif checkbox['state']['toggle']!='on':target=checkbox;action={'kind':'toggle','state':'on'}
            else:target=next(c for c in controls if c['name']=='Apply');action={'kind':'click'}
            action.update(target=target['id'],automation_id=target['automation_id'],target_name=target['name'],reason='Operate only the owned embedded fixture.')
        return {'output':[{'content':[{'type':'output_text','text':json.dumps(action)}]}]}


def browser_smoke(directory,emit=print,cancel=None,*,fixture_no_sandbox=False):
    if fixture_no_sandbox and sys.platform=='win32':raise ValueError('Windows browser checks keep the sandbox enabled.')
    cancel=cancel or threading.Event();root=Path(directory)/('browser-tests-'+uuid.uuid4().hex);root.mkdir(parents=True,exist_ok=False)
    fixture=Fixture()
    def guard():
        if cancel.is_set():raise RuntimeError('Browser checks cancelled.')
    def factory(guard,**options):return Browser(guard,headless=True,check_url=fixture.check_url,fixture_no_sandbox=fixture_no_sandbox,**options)
    task=f'Open "{fixture.url}" in a browser and enter Message, set Confirmed on, and click Apply and verify exactly: "Saved: Hello 世界"'
    def direct(planner,checkpoint=None,adapter=factory):
        data=root/uuid.uuid4().hex;catalog=Catalog(data)
        try:return run_browser(TaskDirector(catalog,planner,lambda *args:True,emit,data,cancel,checkpoint=checkpoint),task,browser_request(task),adapter)
        finally:catalog.close()
    def roundtrip():
        before=len(fixture.commits);result=direct(FixturePlanner())
        if result['outcome']!='steps_verified' or fixture.commits[before:]!=['Hello 世界']:raise RuntimeError('Browser did not verify one real Unicode submission.')
        return {'actual_submissions':1,'actions':result['steps'][0]['record']['actions_executed'],'provider_calls':0}
    def privacy():
        browser=factory(guard)
        try:
            browser.start(fixture.url);snapshot=browser.observe();controls={c['name']:c for c in snapshot['controls']}
            if controls['Password']['value'] or controls['Password']['actions'] or 'never-include-this-value' in json.dumps(snapshot):raise RuntimeError('Password value exposed.')
            if controls['Read only']['actions'] or controls['Upload']['actions'] or 'Hidden' in controls:raise RuntimeError('Unavailable controls advertised.')
            if 'Invisible result must not verify' in controls:raise RuntimeError('Invisible DOM text was accepted as rendered output.')
            value=browser.transport.call('Runtime.evaluate',{'expression':'typeof window.__appAgent','returnByValue':True})
            if value['result']['value']!='undefined':raise RuntimeError('Controller leaked into page world.')
            return {'unavailable_controls_protected':True,'isolated_world':True}
        finally:browser.close()
    def false_completion():
        before=len(fixture.commits);result=direct(FixturePlanner(premature=True))
        if result['outcome']!='verification_failed' or len(fixture.commits)!=before:raise RuntimeError('Premature completion accepted.')
        return {'completion_claim_rejected':True,'actual_submissions':0}
    def stale():
        browser=factory(guard)
        try:
            browser.start(fixture.url);snapshot=browser.observe();target=next(c for c in snapshot['controls'] if c['name']=='Message')
            browser.evaluate("document.querySelector('#message').outerHTML='<input id=message>'")
            try:browser.act({'kind':'type','target':target['id'],'text':'must not enter'})
            except RuntimeError:pass
            else:raise RuntimeError('Replaced control typed.')
            browser.observe();target=next(c for c in browser.controls.values() if c['name']=='Message')
            browser.evaluate("history.pushState({},'', '/changed')")
            try:browser.act({'kind':'type','target':target['id'],'text':'must not enter'})
            except RuntimeError:pass
            else:raise RuntimeError('Changed URL silently accepted.')
            return {'replaced_control_rejected':True,'changed_page_rejected':True}
        finally:browser.close()
    def navigation():
        browser=factory(guard)
        try:
            browser.start(fixture.url);snapshot=browser.observe();link=next(c for c in snapshot['controls'] if c['name']=='Continue')
            browser.act({'kind':'click','target':link['id']});deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                snapshot=browser.observe()
                if result_matches(snapshot,'Navigation complete',result_control_id='page:output'):
                    return {'actual_page_navigation':True,'new_output_verified':True}
                time.sleep(.05)
            raise RuntimeError('Browser did not navigate and verify the linked page.')
        finally:browser.close()
    def redirected_scope():
        browser=factory(guard)
        try:
            try:browser.start(fixture.url+'redirect')
            except (RuntimeError,ValueError):pass
            else:raise RuntimeError('Disallowed redirect was accepted.')
            if not browser.blocked:raise RuntimeError('Redirect scope was not checked before dispatch.')
            return {'redirect_outside_owned_fixture_blocked':True}
        finally:browser.close()
    def replay_check():
        data=root/'queue-data';before=len(fixture.commits)
        class Director(TaskDirector):
            def run(self,goal,use_vision=False):return run_browser(self,goal,browser_request(goal),factory)
        class NoProvider:
            def request(self,**kwargs):raise RuntimeError('Replay requested a provider.')
        for planner in (FixturePlanner(),NoProvider()):
            jobs=Jobs(data)
            try:identity=jobs.submit(task,autonomous=True)
            finally:jobs.close()
            result=run_next(data,planner,lambda *args:True,emit,cancel,director=Director)
            if result['id']!=identity or result['status']!='completed':raise RuntimeError('Queued browser goal failed: '+str(result['detail']))
        if fixture.commits[before:]!=['Hello 世界','Hello 世界'] or result['result']['steps'][0]['record']['execution_mode']!='local_replay':raise RuntimeError('Browser replay produced incorrect effects.')
        return {'actual_submissions':2,'replay_provider_calls':0}
    def uncertain():
        jobs=Jobs(root/'uncertain-data');identity=jobs.submit(task,autonomous=True);checkpoint=jobs.claim(identity)
        class InterruptedBrowser(Browser):
            def act(self,action):
                super().act(action)
                if action['kind']=='click':
                    deadline=time.monotonic()+3
                    while not result_matches(self.observe(),'Saved: Hello 世界',result_control_id='page:output') and time.monotonic()<deadline:time.sleep(.05)
                    raise ConnectionError('Injected interruption after real submission.')
        def interrupted(guard):return InterruptedBrowser(guard,headless=True,check_url=fixture.check_url,fixture_no_sandbox=fixture_no_sandbox)
        before=len(fixture.commits)
        try:
            result=direct(FixturePlanner(),checkpoint,interrupted);state=jobs.settle(checkpoint,result)
            if state['status']!='needs_review' or fixture.commits[before:]!=['Hello 世界'] or jobs.claim(identity) is not None:raise RuntimeError('Uncertain effect replayed.')
            return {'actual_submissions':1,'status':'needs_review','automatic_reclicks':0}
        finally:jobs.close()
    from .browser_sessions import BrowserSessions
    sessions=BrowserSessions(root/'account-data',fixture.check_url)
    def sign_in(name):
        sessions.create(name,fixture.url)
        browser=factory(guard,session=sessions.get(name,fixture.url))
        try:browser.start(fixture.url+'sign-in')
        finally:browser.close()
    def persistent_auth():
        sign_in('work');browser=factory(guard,session=sessions.get('work'))
        try:
            browser.start(fixture.url+'account')
            if not result_matches(browser.observe(),'Account: fixture member',result_control_id='page:output'):raise RuntimeError('Authentication did not survive browser restart.')
            return {'retained_account_observed':True,'cookies_read_by_agent':False}
        finally:browser.close()
    def separated_accounts():
        sessions.create('separate',fixture.url);browser=factory(guard,session=sessions.get('separate'))
        try:
            browser.start(fixture.url+'account')
            if not result_matches(browser.observe(),'Sign in required',result_control_id='page:output'):raise RuntimeError('Other profile inherited authentication.')
            return {'separate_profile_does_not_inherit_account':True}
        finally:browser.close()
    def account_replay():
        sign_in('replay');before=len(fixture.auth_submissions)
        data=root/'account-data';goal=f'Use browser session "replay" at "{fixture.url}account" to enter Message, set Confirmed on, and click Apply and verify exactly: "Saved: Hello 世界"'
        class Director(TaskDirector):
            def run(self,task,use_vision=False):return run_browser(self,task,browser_request(task),factory,sessions)
        class NoProvider:
            def request(self,**kwargs):raise RuntimeError('Authenticated replay requested a provider.')
        for planner in (FixturePlanner(),NoProvider()):
            jobs=Jobs(data)
            try:identity=jobs.submit(goal,autonomous=True)
            finally:jobs.close()
            result=run_next(data,planner,lambda *args:True,emit,cancel,director=Director)
            if result['id']!=identity or result['status']!='completed':raise RuntimeError('Authenticated browser goal failed: '+str(result['detail']))
        if fixture.auth_submissions[before:]!=['Hello 世界','Hello 世界']:raise RuntimeError('Authenticated submissions were missing or repeated.')
        return {'authenticated_submissions':2,'replay_provider_calls':0}
    def busy_session():
        held=sessions.get('work');held.acquire()
        browser=factory(guard,session=sessions.get('work'))
        try:
            try:browser.start(fixture.url+'account')
            except RuntimeError as error:
                if 'already in use' not in str(error):raise
            else:raise RuntimeError('Busy account profile was opened twice.')
            if browser.process is not None:raise RuntimeError('Second browser was started for the locked profile.')
            return {'second_browser_blocked_before_start':True}
        finally:browser.close();held.close()
    def remove_session():
        sign_in('removable');old=sessions.get('removable').metadata['id'];sessions.remove('removable')
        sessions.create('removable',fixture.url);browser=factory(guard,session=sessions.get('removable'))
        try:
            browser.start(fixture.url+'account')
            if old==browser.session.metadata['id'] or not result_matches(browser.observe(),'Sign in required',result_control_id='page:output'):raise RuntimeError('Removed browser session retained authentication.')
            return {'owned_profile_removed':True,'recreated_profile_has_no_authentication':True}
        finally:browser.close()
    nested_goal=f'Open "{fixture.url}nested" in a browser and enter Message, choose Express delivery, confirm, and click Apply and verify exactly: "Saved: Hello 世界 / express"'
    def nested_browser():
        browser=factory(guard)
        try:
            browser.start(fixture.url+'nested');deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if any(c['name']=='Delivery' for c in browser.observe()['controls']):return browser
                cancel.wait(.05);guard()
            raise RuntimeError('Owned embedded fixture did not finish loading.')
        except BaseException:browser.close();raise
    def nested_roundtrip():
        before=len(fixture.commits);data=root/'nested-data';catalog=Catalog(data)
        try:
            result=run_browser(TaskDirector(catalog,NestedPlanner(),lambda *args:True,emit,data,cancel),nested_goal,browser_request(nested_goal),factory)
            if result['outcome']!='steps_verified' or fixture.commits[before:]!=['Hello 世界 / express']:raise RuntimeError('Nested form was not independently verified: '+str(result.get('error',result.get('outcome'))))
            proof=json.loads(Path(result['steps'][0]['proof']['path']).read_text())
            output=next(c for c in proof['controls'] if c['automation_id']=='page:output' and c['name']=='Saved: Hello 世界 / express')
            kinds=[p['kind'] for p in output['state']['context']['path']]
            if kinds!=['shadow','frame','shadow']:raise RuntimeError('Nested evidence does not identify its component/frame context.')
            return {'actual_submissions':1,'independently_verified_context':kinds,'actions':result['steps'][0]['record']['actions_executed']}
        finally:catalog.close()
    def dropdown_protection():
        browser=nested_browser()
        try:
            snapshot=browser.observe();controls={c['name']:c for c in snapshot['controls']}
            if controls['Multiple']['actions'] or controls['Too many']['actions']:raise RuntimeError('Unsupported dropdown advertised selection.')
            for name,value in [('Delivery','disabled'),('Delivery','blocked'),('Delivery','missing'),('Ambiguous','same')]:
                try:browser.act({'kind':'select','target':controls[name]['id'],'text':value})
                except ValueError:pass
                else:raise RuntimeError('Unavailable or ambiguous option was selected.')
            if browser.observe()['controls']!=snapshot['controls']:raise RuntimeError('Rejected selection changed the form.')
            return {'disabled_options_rejected':True,'ambiguous_values_rejected':True,'unsupported_selects_unavailable':True}
        finally:browser.close()
    def nested_privacy():
        browser=nested_browser()
        try:
            snapshot=browser.observe();controls={c['name']:c for c in snapshot['controls']}
            if 'nested-password-must-stay-private' in json.dumps(snapshot) or controls['Nested password']['actions']:raise RuntimeError('Nested password exposed.')
            if any(name in controls for name in ('Hidden nested field','Closed component field','Foreign field')):raise RuntimeError('Unavailable nested controls were exposed.')
            if controls['Inert component button']['actions'] or controls['Inert component button']['enabled']:raise RuntimeError('Inert shadow ancestor was ignored.')
            if result_matches(snapshot,'Hidden nested proof',result_control_id='page:output') or result_matches(snapshot,'Foreign proof',result_control_id='page:output'):raise RuntimeError('Unavailable nested output certified success.')
            if snapshot['coverage']['frames_unavailable']<1:raise RuntimeError('Unavailable embedded frame was not reported.')
            return {'password_protected':True,'hidden_inert_closed_and_cross_origin_controls_unavailable':True}
        finally:browser.close()
    def nested_stale():
        browser=nested_browser()
        target_js="document.querySelector('#host').shadowRoot.querySelector('iframe').contentDocument.querySelector('#component').shadowRoot"
        try:
            snapshot=browser.observe();target=next(c for c in snapshot['controls'] if c['name']=='Delivery')
            browser.evaluate(target_js+".querySelector('#delivery').options[1].label='Changed choice'")
            try:browser.act({'kind':'select','target':target['id'],'text':'express'})
            except RuntimeError:pass
            else:raise RuntimeError('Changed dropdown choices were accepted.')
            snapshot=browser.observe();target=next(c for c in snapshot['controls'] if c['name']=='Message')
            browser.evaluate("document.querySelector('#host').shadowRoot.querySelector('iframe').contentWindow.history.pushState({},'', '/frame-changed')")
            try:browser.act({'kind':'type','target':target['id'],'text':'must not enter'})
            except RuntimeError:pass
            else:raise RuntimeError('Changed embedded page URL was accepted.')
            snapshot=browser.observe();target=next(c for c in snapshot['controls'] if c['name']=='Message')
            browser.evaluate("document.querySelector('#host').shadowRoot.querySelector('iframe').remove()")
            try:browser.act({'kind':'type','target':target['id'],'text':'must not enter'})
            except RuntimeError:pass
            else:raise RuntimeError('Detached embedded document was operated.')
            return {'changed_options_rejected':True,'changed_frame_url_rejected':True,'detached_frame_rejected':True}
        finally:browser.close()
    def nested_replay():
        data=root/'nested-queue';before=len(fixture.commits)
        class Director(TaskDirector):
            def run(self,goal,use_vision=False):return run_browser(self,goal,browser_request(goal),factory)
        class NoProvider:
            def request(self,**kwargs):raise RuntimeError('Nested replay requested a provider.')
        for planner in (NestedPlanner(),NoProvider()):
            jobs=Jobs(data)
            try:identity=jobs.submit(nested_goal,autonomous=True)
            finally:jobs.close()
            result=run_next(data,planner,lambda *args:True,emit,cancel,director=Director)
            if result['id']!=identity or result['status']!='completed':raise RuntimeError('Nested queued goal failed: '+str(result['detail']))
        if fixture.commits[before:]!=['Hello 世界 / express','Hello 世界 / express'] or result['result']['steps'][0]['record']['execution_mode']!='local_replay':raise RuntimeError('Nested replay produced incorrect effects.')
        return {'actual_submissions':2,'replay_provider_calls':0,'context_guards_rechecked':True}
    def traversal_limits():
        browser=factory(guard)
        try:
            browser.start(fixture.url)
            browser.evaluate("document.body.replaceChildren(); for(let i=0;i<8200;i++){const el=document.createElement(i<250?'button':'span');el.textContent='Bounded '+i;document.body.append(el);} const late=document.createElement('output');late.textContent='Late proof';document.body.append(late)")
            snapshot=browser.observe()
            if not snapshot['coverage']['limited'] or snapshot['coverage']['elements']>8000 or len(snapshot['controls'])>402:raise RuntimeError('DOM observation exceeded its advertised limits.')
            if result_matches(snapshot,'Late proof',result_control_id='page:output') or browser.evaluate('globalThis.__appAgent.nodes.size')>400:raise RuntimeError('Out-of-scope output or unbounded retained node map.')
            return {'bounded_elements':snapshot['coverage']['elements'],'bounded_controls':len(snapshot['controls']),'uninspected_output_not_certified':True}
        finally:browser.close()
    checks=[('Real Unicode form submission and rendered output verification',roundtrip),
            ('Password/read-only/upload protection and isolated DOM world',privacy),
            ('Premature completion is rejected',false_completion),
            ('Replaced DOM controls and changed URLs reject stale actions',stale),
            ('Link navigation reaches and verifies the new page',navigation),
            ('Redirect outside the requested network scope is blocked',redirected_scope),
            ('Durable queue and verified replay need no second provider',replay_check),
            ('Interrupted real submission retains uncertain effect without replay',uncertain),
            ('Authentication survives an owned browser profile restart',persistent_auth),
            ('Separate browser profiles do not inherit account authentication',separated_accounts),
            ('Authenticated queued tasks replay without another provider',account_replay),
            ('An owned account profile cannot be opened concurrently',busy_session),
            ('Removing an owned profile clears its account session',remove_session),
            ('Nested shadow/frame form submission and dropdown selection',nested_roundtrip),
            ('Disabled ambiguous and unsupported dropdowns cannot be selected',dropdown_protection),
            ('Nested password and unavailable context protections',nested_privacy),
            ('Stale dropdown and embedded frame contexts reject actions',nested_stale),
            ('Nested queued workflows replay with zero provider calls',nested_replay),
            ('DOM traversal and retained node maps are bounded',traversal_limits)]
    emit('Private browser fixtures only; deterministic local planner, no provider calls or existing accounts.')
    try:return run_checks(checks,root/'report.json',cancel,emit,scope='Nineteen real Chromium fixture checks including owned sessions, dropdowns, open shadow roots and same-origin embedded forms; deterministic planner, no external accounts or all-app certification. Linux fixture sandbox disabled: '+str(fixture_no_sandbox))
    finally:fixture.close()
