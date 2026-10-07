"""Keep cached Windows COM interfaces on their owning thread."""
import queue
import sys
import threading


def initialize_com():
    sys.coinit_flags = 0
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    return pythoncom.CoUninitialize


class AutomationWorker:
    def __init__(self, run, on_error, initialize=initialize_com):
        self.queue = queue.Queue()
        self.run = run
        self.on_error = on_error
        self.initialize = initialize
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, function):
        self.queue.put(function)

    def close(self):
        self.queue.put(None)

    def _loop(self):
        try:
            cleanup = self.initialize()
        except Exception as error:
            self.on_error(error)
            return
        try:
            while True:
                function = self.queue.get()
                if function is None:
                    break
                try:
                    self.run(function)
                except Exception as error:
                    self.on_error(error)
        finally:
            cleanup()
