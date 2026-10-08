import unittest
from unittest.mock import Mock, PropertyMock, patch
from app_agent.desktop import WindowsDesktop, foreground_window, literal_keys, text_actions


class DesktopAdapterTests(unittest.TestCase):
    def test_process_identity_uses_pointer_sized_handle_and_rejects_closed_windows(self):
        from ctypes import wintypes
        from app_agent.desktop import window_process_id
        user32 = Mock()
        def identity(handle, process):
            self.assertEqual(handle, 0x100000001)
            process._obj.value = 81
            return 7
        user32.GetWindowThreadProcessId.side_effect = identity
        with patch("ctypes.WinDLL", return_value=user32, create=True):
            self.assertEqual(window_process_id(0x100000001), 81)
            user32.GetWindowThreadProcessId.side_effect = None
            user32.GetWindowThreadProcessId.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "Window closed"):
                window_process_id(0x100000001)
        self.assertIs(user32.GetWindowThreadProcessId.argtypes[0], wintypes.HWND)

    def test_foreground_window_uses_user32_api_with_pointer_sized_result(self):
        from ctypes import wintypes
        user32 = Mock()
        user32.GetForegroundWindow.return_value = 0x100000001
        with patch("ctypes.WinDLL", return_value=user32, create=True) as library:
            self.assertEqual(foreground_window(), 0x100000001)
        library.assert_called_once_with("user32", use_last_error=True)
        self.assertEqual(user32.GetForegroundWindow.argtypes, [])
        self.assertIs(user32.GetForegroundWindow.restype, wintypes.HWND)

    def test_invoke_capability_queries_uia_property_30031(self):
        desktop, control = self.adapter("Button")
        desktop.window.element_info.name = "Calculator"
        desktop.window.element_info.control_type = "Window"
        desktop.window.element_info.element.CurrentIsPassword = False
        desktop.window.element_info.element.GetCurrentPropertyValue.return_value = False
        desktop.window.descendants.return_value = [control]
        control.element_info.name = "Two"
        control.element_info.automation_id = "num2Button"
        control.element_info.element.GetCurrentPropertyValue.side_effect = lambda identity: identity == 30031
        item = desktop.observe()["controls"][1]
        self.assertIn("invoke", item["actions"])
        control.element_info.element.GetCurrentPropertyValue.assert_any_call(30031)
        self.assertNotIn(10031, [call.args[0] for call in control.element_info.element.GetCurrentPropertyValue.call_args_list])

    def test_keyboard_fallback_escapes_literal_shortcut_characters(self):
        self.assertEqual(literal_keys("a+b^c%{x}"), "a{+}b{^}c{%}{{}x{}}")

    def test_text_pattern_readonly_attribute_advertises_document_input(self):
        control = Mock()
        type(control).iface_value = PropertyMock(side_effect=RuntimeError("No Value pattern"))
        control.iface_text.DocumentRange.GetAttributeValue.return_value = False
        control.iface_text.DocumentRange.GetText.return_value = "sample"
        item = {"type": "Document", "password": False, "actions": [], "value": ""}
        text_actions(control, item)
        self.assertEqual(item["actions"], ["type"])
        self.assertEqual(item["value"], "sample")

    def test_readonly_document_does_not_advertise_input(self):
        control = Mock()
        type(control).iface_value = PropertyMock(side_effect=RuntimeError("No Value pattern"))
        control.iface_text.DocumentRange.GetAttributeValue.return_value = True
        item = {"type": "Document", "password": False, "actions": [], "value": ""}
        text_actions(control, item)
        self.assertNotIn("type", item["actions"])
    def adapter(self, kind="Edit"):
        # These are UIA unit tests, not real HWNDs. Mock the native boundary on
        # every host; otherwise Windows passes Mock objects into ctypes.IsChild.
        native_boundary = patch("app_agent.desktop.native_edit", return_value=None)
        native_boundary.start()
        self.addCleanup(native_boundary.stop)
        desktop = WindowsDesktop.__new__(WindowsDesktop)
        desktop.window = Mock()
        control = Mock()
        control.element_info.control_type = kind
        control.element_info.element.CurrentIsPassword = False
        control.iface_value.CurrentIsReadOnly = False
        control.is_visible.return_value = True
        control.is_enabled.return_value = True
        desktop.controls = [desktop.window, control]
        return desktop, control

    def test_classic_edit_without_uia_patterns_is_advertised_and_verified(self):
        desktop, control = self.adapter()
        desktop.window.descendants.return_value = [control]
        desktop.window.element_info.name = "Untitled - Notepad"
        desktop.window.element_info.control_type = "Window"
        control.element_info.name = "Text Editor"
        control.element_info.automation_id = "15"
        type(control.element_info.element).CurrentIsPassword = PropertyMock(
            side_effect=RuntimeError("UIA property unavailable"))
        native = Mock()
        native.style.return_value = 0
        native.window_text.return_value = "Hello from my personal agent"
        with patch("app_agent.desktop.native_edit", side_effect=lambda c, p: native if c is control else None):
            observed = desktop.observe()["controls"][1]
            self.assertIn("type", observed["actions"])
            self.assertEqual(observed["value"], "Hello from my personal agent")
            desktop.act({"kind": "type", "target": 1, "text": "hello"})
        native.set_edit_text.assert_called_once_with("hello")

    def test_native_password_and_readonly_edits_block_writes(self):
        for style in (0x0020, 0x0800):
            desktop, control = self.adapter()
            native = Mock()
            native.style.return_value = style
            with patch("app_agent.desktop.native_edit", return_value=native):
                with self.assertRaises(ValueError):
                    desktop.act({"kind": "type", "target": 1, "text": "hello"})
            native.set_edit_text.assert_not_called()

    def test_invoke_and_text_use_accessibility_methods(self):
        desktop, control = self.adapter()
        desktop.act({"kind": "invoke", "target": 1})
        control.invoke.assert_called_once()
        desktop.act({"kind": "type", "target": 1, "text": "hello"})
        control.set_edit_text.assert_called_once_with("hello")

    def test_no_typing_into_other_control_types(self):
        desktop, control = self.adapter("Button")
        with self.assertRaises(ValueError):
            desktop.act({"kind": "type", "target": 1, "text": "hello"})
        control.set_edit_text.assert_not_called()

    def test_hidden_target_cannot_be_invoked(self):
        desktop, control = self.adapter()
        control.is_visible.return_value = False
        with self.assertRaises(RuntimeError):
            desktop.act({"kind": "invoke", "target": 1})
        control.invoke.assert_not_called()

    def test_selection_toggle_expansion_and_scroll_patterns(self):
        desktop, control = self.adapter("CheckBox")
        desktop.act({"kind": "select", "target": 1})
        control.iface_selection_item.Select.assert_called_once()
        control.iface_toggle.CurrentToggleState = 0
        desktop.act({"kind": "toggle", "target": 1, "state": "on"})
        control.iface_toggle.Toggle.assert_called_once()
        desktop.act({"kind": "expand", "target": 1})
        control.iface_expand_collapse.Expand.assert_called_once()
        desktop.act({"kind": "collapse", "target": 1})
        control.iface_expand_collapse.Collapse.assert_called_once()
        desktop.act({"kind": "scroll", "target": 1, "direction": "down"})
        control.iface_scroll.Scroll.assert_called_once_with(2, 4)

    def test_password_control_is_never_typed(self):
        desktop, control = self.adapter()
        control.element_info.element.CurrentIsPassword = True
        with self.assertRaises(ValueError):
            desktop.act({"kind": "type", "target": 1, "text": "secret"})
        control.set_edit_text.assert_not_called()

    def test_root_and_out_of_range_targets_blocked(self):
        desktop, control = self.adapter()
        for target in (0, -1, 2, True, "1"):
            with self.assertRaises(ValueError):
                desktop.act({"kind": "invoke", "target": target})
        control.invoke.assert_not_called()
