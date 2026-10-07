import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from app_agent.self_test import NotepadFixture, SkipCheck, editor, learning_experiment, run_checks, self_test, wait_until


def snapshot(value="hello", handle=41, process=81, title="test"):
    return {"window": title, "window_handle": handle, "process_id": process,
            "controls": [{"id": 1, "name": "Text Editor", "type": "Edit", "enabled": True,
                          "visible": True, "password": False, "actions": ["type"], "value": value}]}


class SelfTestTests(unittest.TestCase):
    def test_failure_diagnostics_are_persisted_in_report(self):
        from app_agent.windows_checks import CalculatorDetectionError
        def fail():
            raise CalculatorDetectionError("No arithmetic controls", {"calculator_candidates": []})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = run_checks([("Calculator", fail)], path, threading.Event(), lambda text: None)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["checks"][0]["details"], {"calculator_candidates": []})
        self.assertEqual(report["status"], "failed")

    def test_failed_and_skipped_checks_are_recorded_without_hiding_next_check(self):
        def fail():
            raise RuntimeError("Exact result differs")
        def skip():
            raise SkipCheck("No cloud credential")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            result = run_checks([("failure", fail), ("cloud", skip), ("later", lambda: {"verified": True})],
                                path, threading.Event(), lambda text: None)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["counts"], {"passed": 1, "failed": 1, "skipped": 1, "cancelled": 0})

    def test_missing_cloud_is_partial_not_full_pass(self):
        def skip():
            raise SkipCheck("Cloud unavailable")
        with tempfile.TemporaryDirectory() as directory:
            report = run_checks([("native", lambda: {}), ("cloud", skip)], Path(directory) / "report.json",
                                threading.Event(), lambda text: None)
        self.assertEqual(report["status"], "partial")

    def test_cancel_prevents_remaining_actions_and_saves_report(self):
        cancel = threading.Event()
        later = Mock()
        def first():
            cancel.set()
        with tempfile.TemporaryDirectory() as directory:
            report = run_checks([("first", first), ("later", later)], Path(directory) / "report.json", cancel, lambda text: None)
        later.assert_not_called()
        self.assertEqual(report["status"], "cancelled")
        self.assertEqual(report["counts"]["cancelled"], 1)

    def test_ambiguous_or_password_editors_are_rejected(self):
        current = snapshot()
        self.assertEqual(editor(current)["id"], 1)
        current["controls"][0]["password"] = True
        with self.assertRaises(RuntimeError):
            editor(current)
        current = snapshot()
        current["controls"].append({**current["controls"][0], "id": 2})
        with self.assertRaises(RuntimeError):
            editor(current)

    def fixture(self, directory):
        fixture = NotepadFixture(directory, threading.Event())
        fixture.identity = (41, 81)
        fixture.desktop = Mock()
        fixture.desktop.observe.return_value = snapshot(title=fixture.path.stem + " - Notepad")
        return fixture

    def test_fixture_rejects_changed_process_or_user_document(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory)
            fixture.desktop.observe.return_value["process_id"] = 82
            with self.assertRaises(RuntimeError):
                fixture.replace("test")
            fixture.desktop.act.assert_not_called()
            fixture.desktop.observe.return_value = snapshot(title="My real document - Notepad")
            with self.assertRaises(RuntimeError):
                fixture.replace("test")
            fixture.desktop.act.assert_not_called()

    def test_cloud_grant_only_allows_fixture_editor_typing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(directory)
            current = fixture.observe()
            self.assertTrue(fixture.approve({"kind": "type", "target": 1}, current))
            self.assertFalse(fixture.approve({"kind": "click", "target": 1}, current))
            self.assertFalse(fixture.approve({"kind": "type", "target": 2}, current))
            self.assertFalse(fixture.approve({"kind": "type", "target": 1}, {**current, "window_handle": 42}))

    def test_learning_check_rejects_a_mismatched_generated_goal_before_typing(self):
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": json.dumps({
            "task": "Replace the document text with exactly: First", "expected_result": "Different",
            "capability_name": "Write", "risk": "disposable"})}]}]}
        with tempfile.TemporaryDirectory() as directory, patch("app_agent.learning.research_app", return_value={"capabilities": [{"name": "Write"}]}):
            fixture = self.fixture(directory)
            with self.assertRaisesRegex(RuntimeError, "matching its expected result"):
                learning_experiment(fixture, cloud, directory, threading.Event(), lambda text: None)
            fixture.desktop.act.assert_not_called()

    def test_learning_check_without_credentials_skips_without_opening_or_researching(self):
        fixture = Mock()
        with patch("app_agent.learning.research_app") as research:
            with self.assertRaises(SkipCheck):
                learning_experiment(fixture, None, "unused", threading.Event(), lambda text: None)
            fixture.observe.assert_not_called()
            research.assert_not_called()

    def test_save_does_not_send_shortcut_into_other_foreground_window(self):
        functions = types.SimpleNamespace(GetForegroundWindow=lambda: 999)
        package = types.ModuleType("pywinauto")
        package.win32functions = functions
        with tempfile.TemporaryDirectory() as directory, patch("app_agent.self_test.foreground_window", return_value=999):
            fixture = self.fixture(directory)
            with self.assertRaises(RuntimeError):
                fixture.save()
            fixture.desktop.window.type_keys.assert_not_called()

    def test_save_verifies_disk_not_model_claim(self):
        package = types.ModuleType("pywinauto")
        package.win32functions = types.SimpleNamespace(GetForegroundWindow=lambda: 41)
        with tempfile.TemporaryDirectory() as directory, patch("app_agent.self_test.foreground_window", return_value=41):
            fixture = self.fixture(directory)
            fixture.path.write_text("hello", encoding="utf-8")
            result = fixture.save()
            self.assertTrue(result["disk_text_matches_editor"])
            fixture.desktop.window.type_keys.assert_called_once_with("^s", set_foreground=False)

    def test_wait_times_out_and_stop_does_not_run_probe(self):
        with self.assertRaises(RuntimeError):
            wait_until(lambda: None, threading.Event(), timeout=0)
        cancel = threading.Event()
        cancel.set()
        probe = Mock()
        with self.assertRaises(RuntimeError):
            wait_until(probe, cancel)
        probe.assert_not_called()

    def test_linux_is_not_reported_as_live_windows_validation(self):
        with patch("app_agent.self_test.sys.platform", "linux"):
            with self.assertRaisesRegex(RuntimeError, "interactive Windows"):
                self_test("unused")

    def test_entire_suite_runs_tasks_and_verifies_report_with_simulated_windows(self, changed_process=False, learning_failure=False):
        from test_catalog import app, snapshot as inventory_snapshot
        class Desktop:
            def __init__(self, title, calculator=False):
                self.title, self.calculator, self.value = title, calculator, "6" if calculator else ""
                self.window = Mock(handle=41)
                self.window.process_id.return_value = 81
            def observe(self):
                current = snapshot(self.value, title=self.title)
                if self.calculator:
                    if changed_process:
                        current["process_id"] = 82
                    current["controls"] = [
                        {"id": 1, "name": "Two", "type": "Button", "automation_id": "num2Button", "actions": ["invoke"], "visible": True, "enabled": True},
                        {"id": 2, "name": self.value, "type": "Text", "automation_id": "CalculatorResults", "visible": True, "enabled": True},
                        {"id": 3, "name": "Equals", "type": "Button", "automation_id": "equalButton", "visible": True, "enabled": True}]
                return current
            def act(self, action):
                self.value = "45" if self.calculator else action["text"]
        class Cloud:
            def request(self, **payload):
                request = json.loads(payload["input"])
                if "blueprint" in request and "observation" not in request:
                    self_test_case.assertEqual(request["experiment_context"]["required_task_form"],
                                               "Replace the document text with exactly: <your own short test text>")
                    action = {"task": "Replace the document text with exactly: Independent practice", "expected_result": "Independent practice",
                              "capability_name": "Write text", "risk": "disposable"}
                    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(action)}]}]}
                goal = request.get("required_exact_editor_text")
                if goal is not None:
                    current = request["observation"]["controls"][0]["value"]
                    action = ({"kind": "finish", "expected_text": goal, "reason": "Verified"} if current == goal
                              else {"kind": "type", "target": 1, "text": goal, "reason": "Replace"})
                else:
                    current = request["observation"]["controls"][1]["name"]
                    action = ({"kind": "finish", "expected_text": "45", "reason": "Verified"} if current == "45"
                              else {"kind": "invoke", "target": 1, "reason": "Calculate"})
                target = next((c for c in request["observation"]["controls"] if c["id"] == action.get("target")), None)
                if target:
                    action["automation_id"] = target.get("automation_id")
                    action["target_name"] = target["name"]
                return {"output": [{"content": [{"type": "output_text", "text": json.dumps(action)}]}]}
        def open_fixture(fixture):
            fixture.path.write_text("", encoding="utf-8")
            fixture.desktop = Desktop(fixture.path.stem + " - Notepad")
            fixture.identity = (41, 81)
            # The fake models Notepad's on-disk text, not Python's automatic
            # newline translation (which doubles CRLF on Windows).
            fixture.desktop.window.type_keys.side_effect = lambda *a, **k: fixture.path.write_text(fixture.desktop.value, encoding="utf-8", newline="")
            return {"test_file": str(fixture.path)}
        package = types.ModuleType("pywinauto")
        package.win32functions = types.SimpleNamespace(GetForegroundWindow=lambda: 41)
        calculator = Desktop("Calculator", calculator=True)
        self_test_case = self
        blueprint = {"name": "Microsoft Windows Notepad", "version": "", "sources": [{"url": "https://example.com/notepad-manual"}],
                     "capabilities": [{"name": "Write text", "steps": ["Type into the editor"], "expected_result": "Text appears"}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch("app_agent.self_test.sys.platform", "win32"), \
             patch("app_agent.self_test.foreground_window", return_value=41), \
             patch("app_agent.self_test.doctor", return_value={"visible_windows": 1, "dependencies": {"pywinauto": True}}), \
             patch("app_agent.self_test.scan_apps", return_value=inventory_snapshot([app()])), \
             patch("app_agent.self_test.calculator_smoke", return_value={"passed": 3, "window_handle": 41, "process_id": 81}), \
             patch("app_agent.learning.research_app", side_effect=RuntimeError("Documentation unavailable") if learning_failure else None,
                   return_value=blueprint) as research, \
             patch.object(NotepadFixture, "open", open_fixture), \
             patch("app_agent.self_test.WindowsDesktop") as windows:
            # Other Calculator windows must not affect the established fixture.
            windows.windows.return_value = [(41, "Calculator"), (42, "Calculator")]
            windows.return_value = calculator
            report = self_test(directory, cloud=Cloud(), emit=lambda text: None)
            if changed_process:
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["counts"]["failed"], 1)
                failed = next(item for item in report["checks"] if item["name"] == "AI Calculator task")
                self.assertIn("changed identity", failed["error"])
                self.assertEqual(calculator.value, "6")
                return
            if learning_failure:
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["counts"]["passed"], 12)
                self.assertEqual(report["counts"]["failed"], 1)
                self.assertIn("Documentation unavailable", report["checks"][-1]["error"])
                return
            self.assertEqual(report["status"], "passed", json.dumps(report["checks"], indent=2))
            self.assertEqual(report["counts"]["passed"], 13)
            self.assertEqual(json.loads(Path(report["report_path"]).read_text(encoding="utf-8")), report)
            sessions = Path(report["report_path"]).parent / "sessions.jsonl"
            records = [json.loads(line) for line in sessions.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 4)
            self.assertTrue(all(r["actions_executed"] == 1 and r["outcome"] == "result_observed" for r in records))
            research.assert_called_once()
            self.assertEqual(research.call_args.args[:2], ("Microsoft Windows Notepad", ""))
            details = report["checks"][-1]["details"]
            self.assertEqual(details["overview"]["capabilities_tested_once"], 1)
            self.assertEqual(details["overview"]["capabilities_tested_repeatedly"], 0)
            self.assertEqual(details["documentation_sources"], ["https://example.com/notepad-manual"])
            windows.assert_called_once_with(41)
            windows.windows.assert_not_called()

    def test_calculator_reused_handle_with_different_process_is_rejected(self):
        self.test_entire_suite_runs_tasks_and_verifies_report_with_simulated_windows(changed_process=True)

    def test_learning_research_failure_does_not_hide_other_windows_results(self):
        self.test_entire_suite_runs_tasks_and_verifies_report_with_simulated_windows(learning_failure=True)

    def test_entire_simulated_suite_with_windows_newline_translation(self):
        original = Path.write_text
        def windows_write(path, data, encoding=None, errors=None, newline=None):
            return original(path, data, encoding=encoding, errors=errors,
                            newline="\r\n" if newline is None else newline)
        with patch.object(Path, "write_text", windows_write):
            self.test_entire_suite_runs_tasks_and_verifies_report_with_simulated_windows()
