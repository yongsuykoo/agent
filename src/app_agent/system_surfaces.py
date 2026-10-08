"""Fixed Windows GUI launch routes. No shell or model-generated URI/arguments."""
import ctypes
from pathlib import Path
import subprocess
import sys

SURFACES={
    'settings':('Windows Settings',['Settings','Windows Settings']),
    'file_explorer':('File Explorer',['File Explorer','Windows Explorer']),
    'task_manager':('Task Manager',['Task Manager']),
    'control_panel':('Control Panel',['Control Panel']),
}


def launch_surface(surface):
    if surface not in SURFACES:raise ValueError('Unknown Windows GUI surface.')
    if sys.platform!='win32':raise RuntimeError('Windows GUI launching requires Windows.')
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    def directory(function):
        function.argtypes=[wintypes.LPWSTR,wintypes.UINT];function.restype=wintypes.UINT
        value=ctypes.create_unicode_buffer(32768)
        size=function(value,len(value))
        if not 0<size<len(value):raise OSError('Windows system directory is unavailable.')
        return Path(value.value)
    windows=directory(kernel.GetWindowsDirectoryW)
    system=directory(kernel.GetSystemDirectoryW)
    routes={'settings':[str(windows/'explorer.exe'),'ms-settings:'],
            'file_explorer':[str(windows/'explorer.exe')],
            'task_manager':[str(system/'taskmgr.exe')],
            'control_panel':[str(system/'control.exe')]}
    command=routes[surface]
    if not Path(command[0]).is_file():raise OSError('Windows GUI executable is unavailable.')
    subprocess.Popen(command)
