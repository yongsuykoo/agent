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


class Fixture:
    def __init__(self):
        self.commits=[];self.auth_submissions=[];self.auth_requests=0;self.token=uuid.uuid4().hex;owner=self
        class Handler(BaseHTTPRequestHandler):
            def signed_in(self):return ('fixture_session='+owner.token) in self.headers.get('Cookie','').split('; ')
            def do_GET(self):
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://127.0.0.1:1/private');self.end_headers();return
                body='<h1>Navigation complete</h1>' if self.path=='/next' else PAGE
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
            ('Removing an owned profile clears its account session',remove_session)]
    emit('Private browser fixtures only; deterministic local planner, no provider calls or existing accounts.')
    try:return run_checks(checks,root/'report.json',cancel,emit,scope='Thirteen real Chromium fixture checks including retained account authentication; deterministic planner, no external accounts or all-app certification. Linux fixture sandbox disabled: '+str(fixture_no_sandbox))
    finally:fixture.close()
