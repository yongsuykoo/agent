"""Global Windows emergency cancellation shortcut."""
import ctypes
import sys
import threading


def register_stop(callback, emit):
    stopped = threading.Event()
    if sys.platform != "win32":
        return stopped

    def watch():
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        identifier = 1
        # Ctrl + Alt + F12, plus MOD_NOREPEAT.
        warned=False
        while not user32.RegisterHotKey(None, identifier, 0x0002 | 0x0001 | 0x4000, 0x7B):
            if not warned:
                emit("Global stop shortcut temporarily unavailable; retrying. Use STOP or Esc in this window.");warned=True
            if stopped.wait(1):return
        message = wintypes.MSG()
        try:
            while not stopped.wait(0.05):
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x0312:
                        callback()
        finally:
            user32.UnregisterHotKey(None, identifier)
    threading.Thread(target=watch, daemon=True).start()
    return stopped
