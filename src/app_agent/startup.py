"""Explicit current-account login startup; no administrator or service required."""
from pathlib import Path
import subprocess
import sys

RUN_KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE='PersonalAppAgent'


def startup_enabled():
    if sys.platform!='win32':return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:return bool(winreg.QueryValueEx(key,VALUE)[0])
    except FileNotFoundError:return False


def command(directory,executable=None):
    python=Path(executable or sys.executable)
    background=python.with_name('pythonw.exe')
    if background.is_file():python=background
    if not python.is_file():raise ValueError('Background startup Python executable is missing.')
    return subprocess.list2cmdline([str(python),'-m','app_agent.cli','--data-dir',str(Path(directory).absolute()),'worker'])


def set_startup(directory,enabled):
    if sys.platform!='win32':raise RuntimeError('Login startup configuration requires Windows.')
    import winreg
    if type(enabled) is not bool:raise ValueError('Startup setting must be an explicit boolean.')
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,VALUE,0,winreg.REG_SZ,command(directory))
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
                try:winreg.DeleteValue(key,VALUE)
                except FileNotFoundError:pass
        except FileNotFoundError:pass
