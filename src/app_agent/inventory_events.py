"""Windows registry change signals; periodic scans remain the reconciliation fallback."""
import os
import threading


class InventoryEvents:
    def __init__(self):
        self.watches = []
        self.lock = threading.RLock()
        self.dirty = False
        if os.name != 'nt':
            return
        try:
            import ctypes
            from ctypes import wintypes
            import winreg
            self.registry = winreg
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
            self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateEventW.restype = wintypes.HANDLE
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            self.advapi.RegNotifyChangeKeyValue.argtypes = [wintypes.HANDLE, wintypes.BOOL, wintypes.DWORD, wintypes.HANDLE, wintypes.BOOL]
            self.advapi.RegNotifyChangeKeyValue.restype = wintypes.LONG
            uninstall = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
            targets = [(root, uninstall, view) for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
                       for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)]
            targets += [(root, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths', view)
                        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
                        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)]
            targets += [(root, r'SOFTWARE\Classes', 0) for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)]
            targets.append((winreg.HKEY_CURRENT_USER,
                r'Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages', 0))
            for root, path, view in targets:
                try:
                    key = winreg.OpenKey(root, path, 0, winreg.KEY_NOTIFY | view)
                except OSError:
                    continue
                event = self.kernel.CreateEventW(None, False, False, None)
                if not event:
                    key.Close();continue
                self.watches.append((key, event))
                if not self.arm(key, event):
                    self.kernel.CloseHandle(event);key.Close();self.watches.pop()
        except Exception:
            self.close()

    def arm(self, key, event):
        # Subtree names/values; THREAD_AGNOSTIC avoids signals caused by a thread exiting.
        return self.advapi.RegNotifyChangeKeyValue(int(key), True, 0x10000005, event, True) == 0

    def poll(self):
        with self.lock:
            return self._poll()

    def _poll(self):
        for key, event in list(self.watches):
            status = self.kernel.WaitForSingleObject(event, 0)
            if status == 0:
                self.dirty = True
                if not self.arm(key, event):
                    self.kernel.CloseHandle(event);key.Close();self.watches.remove((key,event))
            elif status == 0xffffffff:
                self.kernel.CloseHandle(event);key.Close();self.watches.remove((key,event))
        return self.dirty

    def scanned(self):
        with self.lock:
            self.dirty = False

    def close(self):
        with self.lock:
            for key, event in self.watches:
                self.kernel.CloseHandle(event);key.Close()
            self.watches.clear()
