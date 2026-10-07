import unittest
from unittest.mock import Mock, PropertyMock, patch
from app_agent.desktop import WindowsDesktop, literal_keys, text_actions


class DesktopAdapterTests(unittest.TestCase):
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
