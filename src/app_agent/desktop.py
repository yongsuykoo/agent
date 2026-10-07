"""Bounded Windows UI Automation adapter, imported only on Windows."""
import sys
import base64
import hashlib
import io

PATTERNS = {"invoke": 10031, "type": 10043, "select": 10036, "toggle": 10041,
            "expand": 10028, "collapse": 10028, "scroll": 10034}
CLICK_TYPES = {"Button", "MenuItem", "TabItem", "CheckBox", "RadioButton", "ListItem", "TreeItem", "Hyperlink", "Custom"}


def literal_keys(text):
    return "".join("{" + character + "}" if character in "+^%~{}()" else character for character in text)


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
                               "enabled": control.is_enabled(), "visible": control.is_visible(),
                               "actions": [], "value": "", "password": False, "state": {}}
                try:
                    element = info.element
                    item["password"] = bool(element.CurrentIsPassword)
                    item["actions"] = [name for name, property_id in PATTERNS.items() if element.GetCurrentPropertyValue(property_id)]
                    if "type" in item["actions"] and not item["password"]:
                        item["value"] = str(control.iface_value.CurrentValue)[:2000]
                        if control.iface_value.CurrentIsReadOnly:
                            item["actions"].remove("type")
                    elif info.control_type == "Document" and not item["password"]:
                        try:
                            item["value"] = control.iface_text.DocumentRange.GetText(2000)
                            readonly = control.iface_text.DocumentRange.GetAttributeValue(40015)
                            if readonly is False or type(readonly) is int and readonly == 0:
                                item["actions"].append("type")
                        except Exception:
                            pass
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
                if info.control_type in CLICK_TYPES:
                    item["actions"].append("click")
                if item["password"]:
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
        if bool(control.element_info.element.CurrentIsPassword):
            raise ValueError("Password controls cannot be automated.")
        if action["kind"] == "invoke":
            control.invoke()
        elif action["kind"] == "type":
            if control.element_info.control_type == "Edit":
                control.set_edit_text(action["text"])
            elif control.element_info.control_type in ("Document", "ComboBox"):
                try:
                    value = control.iface_value
                except Exception:
                    value = None
                if value is not None:
                    if value.CurrentIsReadOnly:
                        raise ValueError("Cannot edit a read-only control.")
                    value.SetValue(action["text"])
                elif control.element_info.control_type == "Document":
                    readonly = control.iface_text.DocumentRange.GetAttributeValue(40015)
                    if not (readonly is False or type(readonly) is int and readonly == 0):
                        raise ValueError("Document is read-only or its editability is unknown.")
                    control.set_focus()
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
