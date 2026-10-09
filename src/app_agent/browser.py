"""Private Chromium session using fixed DOM tools and our own loopback transport."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from .browser_protocol import DevTools
from .browser_scripts import OBSERVE,ACT
from .research import public_https


def browser_request(task):
    quote=r'"([^"\r\n]+)"'
    named=re.fullmatch(r'use\s+browser\s+session\s+'+quote+r'\s+at\s+'+quote+r'\s+to\s+(.+?)\s+and\s+verify\s+exactly:\s*'+quote+r'\s*[.]?',task.strip(),re.I|re.S)
    match=named or re.fullmatch(r'(?:open\s+'+quote+r'\s+in\s+(?:a\s+)?browser\s+and|use\s+(?:the\s+)?browser\s+at\s+'+quote+r'\s+to)\s+(.+?)\s+and\s+verify\s+exactly:\s*'+quote+r'\s*[.]?',task.strip(),re.I|re.S)
    if not match:return None
    first,second,instruction,expected=match.groups();url=second if named else first or second
    if len(url)>4096 or not instruction.strip() or len(instruction)>4000 or not expected.strip() or len(expected)>2000:return None
    request={'url':url,'task':instruction.strip(),'expected_result':expected}
    if named:
        from .browser_sessions import session_name
        request['session']=session_name(first)
    return request


def executable():
    if sys.platform=='win32':
        for root in (os.getenv('PROGRAMFILES(X86)'),os.getenv('PROGRAMFILES'),os.getenv('LOCALAPPDATA')):
            if root:
                for suffix in ('Microsoft/Edge/Application/msedge.exe','Google/Chrome/Application/chrome.exe'):
                    path=Path(root)/suffix
                    if path.is_file():return str(path)
    else:
        for name in ('chromium','chromium-browser','google-chrome'):
            path=shutil.which(name)
            if path:return path
    raise RuntimeError('A supported Edge or Chrome browser executable was not found.')


def read_endpoint(path,process,guard,timeout=15):
    """Wait for a complete owned endpoint, including Windows sharing delays."""
    deadline=time.monotonic()+timeout
    while True:
        guard()
        if process.poll() is not None:raise RuntimeError('Managed browser exited before startup; inspect the installed browser and sandbox configuration.')
        try:
            with path.open('rb') as stream:data=stream.read(4097)
            lines=data.decode('ascii').splitlines()
            if len(data)<=4096 and len(lines)==2 and re.fullmatch(r'[0-9]{1,5}',lines[0]) and re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]{1,128}',lines[1]):
                port=int(lines[0])
                if 1<=port<=65535:return port,lines[1]
        except (FileNotFoundError,PermissionError,UnicodeError):pass
        if time.monotonic()>deadline:raise TimeoutError('Managed browser startup timed out waiting for its complete endpoint.')
        time.sleep(.05)


class Browser:
    def __init__(self,guard=lambda:None,*,headless=False,check_url=public_https,fixture_no_sandbox=False,session=None,manual_login=False):
        if fixture_no_sandbox and (sys.platform=='win32' or check_url is public_https):
            raise ValueError('Disabling the browser sandbox is permitted only for trusted Linux test fixtures.')
        self.guard=guard;self.check_url=check_url;self.headless=headless;self.fixture_no_sandbox=fixture_no_sandbox
        self.transport=None;self.process=None;self.profile=None;self.target=None;self.controls={};self.blocked=0
        self.session,self.manual_login=session,manual_login

    def start(self,url):
        self.check_url(url);self.guard()
        if self.session:self.session.check_url(url)
        binary=executable()
        proxy=os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
        if proxy:
            parsed=urlsplit(proxy)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Browser proxy configuration is unsupported.')
        self.profile=tempfile.TemporaryDirectory(prefix='app-agent-browser-')
        root=Path(self.profile.name)
        # Windows browser children can retain inherited log handles after the
        # parent exits. Never tie those handles to a disposable profile folder.
        self.log=(root/'browser.log').open('wb') if sys.platform!='win32' else None
        profile=self.session.profile if self.session else root/'profile'
        args=[binary,'--user-data-dir='+str(profile),'--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-background-mode','--window-size=1280,720','about:blank']
        if self.headless:args.insert(1,'--headless=new')
        if self.fixture_no_sandbox:args.insert(1,'--no-sandbox')
        if proxy:
            args.insert(1,'--proxy-server='+proxy)
            if self.check_url is public_https:args.insert(1,'--proxy-bypass-list=<-loopback>')
        env=os.environ.copy()
        if sys.platform!='win32':env['XDG_CONFIG_HOME']=str(root);env['XDG_CACHE_HOME']=str(root)
        try:
            if self.session:
                self.session.acquire()
                # A retained profile may have a port file from an earlier process.
                from .file_tools import safe_path
                safe_path(profile/'DevToolsActivePort').unlink(missing_ok=True)
            output=self.log if self.log is not None else subprocess.DEVNULL
            self.process=subprocess.Popen(args,stdout=output,stderr=output,env=env)
            port,endpoint=read_endpoint(profile/'DevToolsActivePort',self.process,self.guard)
            self.transport=DevTools('ws://127.0.0.1:'+str(port)+endpoint,port,self.guard)
            self.info=self.transport.call('Browser.getVersion',browser=True)
            self.transport.call('Browser.setDownloadBehavior',{'behavior':'deny'},browser=True)
            self.target=self.transport.call('Target.createTarget',{'url':'about:blank'},browser=True)['targetId']
            self.transport.session=self.transport.call('Target.attachToTarget',{'targetId':self.target,'flatten':True},browser=True)['sessionId']
            self.transport.events=self.event
            self.transport.call('Target.setDiscoverTargets',{'discover':True},browser=True)
            self.transport.call('Page.enable');self.transport.call('Runtime.enable')
            self.transport.call('Fetch.enable',{'patterns':[{'urlPattern':'*','requestStage':'Request'}]})
            result=self.transport.call('Page.navigate',{'url':url})
            if result.get('errorText'):raise RuntimeError('Browser navigation failed: '+result['errorText'])
            self.identity=int(hashlib.sha256(self.target.encode()).hexdigest()[:12],16)
            self.wait_ready(initial=True)
            return self
        except BaseException:self.close();raise

    def event(self,event):
        if event['method']=='Fetch.requestPaused':
            params=event['params'];request=params['request'];allowed=True
            try:self.check_url(request['url'])
            except (ValueError,RuntimeError):allowed=False
            if allowed:self.transport.send('Fetch.continueRequest',{'requestId':params['requestId']},event.get('sessionId'))
            else:
                self.blocked+=1
                self.transport.send('Fetch.failRequest',{'requestId':params['requestId'],'errorReason':'BlockedByClient'},event.get('sessionId'))
        elif event['method']=='Target.targetCreated':
            target=event['params']['targetInfo']
            if not self.manual_login and target['type']=='page' and target['targetId']!=self.target:self.transport.send('Target.closeTarget',{'targetId':target['targetId']})

    def evaluate(self,expression):
        frame=self.transport.call('Page.getFrameTree')['frameTree']['frame']['id']
        context=self.transport.call('Page.createIsolatedWorld',{'frameId':frame,'worldName':'AppAgent-reviewed-dom-tools'})['executionContextId']
        value=self.transport.call('Runtime.evaluate',{'expression':expression,'contextId':context,'returnByValue':True,'awaitPromise':False})
        if value.get('exceptionDetails'):raise RuntimeError('Reviewed browser DOM action failed: '+str(value['exceptionDetails'].get('text','Exception')))
        return value.get('result',{}).get('value')

    def wait_ready(self,initial=False):
        deadline=time.monotonic()+15
        while True:
            self.guard()
            try:
                state=self.evaluate('({ready:document.readyState,url:location.href})')
                if state['ready'] in ('interactive','complete') and (not initial or state['url']!='about:blank'):return
            except RuntimeError:pass
            if time.monotonic()>deadline:raise TimeoutError('Browser document did not become ready.')
            time.sleep(.05)

    def observe(self):
        if self.session:self.session.validate()
        deadline=time.monotonic()+2
        while True:
            self.guard()
            try:
                snapshot=self.evaluate(OBSERVE)
                break
            except RuntimeError:
                if time.monotonic()>=deadline:raise
                time.sleep(.05)
        self.check_url(snapshot['url'])
        if self.session:self.session.check_url(snapshot['url'])
        self.url=snapshot['url']
        self.controls={c['id']:c for c in snapshot['controls']}
        return {'window':'Managed browser page','window_handle':self.identity,'process_id':self.process.pid,
                'url':snapshot['url'],'page_title':snapshot['title'],'controls':snapshot['controls'],'coverage':snapshot.get('coverage',{})}

    def act(self,action):
        if self.session:self.session.validate();self.session.check_url(self.url)
        self.guard();control=self.controls.get(action.get('target'))
        if not control or control['password'] or action['kind'] not in control['actions']:raise ValueError('Browser action does not identify an available control.')
        if action['kind'] in ('type','select') and (not isinstance(action.get('text'),str) or len(action['text'])>2000):raise ValueError('Browser text entry or selection value is invalid.')
        if action['kind']=='select':
            options=[o for o in control.get('state',{}).get('options',[]) if o['value']==action['text']]
            if len(options)!=1 or not options[0]['enabled']:raise ValueError('Browser selection needs one enabled advertised option value.')
        if action['kind']=='toggle' and action.get('state') not in ('on','off'):raise ValueError('Browser checkbox needs an explicit state.')
        if control.get('href'):self.check_url(control['href'])
        if self.session and control.get('href'):self.session.check_url(control['href'])
        result=self.evaluate(ACT+'('+json.dumps({'control':control,'action':action,'url':self.url})+')')
        if result is not True:raise RuntimeError('Browser action did not confirm dispatch.')

    def close(self):
        if self.transport:
            try:
                self.transport.guard=lambda:None
                self.transport.call('Browser.close',browser=True,timeout=2)
            except Exception:pass
            finally:self.transport.close();self.transport=None
        if self.process and self.process.poll() is None:
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        if getattr(self,'log',None) is not None:self.log.close()
        if self.session and (not self.process or self.process.poll() is not None):self.session.close()
        if self.profile:
            deadline=time.monotonic()+3
            while True:
                try:self.profile.cleanup();self.profile=None;break
                except PermissionError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.05)
