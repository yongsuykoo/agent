"""Bounded Windows UI Automation adapter, imported only on Windows."""
import sys
import base64
import hashlib
import io

# UIA_Is*PatternAvailable PROPERTY identifiers, not pattern identifiers.
PATTERNS = {"invoke": 30031, "type": 30043, "select": 30036, "toggle": 30041,
            "expand": 30028, "collapse": 30028, "scroll": 30034}
CLICK_TYPES = {"Button", "MenuItem", "TabItem", "CheckBox", "RadioButton", "ListItem", "TreeItem", "Hyperlink", "Custom"}


def literal_keys(text):
    return "".join("{" + character + "}" if character in "+^%~{}()" else character for character in text)


def foreground_window():
    """Read the foreground HWND through the actual, pointer-sized Win32 API."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    function = user32.GetForegroundWindow
    function.argtypes = []
    function.restype = wintypes.HWND
    return function()


def native_edit(control, parent):
    """Resolve only a native Edit child belonging to the selected window."""
    if sys.platform != "win32" or control.element_info.control_type != "Edit":
        return None
    from pywinauto import Desktop
    from pywinauto import win32functions
    handle = control.handle
    if not handle or not win32functions.IsChild(parent.handle, handle):
        return None
    wrapper = Desktop(backend="win32").window(handle=handle).wrapper_object()
    if wrapper.class_name() != "Edit" or wrapper.process_id() != parent.process_id():
        return None
    return wrapper


def password_state(control, native=None):
    if native is not None:
        return bool(native.style() & 0x0020)  # ES_PASSWORD
    try:
        return bool(control.element_info.element.CurrentIsPassword)
    except Exception:
        return None


def text_readonly(control):
    try:
        value = control.iface_value.CurrentIsReadOnly
        if type(value) in (bool, int):
            return bool(value)
    except Exception:
        pass
    try:
        value = control.iface_text.DocumentRange.GetAttributeValue(40015)
        if type(value) in (bool, int) and value in (0, 1):
            return bool(value)
    except Exception:
        pass
    if sys.platform == "win32" and control.element_info.class_name == "Edit" and control.handle:
        import ctypes
        from ctypes import wintypes
        get_style = ctypes.windll.user32.GetWindowLongW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_long
        return bool(get_style(control.handle, -16) & 0x0800)
    return None


def text_actions(control, item):
    if item["type"] not in ("Edit", "Document", "ComboBox") or item["password"]:
        return
    try:
        item["value"] = str(control.iface_value.CurrentValue)[:2000]
    except Exception:
        try:
            item["value"] = control.iface_text.DocumentRange.GetText(2000)
        except Exception:
            pass
    item["readonly"] = text_readonly(control)
    item["actions"] = [action for action in item["actions"] if action != "type"]
    if item["readonly"] is False:
        item["actions"].append("type")


def window_process_id(handle):
    """Read the native process identity without inspecting window contents."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    function = user32.GetWindowThreadProcessId
    function.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    function.restype = wintypes.DWORD
    process = wintypes.DWORD()
    if not function(handle, ctypes.byref(process)) or not process.value:
        raise RuntimeError("Window closed or its process identity is unavailable.")
    return process.value


def window_process_executable(handle):
    """Read the executable of one current window, without command arguments."""
    if sys.platform != 'win32':
        raise RuntimeError('Process identity requires Windows.')
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.restype=wintypes.BOOL
    process=kernel.OpenProcess(0x1000,False,window_process_id(handle))
    if not process:return None
    try:
        buffer=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(buffer))
        return buffer.value if kernel.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(length)) else None
    finally:kernel.CloseHandle(process)


def window_class_name(handle):
    if sys.platform!='win32':raise RuntimeError('Window class requires Windows.')
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user32.GetClassNameW.restype=ctypes.c_int
    value=ctypes.create_unicode_buffer(256)
    return value.value if user32.GetClassNameW(handle,value,len(value)) else None


