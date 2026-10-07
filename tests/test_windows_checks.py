import unittest
from unittest.mock import Mock, patch
from app_agent.windows_checks import calculator_smoke


class CalculatorChecksTests(unittest.TestCase):
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
