"""Owned browser profiles; cookies stay with Chromium, never enter agent records."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
from urllib.parse import urlsplit
from .file_tools import safe_path
from .research import public_https
from .session_lock import SessionLock


def session_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}',value):
        raise ValueError('Browser session name needs 1–32 letters, numbers, underscores or hyphens.')
    return value.casefold()


def origin(url):
    if not isinstance(url,str) or len(url)>4096:raise ValueError('Invalid browser session URL.')
    value=urlsplit(url)
    if value.scheme not in ('https','http') or not value.hostname or value.username or value.password:raise ValueError('Invalid browser session URL.')
    host=value.hostname.casefold().rstrip('.')
    if ':' not in host:host=host.encode('idna').decode('ascii')
    if ':' in host:host='['+host+']'
    port=value.port
    return value.scheme+'://'+host+(':'+str(port) if port and port!={'http':80,'https':443}[value.scheme] else '')


def _write(path,value):
    temp=path.parent/(uuid.uuid4().hex+'.tmp')
    try:
        descriptor=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)


class BrowserSessions:
    def __init__(self,directory,check_url=public_https):
        self.root=safe_path((Path(directory)/'browser-sessions').absolute())
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700);self.check_url=check_url
    def folder(self,name):
        return safe_path(self.root/('session-'+hashlib.sha256(session_name(name).encode()).hexdigest()[:24]))
    def _read(self,name):
        name=session_name(name);directory=self.folder(name);path=safe_path(directory/'session.json')
        if not path.is_file():raise RuntimeError('Browser session is not configured. Open Browser sessions and sign in once.')
        if path.stat().st_size>4096:raise ValueError('Invalid browser session metadata size.')
        try:value=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):raise ValueError('Browser session metadata is invalid.') from None
        if (not isinstance(value,dict) or set(value)!={'format','name','id','revision','origin','created_at'}
                or value['format']!=1 or value['name']!=name
                or not isinstance(value['origin'],str)
                or any(not isinstance(value[k],str) or not re.fullmatch(r'[0-9a-f]{32}',value[k]) for k in ('id','revision'))
                or not isinstance(value['created_at'],str) or len(value['created_at'])>40):
            raise ValueError('Browser session metadata is invalid.')
        # Reading local metadata must work offline. Network destinations are
        # validated by check_url before browser startup and each request.
        if origin(value['origin'])!=value['origin']:raise ValueError('Browser session origin is invalid.')
        marker=safe_path(directory/'profile'/'app-agent-profile-id')
        if not marker.is_file() or marker.stat().st_size!=32 or marker.read_text()!=value['id']:
            raise ValueError('Browser session profile identity changed; no account selected.')
        return value
    def create(self,name,url):
        name=session_name(name);self.check_url(url);bound=origin(url);directory=self.folder(name)
        with SessionLock(self.root,'registry'):
            if directory.exists():
                value=self._read(name)
                if value['origin']!=bound:raise ValueError('Session name is already bound to another site. Use a different name.')
                return value
            directory.mkdir(mode=0o700,exist_ok=False);profile=directory/'profile';profile.mkdir(mode=0o700)
            value={'format':1,'name':name,'id':uuid.uuid4().hex,'revision':uuid.uuid4().hex,'origin':bound,'created_at':datetime.now(timezone.utc).isoformat()}
            (profile/'app-agent-profile-id').write_text(value['id'])
            _write(directory/'session.json',value)
            return value
    def get(self,name,url=None):
        value=self._read(name)
        session=BrowserSession(self,value)
        if url is not None:session.check_url(url)
        return session
    def list(self):
        result=[]
        for path in sorted(self.root.glob('session-*')):
            file=safe_path(path/'session.json')
            if not file.is_file() or file.stat().st_size>4096:raise ValueError('Browser session metadata is invalid.')
            try:name=json.loads(file.read_text(encoding='utf-8'))['name']
            except (ValueError,KeyError,TypeError):raise ValueError('Browser session metadata is invalid.') from None
            value=self._read(name)
            if self.folder(name)!=path:raise ValueError('Browser session registry identity changed.')
            result.append({key:value[key] for key in ('name','origin','created_at')})
        return result
    def rotate(self,name):
        # A manual sign-in can switch accounts. Invalidate prior learned recipes.
        with SessionLock(self.root,'registry'):
            session=self.get(name)
            try:
                session.acquire();value={**session.metadata,'revision':uuid.uuid4().hex}
                _write(session.directory/'session.json',value)
                return {key:value[key] for key in ('name','origin','revision')}
            finally:session.close()
    def remove(self,name):
        with SessionLock(self.root,'registry'):
            session=self.get(name)
            try:
                session.acquire();shutil.rmtree(session.directory)
            finally:session.close()


class BrowserSession:
    def __init__(self,store,metadata):
        self.store,self.metadata=store,metadata
        self.directory=store.folder(metadata['name']);self.profile=safe_path(self.directory/'profile')
        self.lock=SessionLock(self.directory,'browser');self.owned=False
    def validate(self):
        if self.store._read(self.metadata['name'])!=self.metadata:raise RuntimeError('Browser session changed; account task stopped.')
    def check_url(self,url):
        self.store.check_url(url)
        if origin(url)!=self.metadata['origin']:raise ValueError('Browser session task must stay on its configured site origin.')
    def acquire(self):
        self.validate()
        if not self.lock.acquire():raise RuntimeError('Browser session is already in use; wait for its browser to close.')
        self.owned=True
        try:self.validate()
        except BaseException:self.close();raise
    def close(self):self.lock.close();self.owned=False


def login_session(directory,name,url,emit=print,cancel=None):
    """User signs in directly; no model, password reading or cookie export."""
    import threading
    from .browser import Browser
    cancel=cancel or threading.Event();store=BrowserSessions(directory);store.create(name,url)
    session=store.get(name,url)
    def guard():
        if cancel.is_set():raise RuntimeError('Browser sign-in stopped.')
    browser=Browser(guard,session=session,manual_login=True)
    emit('Sign in directly in the browser, then close its window. Account data stays in this agent-owned profile. No provider call is made.')
    try:
        browser.start(url)
        while browser.process.poll() is None and not cancel.is_set():
            try:browser.transport.call('Browser.getVersion',browser=True,timeout=2)
            except (ConnectionError,OSError):break
            cancel.wait(.2)
    finally:browser.close()
    if cancel.is_set():raise RuntimeError('Browser sign-in stopped; no authentication claim was saved.')
    store.rotate(name)
    emit('Browser session retained. Authentication will be checked by the actual site during later tasks.')
    return {'name':session.metadata['name'],'origin':session.metadata['origin'],'profile_retained':True,'authentication':'not_assumed'}
