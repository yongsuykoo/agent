import unittest
from unittest.mock import Mock, patch
from app_agent.windows_checks import CalculatorDetectionError, calculator_smoke


class CalculatorChecksTests(unittest.TestCase):
    def test_non_arithmetic_calculator_mode_is_switched_to_standard(self):
        desktop = self.calculator()
        desktop.window.class_name.return_value = "ApplicationFrameWindow"
        ready = {"standard": False}
        original_observe = desktop.observe.side_effect
        original_keys = desktop.window.type_keys.side_effect
        def observe():
            if ready["standard"]:
                return original_observe()
            return {"window": "Calculator", "controls": [{"id": 1, "automation_id": "converterView"}]}
        def keys(sequence, **kwargs):
            if sequence == "%1":
                ready["standard"] = True
            else:
                original_keys(sequence, **kwargs)
        desktop.observe.side_effect = observe
        desktop.window.type_keys.side_effect = keys
        cancel = Mock()
        cancel.is_set.return_value = False
        with patch("app_agent.windows_checks.sys.platform", "win32"), \
             patch("app_agent.windows_checks.subprocess.Popen"), \
             patch("app_agent.windows_checks.WindowsDesktop") as adapter, \
             patch("app_agent.windows_checks.foreground_window", return_value=41):
            adapter.windows.return_value = [(99, "Other app"), (41, "Calculator")]
            adapter.return_value = desktop
            result = calculator_smoke(cancel)
        self.assertEqual(result["passed"], 3)
        desktop.window.type_keys.assert_any_call("%1", set_foreground=False)
        self.assertEqual(desktop.window.type_keys.call_count, 4)
        self.assertEqual(adapter.call_args_list[0].args, (41,))

    def test_failed_detection_records_ids_and_does_not_send_keys_to_unknown_app(self):
        desktop = Mock()
        desktop.window.class_name.return_value = "Chrome_WidgetWin_1"
        desktop.observe.return_value = {"window": "Calculator", "controls": [{"id": 1, "automation_id": "browserView"}]}
        cancel = Mock()
        cancel.is_set.return_value = False
        with patch("app_agent.windows_checks.sys.platform", "win32"), \
             patch("app_agent.windows_checks.subprocess.Popen"), \
             patch("app_agent.windows_checks.WindowsDesktop") as adapter, \
             patch("app_agent.windows_checks.time.monotonic", side_effect=[0, 1, 100]):
            adapter.windows.return_value = [(41, "Calculator")]
            adapter.return_value = desktop
            with self.assertRaises(CalculatorDetectionError) as failure:
                calculator_smoke(cancel)
        self.assertEqual(failure.exception.details["calculator_candidates"][0]["automation_ids"], ["browserView"])
        self.assertIn("CalculatorResults", failure.exception.details["calculator_candidates"][0]["missing_required_ids"])
        desktop.window.type_keys.assert_not_called()
        desktop.act.assert_not_called()

    def calculator(self):
        desktop = Mock()
        desktop.window.handle = 41
        desktop.window.process_id.return_value = 81
        identities = [*[f"num{i}Button" for i in range(10)], "plusButton", "minusButton", "divideButton", "equalButton"]
        state = {"value": "0", "left": None, "operator": None, "new": True}
        def observe():
            controls = [{"id": i + 1, "automation_id": identity, "name": identity, "type": "Button",
                         "enabled": True, "visible": True, "actions": ["click"]} for i, identity in enumerate(identities)]
            controls.append({"id": 99, "automation_id": "CalculatorResults", "name": state["value"], "type": "Text"})
            return {"window": "Calculator", "controls": controls}
        def clear(*args, **kwargs):
            state.update(value="0", left=None, operator=None, new=True)
        def act(action):
            identity = identities[action["target"] - 1]
            if identity.startswith("num"):
                digit = identity[3]
                state["value"] = digit if state["new"] else state["value"] + digit
                state["new"] = False
            elif identity == "equalButton":
                left, right = state["left"], int(state["value"])
                value = {"plusButton": lambda: left + right, "minusButton": lambda: left - right,
                         "divideButton": lambda: left // right}[state["operator"]]()
                state.update(value=str(value), new=True)
            else:
                state.update(left=int(state["value"]), operator=identity, new=True)
        desktop.observe.side_effect = observe
        desktop.act.side_effect = act
        desktop.window.type_keys.side_effect = clear
        return desktop

    def test_calculator_without_clear_button_uses_scoped_escape_and_clicks(self):
        desktop = self.calculator()
        cancel = Mock()
        cancel.is_set.return_value = False
        with patch("app_agent.windows_checks.sys.platform", "win32"), \
             patch("app_agent.windows_checks.subprocess.Popen"), \
             patch("app_agent.windows_checks.WindowsDesktop") as adapter, \
             patch("app_agent.windows_checks.foreground_window", return_value=41):
            adapter.windows.return_value = [(41, "Calculator")]
            adapter.return_value = desktop
            result = calculator_smoke(cancel)
        self.assertEqual(result["passed"], 3)
        self.assertEqual((result["window_handle"], result["process_id"]), (41, 81))
        self.assertEqual([c["expected"] for c in result["checks"]], ["42", "4", "6"])
        self.assertEqual(desktop.window.type_keys.call_count, 3)
        self.assertTrue(all(call.args[0]["kind"] == "click" for call in desktop.act.call_args_list))

    def test_escape_is_not_sent_when_other_app_has_foreground_focus(self):
        desktop = self.calculator()
        with patch("app_agent.windows_checks.sys.platform", "win32"), \
             patch("app_agent.windows_checks.subprocess.Popen"), \
             patch("app_agent.windows_checks.WindowsDesktop") as adapter, \
             patch("app_agent.windows_checks.foreground_window", return_value=999):
            adapter.windows.return_value = [(41, "Calculator")]
            adapter.return_value = desktop
            with self.assertRaisesRegex(RuntimeError, "no clear shortcut sent"):
                calculator_smoke()
        desktop.act.assert_not_called()
        desktop.window.type_keys.assert_not_called()
