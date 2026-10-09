"""OS-owned local process locks; termination releases ownership automatically."""
import hashlib
import os
import threading
from pathlib import Path

_HELD=set()
_LOCAL=threading.RLock()


class SessionLock:
    def __init__(self,directory,name='worker'):
        self.directory=Path(directory);self.name=name;self.handle=None;self.owned=False
        self.directory.mkdir(parents=True,exist_ok=True)
        self.identity=(str(self.directory.resolve()).casefold() if os.name=='nt' else str(self.directory.resolve()),name)
        self.registered=False

    def acquire(self):
        with _LOCAL:
            if self.owned:return True
            if self.identity in _HELD:return False
            _HELD.add(self.identity);self.registered=True
            try:return self._acquire()
            except BaseException:self.close();raise

    def _acquire(self):
        if self.owned:return True
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
            kernel.ReleaseMutex.argtypes=[wintypes.HANDLE];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            identity=hashlib.sha256(str(self.directory.resolve()).casefold().encode()).hexdigest()
            self.handle=kernel.CreateMutexW(None,False,'Local\\AppAgent-'+self.name+'-'+identity);self.kernel=kernel
            if not self.handle:raise OSError('Cannot create the local agent process lock.')
            result=kernel.WaitForSingleObject(self.handle,0)
            if result==0xFFFFFFFF:raise OSError('Cannot inspect the local agent process lock.')
            self.owned=result in (0,0x80)
        else:
            import fcntl
            self.handle=(self.directory/(self.name+'.lock')).open('a+b')
            try:fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB);self.owned=True
            except BlockingIOError:self.owned=False
        if not self.owned:self.close()
        return self.owned

    def close(self):
        with _LOCAL:
            if self.handle is not None:
                if os.name=='nt':
                    if self.owned:self.kernel.ReleaseMutex(self.handle)
                    self.kernel.CloseHandle(self.handle)
                else:self.handle.close()
            if self.registered:_HELD.discard(self.identity)
            self.handle=None;self.owned=False;self.registered=False

    def __enter__(self):
        if not self.acquire():raise RuntimeError('This App Agent '+self.name+' is already running for this data folder.')
        return self

    def __exit__(self,*args):self.close()


def ui_open(directory):
    lock=SessionLock(directory,'ui')
    try:return not lock.acquire()
    finally:lock.close()
