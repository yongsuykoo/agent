import json
import tempfile
import unittest
from app_agent.runner import TaskRunner, validate_action, reconcile_action
from test_runner import FakeDesktop, FakeCloud, observation


class RecoveryTests(unittest.TestCase):
    def test_stable_identity_corrects_seven_vs_eight_numeric_index(self):
        controls = [{"id": 43, "name": "Seven", "type": "Button", "automation_id": "num7Button", "enabled": True, "visible": True, "actions": ["invoke"]},
                    {"id": 44, "name": "Eight", "type": "Button", "automation_id": "num8Button", "enabled": True, "visible": True, "actions": ["invoke"]}]
        snapshot = {"controls": controls}
        action = {"kind": "invoke", "reason": "Press Seven", "target": 44, "automation_id": "num7Button", "target_name": "Seven"}
        self.assertEqual(validate_action(action, snapshot, require_identity=True)["target"], 43)
        with self.assertRaises(ValueError):
            validate_action({**action, "automation_id": "num8Button"}, snapshot, require_identity=True)
        controls.append({**controls[0], "id": 49})
        with self.assertRaises(ValueError):
            validate_action(action, snapshot, require_identity=True)

    def test_numeric_index_alone_is_rejected_for_model_actions(self):
        with self.assertRaisesRegex(ValueError, "numeric indexes alone"):
            validate_action({"kind": "invoke", "target": 1, "reason": "Press"}, observation(), require_identity=True)

    def test_wrong_result_claim_replans_and_verifies_authoritative_display(self):
        class Desktop(FakeDesktop):
            def observe(self):
                return {"window": "Calculator", "controls": [
                    {"id": 1, "name": "Clear", "type": "Button", "automation_id": "clearButton", "enabled": True, "visible": True, "actions": ["invoke"]},
                    {"id": 2, "name": "Display is " + ("45" if self.actions else "46"), "type": "Text", "automation_id": "CalculatorResults", "enabled": True, "visible": True}]}
        class Cloud(FakeCloud):
            def request(self, **payload):
                schema = payload["text"]["format"]
                assert schema["type"] == "json_schema" and schema["strict"] is True
                assert schema["schema"]["additionalProperties"] is False
                assert "automation_id" in schema["schema"]["required"]
                return super().request(**payload)
        cloud = Cloud([{"kind": "finish", "reason": "Wrong claim", "expected_text": "46"},
                       {"kind": "invoke", "target": 1, "reason": "Recover"},
                       {"kind": "finish", "reason": "Correct result", "expected_text": "45"}])
        result = self.execute(Desktop(), cloud, required_result_text="45", result_control_id="CalculatorResults")
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["execution"], "rejected_completion")
        self.assertIn("45", result["history"][0]["error"])

    def test_numeric_display_does_not_accept_substring_or_negative_result(self):
        for wrong in ("145", "-45", "45.5"):
            class Desktop(FakeDesktop):
                def observe(self):
                    return {"window": "Calculator", "controls": [{"id": 1, "name": "Display is " + wrong,
                            "type": "Text", "automation_id": "CalculatorResults", "enabled": True, "visible": True}]}
            cloud = FakeCloud([{"kind": "finish", "reason": "Done", "expected_text": "45"}]*3)
            result = self.execute(Desktop(), cloud, required_result_text="45", result_control_id="CalculatorResults")
            self.assertEqual(result["outcome"], "verification_failed")

    def test_unsupported_action_replans_to_advertised_text_entry(self):
        class Desktop(FakeDesktop):
            def observe(self):
                return {"window": "Untitled - Notepad", "controls": [{"id": 1, "name": "Text Editor", "type": "Edit", "automation_id": "editor", "enabled": True, "visible": True, "actions": ["type"], "value": "Hello" if self.actions else ""}]}
        cloud = FakeCloud([{"kind": "invoke", "target": 1, "reason": "Wrong pattern"},
                           {"kind": "type", "target": 1, "text": "Hello", "reason": "Use advertised text action"},
                           {"kind": "finish", "expected_text": "Hello", "reason": "Text present"}])
        result = self.execute(Desktop(), cloud)
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["execution"], "rejected_invalid_action")
        self.assertIn("available actions: type", result["history"][0]["error"])

    def test_old_greeting_cannot_satisfy_exact_replacement_task(self):
        goal = "My agent can operate Notepad."
        class Desktop(FakeDesktop):
            def observe(self):
                value = self.actions[-1]["text"] if self.actions else "Hello from my personal agent"
                return {"window": "Notepad", "controls": [{"id": 1, "name": "Text Editor", "type": "Edit", "automation_id": "15", "enabled": True, "visible": True, "actions": ["type"], "value": value}]}
        wrong = {"kind": "finish", "expected_text": "Hello from my personal agent", "reason": "Old greeting present"}
        task = "Replace the document text with exactly: " + goal + " Then verify the text."
        with tempfile.TemporaryDirectory() as directory:
            desktop = Desktop()
            cloud = FakeCloud([wrong, {"kind": "type", "target": 1, "text": goal, "reason": "Replace"},
                               {"kind": "finish", "expected_text": goal, "reason": "Correct text present"}])
            result = TaskRunner(desktop, cloud, lambda a, o: True, lambda m: None, directory).run(task, effect_timeout=0)
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["execution"], "rejected_completion")
        with tempfile.TemporaryDirectory() as directory:
            result = TaskRunner(Desktop(), FakeCloud([wrong]*3), lambda a, o: True, lambda m: None, directory).run(task)
        self.assertEqual(result["outcome"], "verification_failed")
        self.assertEqual(result["actions_executed"], 0)

    def execute(self, desktop, cloud, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            return TaskRunner(desktop, cloud, lambda action, obs: True, lambda text: None, directory).run("Calculate", effect_timeout=0, **kwargs)

    def test_action_failure_is_reobserved_and_replanned(self):
        class Desktop(FakeDesktop):
            def act(self, action):
                if action["kind"] == "invoke":
                    raise RuntimeError("Invoke pattern unavailable")
                super().act(action)
        cloud = FakeCloud([{"kind": "invoke", "target": 1, "reason": "Try invoke"},
                           {"kind": "click", "target": 1, "reason": "Recover using click"},
                           {"kind": "finish", "expected_text": "42", "reason": "Result"}])
        result = self.execute(Desktop(), cloud)
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["execution"], "failed")
        self.assertEqual(result["history"][1]["effect"], "observed_change")

    def test_repeated_no_effect_actions_stop(self):
        class Desktop(FakeDesktop):
            def observe(self):
                return observation()
        cloud = FakeCloud([{"kind": "invoke", "target": 1, "reason": "Try"}] * 3)
        result = self.execute(Desktop(), cloud)
        self.assertEqual(result["outcome"], "stalled")
        self.assertEqual(result["actions_executed"], 2)

    def test_visual_input_requires_bounds_and_unchanged_image(self):
        before = {**observation(), "viewport": {"width": 100, "height": 100, "sha256": "before"}}
        action = {"kind": "click_point", "x": 10, "y": 20, "reason": "Click"}
        self.assertEqual(validate_action(action, before), action)
        self.assertEqual(reconcile_action(action, before, before), action)
        self.assertIsNone(reconcile_action(action, before, {**before, "viewport": {**before["viewport"], "sha256": "after"}}))
        for bad in ({**action, "x": -1}, {**action, "x": 100}, {**action, "x": True}):
            with self.assertRaises(ValueError):
                validate_action(bad, before)

    def test_screenshot_sent_but_not_saved_in_session(self):
        class Desktop(FakeDesktop):
            def capture(self):
                return {"width": 10, "height": 10, "sha256": "testhash", "data_url": "data:image/png;base64,PRIVATEIMAGE"}
        class Cloud(FakeCloud):
            def request(self, **payload):
                self.payload = payload
                return super().request(**payload)
        desktop = Desktop()
        desktop.actions.append({"prior": True})
        cloud = Cloud([{"kind": "finish", "expected_text": "42", "reason": "Result"}])
        result = self.execute(desktop, cloud, use_vision=True)
        self.assertEqual(result["outcome"], "result_observed")
        self.assertIn("PRIVATEIMAGE", json.dumps(cloud.payload))
        self.assertNotIn("PRIVATEIMAGE", json.dumps(result))

    def test_visual_point_executes_and_is_counted_without_control_id(self):
        class Desktop(FakeDesktop):
            def capture(self):
                return {"width": 10, "height": 10, "sha256": "image", "data_url": "data:image/png;base64,test"}
        cloud = FakeCloud([{"kind": "click_point", "x": 3, "y": 4, "reason": "Click visible target"},
                           {"kind": "finish", "expected_text": "42", "reason": "Result"}])
        result = self.execute(Desktop(), cloud, use_vision=True)
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["executed_action"]["kind"], "click_point")

    def test_visual_assessment_has_distinct_outcome(self):
        class Desktop(FakeDesktop):
            def capture(self):
                return {"width": 10, "height": 10, "sha256": "image", "data_url": "data:image/png;base64,test"}
        cloud = FakeCloud([{"kind": "finish", "expected_text": "Visible result", "reason": "Result"},
                           {"matches": True, "observed_text": "Visible result", "evidence": "Image text"}])
        result = self.execute(Desktop(), cloud, use_vision=True)
        self.assertEqual(result["outcome"], "visual_result_assessed")
        self.assertEqual(result["history"][-1]["image_sha256"], "image")
