import json
import tempfile
import threading
import unittest
from pathlib import Path
from app_agent.runner import TaskRunner, validate_action, reconcile_action


def observation(name="Add", enabled=True):
    return {"window": "Calculator", "controls": [{"id": 1, "name": name, "type": "Text" if name == "42" else "Button", "automation_id": "plus", "enabled": enabled, "visible": True}]}


class FakeDesktop:
    def __init__(self):
        self.actions = []
    def observe(self):
        return observation("42" if self.actions else "Add")
    def act(self, action):
        self.actions.append(action)


class FakeCloud:
    def __init__(self, actions):
        self.actions = iter(actions)
    def request(self, **payload):
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(next(self.actions))}]}]}


class RunnerTests(unittest.TestCase):
    def execute(self, actions, approve=lambda action, obs: True, desktop=None, cancel=None):
        desktop = desktop or FakeDesktop()
        with tempfile.TemporaryDirectory() as directory:
            result = TaskRunner(desktop, FakeCloud(actions), approve, lambda msg: None, directory, cancel).run("Calculate", max_steps=3)
            saved = json.loads((Path(directory) / "sessions.jsonl").read_text())
            self.assertEqual(saved, result)
            return result, desktop

    def test_approved_action_then_observed_result(self):
        result, desktop = self.execute([{"kind": "invoke", "target": 1, "reason": "Add"}, {"kind": "finish", "expected_text": "42", "reason": "Result"}])
        self.assertEqual(result["outcome"], "result_observed")
        self.assertEqual(len(desktop.actions), 1)
        self.assertEqual(result["actions_executed"], 1)
        self.assertEqual(result["history"][0]["execution"], "executed")

    def test_control_reordering_remaps_approved_target(self):
        before = observation()
        after = observation()
        after["controls"][0]["id"] = 5
        action = {"kind": "invoke", "target": 1, "reason": "Add"}
        self.assertEqual(reconcile_action(action, before, after)["target"], 5)

    def test_unrelated_button_visibility_change_is_tolerated(self):
        before = observation()
        before["controls"].append({"id": 2, "name": "Minimize", "type": "Button", "automation_id": "min", "enabled": True, "visible": True})
        after = json.loads(json.dumps(before))
        after["controls"][1]["visible"] = False
        action = {"kind": "invoke", "target": 1, "reason": "Add"}
        self.assertEqual(reconcile_action(action, before, after), action)

    def test_result_changes_and_duplicate_targets_block_approval(self):
        before = observation()
        before["controls"].append({"id": 2, "name": "0", "type": "Text", "automation_id": "result", "enabled": True, "visible": True})
        after = json.loads(json.dumps(before))
        after["controls"][1]["name"] = "23"
        action = {"kind": "invoke", "target": 1, "reason": "Add"}
        self.assertIsNone(reconcile_action(action, before, after))
        duplicate = json.loads(json.dumps(before))
        duplicate["controls"].append({**duplicate["controls"][0], "id": 3})
        self.assertIsNone(reconcile_action(action, before, duplicate))

    def test_rejection_prevents_action(self):
        result, desktop = self.execute([{"kind": "invoke", "target": 1, "reason": "Add"}], approve=lambda action, obs: False)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(desktop.actions, [])

    def test_false_completion_fails_verification(self):
        result, desktop = self.execute([{"kind": "finish", "expected_text": "42", "reason": "Done"}])
        self.assertEqual(result["outcome"], "verification_failed")

    def test_button_label_does_not_prove_completion(self):
        result, desktop = self.execute([{"kind": "finish", "expected_text": "Add", "reason": "Done"}])
        self.assertEqual(result["outcome"], "verification_failed")

    def test_cancel_before_request(self):
        cancel = threading.Event()
        cancel.set()
        result, desktop = self.execute([], cancel=cancel)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(desktop.actions, [])

    def test_cancel_during_approval(self):
        cancel = threading.Event()
        def approve(action, obs):
            cancel.set()
            return True
        result, desktop = self.execute([{"kind": "invoke", "target": 1, "reason": "Add"}], approve=approve, cancel=cancel)
        self.assertEqual(result["outcome"], "cancelled")
        self.assertEqual(desktop.actions, [])

    def test_stale_approval_replans(self):
        desktop = FakeDesktop()
        def approve(action, obs):
            desktop.actions.append({"external": True})
            return True
        result, desktop = self.execute([{"kind": "invoke", "target": 1, "reason": "Add"}, {"kind": "blocked", "reason": "Changed"}], approve=approve, desktop=desktop)
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(desktop.actions, [{"external": True}])

    def test_invalid_and_disabled_actions_rejected(self):
        for action in ({"kind": "shell", "reason": "run"}, {"kind": "invoke", "target": 0, "reason": "root"}, {"kind": "invoke", "target": 9, "reason": "missing"}, {"kind": "finish", "reason": "done", "expected_text": ""}):
            with self.assertRaises(ValueError):
                validate_action(action, observation())
        with self.assertRaises(ValueError):
            validate_action({"kind": "invoke", "target": 1, "reason": "disabled"}, observation(enabled=False))
