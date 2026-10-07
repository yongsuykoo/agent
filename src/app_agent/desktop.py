"""Bounded Windows UI Automation adapter, imported only on Windows."""
import sys


class WindowsDesktop:
    def __init__(self, handle):
        if sys.platform != "win32":
            raise RuntimeError("Desktop control requires an interactive Windows session.")
        from pywinauto import Desktop
        self.window = Desktop(backend="uia").window(handle=int(handle)).wrapper_object()
        self.controls = []

    @staticmethod
    def windows():
        if sys.platform != "win32":
            raise RuntimeError("Window discovery requires Windows.")
        from pywinauto import Desktop
        return [(window.handle, window.window_text()) for window in Desktop(backend="uia").windows()
                if window.is_visible() and window.window_text()]

    def observe(self):
        if not self.window.is_visible():
            raise RuntimeError("Selected window is no longer visible.")
        self.controls = [self.window] + self.window.descendants()[:250]
        result = []
        for index, control in enumerate(self.controls):
            try:
                info = control.element_info
                result.append({"id": index, "name": info.name[:500], "type": info.control_type,
                               "automation_id": info.automation_id,
                               "enabled": control.is_enabled(), "visible": control.is_visible()})
            except Exception:
                continue
        return {"window": self.window.window_text(), "controls": result}

    def act(self, action):
        index = action.get("target")
        if type(index) is not int or not 0 < index < len(self.controls):
            raise ValueError("Action target is outside the selected window.")
        control = self.controls[index]
        if not control.is_visible() or not control.is_enabled():
            raise RuntimeError("Target is hidden or disabled; re-observation required.")
        self.window.set_focus()
        if action["kind"] == "invoke":
            control.invoke()
        elif action["kind"] == "type":
            if control.element_info.control_type != "Edit":
                raise ValueError("Text entry is allowed only into Edit controls.")
            control.set_edit_text(action["text"])
        else:
            raise ValueError("Unsupported desktop action.")
