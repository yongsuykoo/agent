import unittest
from app_agent.practice_policy import calculator_action, calculator_app


class PracticePolicyTests(unittest.TestCase):
    def observation(self, target_id="num2Button"):
        return {"controls": [
            {"id": 1, "type": "Text", "automation_id": "CalculatorResults"},
            {"id": 2, "type": "Button", "automation_id": "num2Button"},
            {"id": 3, "type": "Button", "automation_id": "equalButton"},
            {"id": 4, "type": "Button", "automation_id": target_id}]}

    def test_only_mathematical_calculator_controls_are_allowed(self):
        self.assertTrue(calculator_action({"kind": "invoke", "target": 4}, self.observation("plusButton")))
        self.assertTrue(calculator_action({"kind": "click", "target": 4}, self.observation("plusButton")))
        for identity in ("Close", "ClearMemoryButton", "TogglePaneButton", "unknown"):
            self.assertFalse(calculator_action({"kind": "invoke", "target": 4}, self.observation(identity)))
            self.assertFalse(calculator_action({"kind": "click", "target": 4}, self.observation(identity)))
        self.assertFalse(calculator_action({"kind": "type", "target": 4}, self.observation()))

    def test_other_apps_cannot_claim_calculator_permission(self):
        self.assertFalse(calculator_action({"kind": "invoke", "target": 4}, {"controls": []}))
        self.assertFalse(calculator_app({"app_id": "other!Calculator"}))
        self.assertTrue(calculator_app({"app_id": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}))