class WindowsDesktop:
    executable=staticmethod(window_process_executable)
    window_class=staticmethod(window_class_name)
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
        found = []
        for window in Desktop(backend="uia").windows():
            try:
                title = window.window_text()
                if window.is_visible() and title:
                    found.append((window.handle, title))
            except Exception:
                # Windows can close or become inaccessible during enumeration.
                continue
        return found

    def observe(self):
        if not self.window.is_visible():
            raise RuntimeError("Selected window is no longer visible.")
        try:
            self.controls = [self.window] + self.window.descendants()[:250]
        except Exception as error:
            raise RuntimeError("Could not read the selected app's accessibility controls. Close and reopen the app, refresh windows, and select it again.") from error
        result = []
        for index, control in enumerate(self.controls):
            try:
                info = control.element_info
                item = {"id": index, "name": info.name[:500], "type": info.control_type,
                               "automation_id": info.automation_id,
                               "class_name": str(getattr(info, "class_name", ""))[:200],
                               "enabled": control.is_enabled(), "visible": control.is_visible(),
                               "actions": [], "value": "", "password": False, "state": {}}
                try:
                    element = info.element
                    item["password"] = password_state(control)
                    for name, property_id in PATTERNS.items():
                        try:
                            if element.GetCurrentPropertyValue(property_id):
                                item["actions"].append(name)
                        except Exception:
                            continue
                    text_actions(control, item)
                    if "toggle" in item["actions"]:
                        item["state"]["toggle"] = int(control.iface_toggle.CurrentToggleState)
                    if "expand" in item["actions"]:
                        item["state"]["expanded"] = int(control.iface_expand_collapse.CurrentExpandCollapseState)
                    if "select" in item["actions"]:
                        item["state"]["selected"] = bool(control.iface_selection_item.CurrentIsSelected)
                    if "scroll" in item["actions"]:
                        item["state"]["scroll"] = [float(control.iface_scroll.CurrentHorizontalScrollPercent), float(control.iface_scroll.CurrentVerticalScrollPercent)]
                except Exception:
                    pass
                # Native edit support must survive failures in UIA property probing.
                native = native_edit(control, self.window)
                if native is not None:
                    item["password"] = password_state(control, native)
                    if not item["password"]:
                        item["value"] = native.window_text()[:2000]
                        item["readonly"] = bool(native.style() & 0x0800)
                        item["actions"] = [a for a in item["actions"] if a != "type"]
                        if not item["readonly"]:
                            item["actions"].append("type")
                if info.control_type in CLICK_TYPES:
                    item["actions"].append("click")
                if item["password"] is not False:
                    item["name"] = "[password control]"
                    item["value"] = ""
                    item["actions"] = []
                result.append(item)
            except Exception:
                continue
        return {"window": self.window.window_text(), "window_handle": self.window.handle,
                "process_id": self.window.process_id(), "controls": result}

    def act(self, action):
        if action.get("kind") == "click_point":
            viewport = self.viewport
            bounds = self.window.rectangle()
            if bounds.width() != viewport["original_width"] or bounds.height() != viewport["original_height"]:
                raise RuntimeError("Window resized; capture a new image before clicking.")
            x, y = action["x"], action["y"]
            if type(x) is not int or type(y) is not int or not 0 <= x < viewport["width"] or not 0 <= y < viewport["height"]:
                raise ValueError("Visual click is outside the selected window.")
            self.window.set_focus()
            from pywinauto import mouse
            mouse.click(coords=(bounds.left + int(x * bounds.width() / viewport["width"]),
                                bounds.top + int(y * bounds.height() / viewport["height"])))
            return
        index = action.get("target")
        if type(index) is not int or not 0 < index < len(self.controls):
            raise ValueError("Action target is outside the selected window.")
        control = self.controls[index]
        if not control.is_visible() or not control.is_enabled():
            raise RuntimeError("Target is hidden or disabled; re-observation required.")
        self.window.set_focus()
        native = native_edit(control, self.window)
        if password_state(control, native) is not False:
            raise ValueError("Password controls cannot be automated.")
        if action["kind"] == "invoke":
            control.invoke()
        elif action["kind"] == "type":
            if native is not None:
                if native.style() & 0x0800:
                    raise ValueError("Cannot edit a read-only control.")
                native.set_edit_text(action["text"])
                return
            if control.element_info.control_type in ("Edit", "Document", "ComboBox"):
                if text_readonly(control) is not False:
                    raise ValueError("Text target is read-only or its editability is unknown.")
                try:
                    value = control.iface_value
                except Exception:
                    value = None
                if value is not None:
                    if value.CurrentIsReadOnly:
                        raise ValueError("Cannot edit a read-only control.")
                    if control.element_info.control_type == "Edit":
                        control.set_edit_text(action["text"])
                    else:
                        value.SetValue(action["text"])
                elif control.element_info.control_type in ("Edit", "Document"):
                    control.set_focus()
                    if not control.element_info.element.CurrentHasKeyboardFocus:
                        raise RuntimeError("Text target did not receive focus; no keyboard input sent.")
                    from pywinauto.keyboard import send_keys
                    send_keys("^a")
                    send_keys(literal_keys(action["text"]), with_spaces=True, with_newlines=True, with_tabs=True)
                else:
                    raise ValueError("Editable value pattern unavailable.")
            else:
                raise ValueError("Text entry requires a supported editable control.")
        elif action["kind"] == "select":
            control.iface_selection_item.Select()
        elif action["kind"] == "toggle":
            wanted = {"off": 0, "on": 1}[action["state"]]
            if control.iface_toggle.CurrentToggleState != wanted:
                control.iface_toggle.Toggle()
        elif action["kind"] in ("expand", "collapse"):
            if action["kind"] == "expand":
                control.iface_expand_collapse.Expand()
            else:
                control.iface_expand_collapse.Collapse()
        elif action["kind"] == "scroll":
            horizontal, vertical = {"up": (2, 1), "down": (2, 4), "left": (1, 2), "right": (4, 2)}[action["direction"]]
            control.iface_scroll.Scroll(horizontal, vertical)
        elif action["kind"] == "click":
            if control.element_info.control_type not in CLICK_TYPES:
                raise ValueError("Control type does not support the approved click fallback.")
            bounds = control.rectangle()
            window = self.window.rectangle()
            if not (window.left <= bounds.left < bounds.right <= window.right and window.top <= bounds.top < bounds.bottom <= window.bottom):
                raise ValueError("Click target is outside the selected window.")
            control.click_input()
        else:
            raise ValueError("Unsupported desktop action.")

    def capture(self):
        if not self.window.is_visible():
            raise RuntimeError("Cannot capture a hidden app window.")
        image = self.window.capture_as_image()
        original = image.size
        image.thumbnail((1280, 1280))
        output = io.BytesIO()
        image.save(output, format="PNG")
        raw = output.getvalue()
        if len(raw) > 4_000_000:
            raise RuntimeError("Selected-window image exceeds upload limit.")
        self.viewport = {"width": image.width, "height": image.height,
                         "original_width": original[0], "original_height": original[1]}
        return {**self.viewport, "sha256": hashlib.sha256(raw).hexdigest(),
                "data_url": "data:image/png;base64," + base64.b64encode(raw).decode()}
