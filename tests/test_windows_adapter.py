import unittest
from unittest.mock import Mock
from app_agent.desktop import WindowsDesktop


class DesktopAdapterTests(unittest.TestCase):
    def adapter(self, kind="Edit"):
        desktop = WindowsDesktop.__new__(WindowsDesktop)
        desktop.window = Mock()
        control = Mock()
        control.element_info.control_type = kind
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

    def test_root_and_out_of_range_targets_blocked(self):
        desktop, control = self.adapter()
        for target in (0, -1, 2, True, "1"):
            with self.assertRaises(ValueError):
                desktop.act({"kind": "invoke", "target": target})
        control.invoke.assert_not_called()
